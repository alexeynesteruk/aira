"""One-assessment CLI vertical slice over the real engine and provider adapter.

Live calls require OPENAI_API_KEY and AIRA_MODEL; missing configuration exits 2
before any provider contact. Results are persisted artifacts, never fixtures.
"""

import argparse
import asyncio
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import ValidationError

from app.assessment.build_config import build_limits_from_environment
from app.assessment.builds import DocumentBuildService
from app.assessment.export import render_markdown
from app.assessment.stages import StageInterpreter
from app.assessment.workflow import (
    WorkflowEngine,
    WorkflowLimits,
    workflow_parser_fingerprint,
)
from app.documents import NativePdfConfig, PdfInputError, inspect_pdf
from app.llm.config import OpenAISettings
from app.llm.interpreter import OpenAIStageInterpreter, openai_configuration
from app.llm.openai_adapter import OpenAIAdapter
from app.policies.compiler import BuildLimits
from app.schemas import (
    AssessmentExport,
    ConfigurationProvenance,
    CreateAssessmentRequest,
    DateAnnotation,
    DocumentRole,
    MetadataAnnotation,
    RunRecord,
    RunStatus,
    TextAnnotation,
)
from app.storage import LocalStore

_TEXT_FIELDS: tuple[
    Literal["procedure", "procedure_code", "anatomical_target", "laterality", "payer", "plan"],
    ...,
] = ("procedure", "procedure_code", "anatomical_target", "laterality", "payer", "plan")
_DATE_FIELDS: tuple[Literal["service_date", "assessment_cutoff"], ...] = (
    "service_date",
    "assessment_cutoff",
)


async def run_assessment(
    policy_path: Path,
    chart_path: Path,
    *,
    store: LocalStore,
    interpreter: StageInterpreter,
    configuration: ConfigurationProvenance,
    annotations: tuple[MetadataAnnotation, ...] = (),
    parser_config: NativePdfConfig | None = None,
    limits: WorkflowLimits | None = None,
    build_limits: BuildLimits | None = None,
) -> RunRecord:
    """Ingest both PDFs, run the bounded workflow, and return the stopped run."""
    now = datetime.now(UTC)
    policy_raw = policy_path.read_bytes()
    policy_document = inspect_pdf(
        policy_raw,
        document_id=f"doc-{uuid4().hex}",
        filename=policy_path.name,
        role=DocumentRole.POLICY,
        created_at=now,
    )
    chart_raw = chart_path.read_bytes()
    chart_document = inspect_pdf(
        chart_raw,
        document_id=f"doc-{uuid4().hex}",
        filename=chart_path.name,
        role=DocumentRole.CHART,
        created_at=now,
    )
    store.put_document(policy_document, policy_raw)
    store.put_document(chart_document, chart_raw)
    engine = WorkflowEngine(
        store,
        interpreter,
        configuration,
        parser_config=parser_config,
        limits=limits,
        build_limits=build_limits,
    )
    await engine.start()
    try:
        submitted = await engine.submit(
            CreateAssessmentRequest(
                policy_document_id=policy_document.document_id,
                chart_document_id=chart_document.document_id,
                annotations=annotations,
            )
        )
        return await engine.wait(submitted.run_id)
    finally:
        await engine.close()


def write_outputs(store: LocalStore, run: RunRecord, output_dir: Path) -> list[Path]:
    """Persist run.json always; completed/needs_input runs also export."""
    output_dir.mkdir(parents=True, exist_ok=True)
    written = [output_dir / "run.json"]
    written[0].write_text(run.model_dump_json(indent=2) + "\n")
    if run.status in (RunStatus.COMPLETED, RunStatus.NEEDS_INPUT):
        export = AssessmentExport(
            exported_at=datetime.now(UTC),
            run=run,
            documents=(
                store.get_document(run.policy_document_id),
                store.get_document(run.chart_document_id),
            ),
        )
        export_path = output_dir / "export.json"
        export_path.write_text(export.model_dump_json(indent=2) + "\n")
        written.append(export_path)
        checklist_path = output_dir / "checklist.md"
        checklist_path.write_text(render_markdown(export))
        written.append(checklist_path)
    return written


def _annotations(arguments: argparse.Namespace) -> tuple[MetadataAnnotation, ...]:
    now = datetime.now(UTC)
    annotations: list[MetadataAnnotation] = []
    for text_field in _TEXT_FIELDS:
        value = getattr(arguments, text_field)
        if value is not None:
            annotations.append(
                TextAnnotation(
                    annotation_id=f"staff-{text_field}",
                    field=text_field,
                    value=value,
                    created_at=now,
                )
            )
    for date_field in _DATE_FIELDS:
        value = getattr(arguments, date_field)
        if value is not None:
            annotations.append(
                DateAnnotation(
                    annotation_id=f"staff-{date_field}",
                    field=date_field,
                    value=value,
                    created_at=now,
                )
            )
    return tuple(annotations)


