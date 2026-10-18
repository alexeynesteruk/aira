"""Prepare or explicitly run one isolated model stage on development text fixtures.

This is a feasibility instrument, not the production assessment workflow. It never
reads expected chart findings, grades its own answers, or opens the reserved set.
"""

import argparse
import asyncio
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from pydantic import ValidationError

from app.schemas import SCHEMA_VERSION

from .config import OpenAISettings
from .openai_adapter import ModelFailure, OpenAIAdapter, strict_output_schema
from .prompts import PROMPTS, StageName


@dataclass(frozen=True)
class ExperimentInput:
    case_id: str
    stage: StageName
    packet: dict[str, Any]
    hashes: dict[str, str]
    expectation_reference: str


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("Experiment manifest must be a JSON object")
    return value


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def prepare(root: Path, case_id: str, stage: StageName) -> ExperimentInput:
    """Load exact development inputs; expected patient answers never enter a prompt."""
    root = root.resolve()
    manifest_path = root / "evals/cases/development.json"
    registry_path = root / "evals/source-registry.json"
    cases = _read_json(manifest_path)["cases"]
    matches = [case for case in cases if case["case_id"] == case_id]
    if len(matches) != 1:
        raise ValueError("Select one case from the development manifest")
    case = matches[0]
    registry = _read_json(registry_path)["sources"]
    hashes = {
        "development_manifest": _sha(manifest_path.read_bytes()),
        "source_registry": _sha(registry_path.read_bytes()),
    }
    documents = []
    for role in ("policy", "chart"):
        source_id = case[f"{role}_source_id"]
        record = registry[source_id]
        if record["split"] != "development" or record["format"] != "markdown":
            raise ValueError("This isolated experiment accepts development text fixtures only")
        path = (root / record["path"]).resolve()
        if not path.is_relative_to(root / "tests/fixtures/scenarios"):
            raise ValueError("Fixture source must remain inside the scenario directory")
        data = path.read_bytes()
        if _sha(data) != record["sha256"] or record["role"] != role:
            raise ValueError("Fixture source hash or role differs from its reviewed registry")
        parts = re.split(r"<!-- page:(\d+) -->", data.decode())
        pages = [
            {"page": int(parts[index]), "text": parts[index + 1].strip()}
            for index in range(1, len(parts), 2)
        ]
        if [page["page"] for page in pages] != record["logical_pages"]:
            raise ValueError("Fixture logical pages differ from their reviewed registry")
        documents.append({"document_id": source_id, "role": role, "pages": pages})
        hashes[source_id] = record["sha256"]
    packet: dict[str, Any] = {
        "input_kind": "fictional_text_with_logical_pages_not_pdf_extraction",
        "selected_request": case["request"],
        "documents": documents if stage != "policy" else [documents[0]],
    }
    if stage == "evidence":
        # An isolated evidence experiment uses reviewed criteria, not a generated
        # policy candidate. The end-to-end pipeline must validate its own policy.
        policy_path = root / "evals/expected/policies.json"
        policy = _read_json(policy_path)["policies"][case["policy_expectation_id"]]
        packet["criteria_origin"] = "independent_policy_annotation_for_isolated_stage"
        packet["criteria"] = [
            {"criterion_id": item["criterion_id"], "wording": item["wording"]}
            for item in policy["criteria"]
        ]
        hashes["policy_annotations"] = _sha(policy_path.read_bytes())
    return ExperimentInput(
        case_id, stage, packet, hashes, f"evals/expected/development.json#{case['expected_id']}"
    )


def experiment_record(item: ExperimentInput) -> dict[str, Any]:
    prompt = PROMPTS[item.stage]
    schema = strict_output_schema(prompt.output_type)
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "kind": "isolated_stage_feasibility",
        "case_id": item.case_id,
        "stage": item.stage,
        "schema_version": SCHEMA_VERSION,
        "output_schema_sha256": _sha(json.dumps(schema, sort_keys=True).encode()),
        "prompt_version": prompt.version,
        "prompt_sha256": _sha(prompt.instructions.encode()),
        "input_sha256": item.hashes,
        "expectation_reference": item.expectation_reference,
        "semantic_validation": "not_performed",
        "production_assessment": False,
    }


async def run_experiment(
    item: ExperimentInput, settings: OpenAISettings, *, adapter: OpenAIAdapter | None = None
) -> dict[str, Any]:
    prompt = PROMPTS[item.stage]
    client = adapter or OpenAIAdapter(settings)
    record = {
        **experiment_record(item),
        "provider": "openai",
        "api": "responses",
        "configured_model": settings.model,
        "sdk_version": version("openai"),
        "max_output_tokens": settings.max_output_tokens,
        "max_attempts": settings.max_attempts,
        "request_timeout_seconds": settings.request_timeout_seconds,
        "stage_timeout_seconds": settings.stage_timeout_seconds,
    }
    try:
        result = await client.interpret(
            phase=prompt.phase,
            instructions=prompt.instructions,
            source_text=json.dumps(item.packet),
            output_type=prompt.output_type,
            prompt_version=prompt.version,
        )
        return {
            **record,
            "status": "candidate_received",
            "model": result.model,
            "candidate": result.value.model_dump(mode="json"),
            "metrics": asdict(result.metrics),
        }
    except ModelFailure as exc:
        return {
            **record,
            "status": "failed",
            "error": exc.error.model_dump(mode="json"),
            "metrics": asdict(exc.metrics),
        }
    finally:
        if adapter is None:
            await client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--case", default="venous_matched")
    parser.add_argument("--stage", choices=tuple(PROMPTS), default="scope")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--model", help="Explicit nonsecret model override for comparison")
    parser.add_argument("--live", action="store_true", help="Make a billable provider call")
    parser.add_argument("--repeat", type=int, choices=(1, 2, 3), default=1)
    args = parser.parse_args()
    try:
        item = prepare(args.root, args.case, cast(StageName, args.stage))
        settings = OpenAISettings.from_environment(env_file=args.env_file) if args.live else None
        if settings is not None and args.model:
            settings = OpenAISettings.model_validate({**settings.model_dump(), "model": args.model})
    except (OSError, ValueError, KeyError, ValidationError):
        parser.error(
            "Check the development case, reviewed source files, and key/model configuration"
        )
    folder = args.root / "data/model-experiments" / uuid4().hex
    folder.mkdir(parents=True)
    prompt = PROMPTS[item.stage]
    packet = {
        **experiment_record(item),
        "status": "prepared",
        "instructions": prompt.instructions,
        "input": item.packet,
        "output_schema": strict_output_schema(prompt.output_type),
    }
    (folder / "input.json").write_text(json.dumps(packet, indent=2) + "\n")
    if settings is None:
        print(f"Prepared {folder / 'input.json'}; no provider call was made.")
        return 0
    for index in range(args.repeat):
        result = asyncio.run(run_experiment(item, settings))
        target = folder / f"attempt-{index + 1}.json"
        target.write_text(json.dumps(result, indent=2) + "\n")
        print(f"{result['status']}: {target}")
        if result["status"] == "failed":
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