async def _assess(arguments: argparse.Namespace, settings: OpenAISettings) -> int:
    adapter = OpenAIAdapter(settings)
    try:
        output_dir = arguments.output_dir or arguments.data_dir / "exports"
        store = LocalStore(arguments.data_dir)
        try:
            run = await run_assessment(
                arguments.policy,
                arguments.chart,
                store=store,
                interpreter=OpenAIStageInterpreter(adapter),
                configuration=openai_configuration(
                    settings,
                    workflow_parser_fingerprint(NativePdfConfig(), WorkflowLimits()),
                ),
                annotations=_annotations(arguments),
                build_limits=build_limits_from_environment(
                    env_file=arguments.env_file, output_tokens=settings.max_output_tokens
                ),
            )
        except PdfInputError as exc:
            print(f"{exc.error.message} {exc.error.action}", file=sys.stderr)
            return 2
        written = write_outputs(store, run, output_dir)
        print(f"Run {run.run_id}: {run.status.value}")
        if run.result is not None:
            print(f"Outcome: {run.result.outcome.value}")
        if run.error is not None:
            print(f"Error {run.error.code.value}: {run.error.message}", file=sys.stderr)
        for path in written:
            print(f"Wrote {path}")
        return 0 if run.status in (RunStatus.COMPLETED, RunStatus.NEEDS_INPUT) else 1
    finally:
        await adapter.close()


async def _prepare(arguments: argparse.Namespace, settings: OpenAISettings) -> int:
    adapter = OpenAIAdapter(settings)
    parser_config = NativePdfConfig()
    store = LocalStore(arguments.data_dir)
    builds = DocumentBuildService(
        store,
        OpenAIStageInterpreter(adapter),
        openai_configuration(
            settings, workflow_parser_fingerprint(parser_config, WorkflowLimits())
        ),
        parser_config=parser_config,
        limits=build_limits_from_environment(
            env_file=arguments.env_file, output_tokens=settings.max_output_tokens
        ),
    )
    try:
        raw = arguments.document.read_bytes()
        doc = inspect_pdf(
            raw,
            document_id="doc-" + uuid4().hex,
            filename=arguments.document.name,
            role=DocumentRole(arguments.role),
            created_at=datetime.now(UTC),
        )
        store.put_document(doc, raw)
        await builds.start()
        record = await builds.wait((await builds.submit(doc.document_id)).build_id)
        output = arguments.output_dir or arguments.data_dir / "exports" / record.build_id
        output.mkdir(parents=True, exist_ok=True)
        target = output / "build.json"
        target.write_text(record.model_dump_json(indent=2) + "\n")
        print(f"Build {record.build_id}: {record.status}; saved {target}")
        if record.error:
            print(record.error.message, file=sys.stderr)
        return 0 if record.status == "completed" else 1
    except (PdfInputError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        await builds.close()
        await adapter.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aira", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    assess = commands.add_parser("assess", help="Assess one policy/chart PDF pair.")
    assess.add_argument("--policy", type=Path, required=True)
    assess.add_argument("--chart", type=Path, required=True)
    assess.add_argument("--data-dir", type=Path, default=Path("data/cli"))
    assess.add_argument("--output-dir", type=Path, default=None)
    assess.add_argument("--env-file", type=Path, default=Path(".env"))
    for text_field in _TEXT_FIELDS:
        assess.add_argument(f"--{text_field.replace('_', '-')}", dest=text_field)
    for date_field in _DATE_FIELDS:
        assess.add_argument(
            f"--{date_field.replace('_', '-')}", dest=date_field, type=date.fromisoformat
        )
    prepare = commands.add_parser("prepare", help="Prepare one policy or chart independently.")
    prepare.add_argument("--document", type=Path, required=True)
    prepare.add_argument("--role", choices=("policy", "chart"), required=True)
    prepare.add_argument("--data-dir", type=Path, default=Path("data/cli"))
    prepare.add_argument("--output-dir", type=Path, default=None)
    prepare.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args(argv)
    try:
        settings = OpenAISettings.from_environment(env_file=arguments.env_file)
    except ValidationError:
        print(
            "Configure OPENAI_API_KEY and AIRA_MODEL in the environment or .env.",
            file=sys.stderr,
        )
        return 2
    return asyncio.run(
        _prepare(arguments, settings)
        if arguments.command == "prepare"
        else _assess(arguments, settings)
    )


if __name__ == "__main__":
    raise SystemExit(main())
