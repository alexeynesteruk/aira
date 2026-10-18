import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import SecretStr

from app.llm import experiment
from app.llm.config import OpenAISettings
from app.llm.experiment import prepare, run_experiment
from app.llm.openai_adapter import ModelCandidate, ModelFailure, ModelMetrics
from app.schemas import CandidateRequest, ErrorCode, OperationalError, ScopeCandidate

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.parametrize("case", ["venous_matched", "venous_missing_diameter", "monitor_matched"])
def test_stage_packets_contain_reviewed_sources_without_expected_patient_answers(case):
    scope = prepare(ROOT, case, "scope")
    policy = prepare(ROOT, case, "policy")
    evidence = prepare(ROOT, case, "evidence")
    assert len(scope.packet["documents"]) == 2
    assert len(policy.packet["documents"]) == 1
    assert policy.packet["documents"][0]["role"] == "policy"
    assert evidence.packet["criteria_origin"].startswith("independent_policy_annotation")
    assert all(set(item) == {"criterion_id", "wording"} for item in evidence.packet["criteria"])
    for item in (scope, policy, evidence):
        assert "findings" not in item.packet and "expected_id" not in item.packet
        assert "outcome" not in item.packet and "status" not in item.packet
        assert all("held" not in source_id for source_id in item.hashes)
        assert all(document["pages"][0]["page"] == 1 for document in item.packet["documents"])


@pytest.mark.parametrize("case", ["unknown", "held_out", "supplied_pair_mismatch"])
def test_text_experiment_rejects_unknown_reserved_and_pdf_inputs(case):
    with pytest.raises(ValueError):
        prepare(ROOT, case, "scope")


def test_prepare_checks_source_hash_before_contacting_provider(tmp_path):
    (tmp_path / "evals/cases").mkdir(parents=True)
    manifest = {
        "cases": [{"case_id": "changed", "policy_source_id": "policy", "chart_source_id": "chart"}]
    }
    (tmp_path / "evals/cases/development.json").write_text(json.dumps(manifest))
    (tmp_path / "tests/fixtures/scenarios").mkdir(parents=True)
    (tmp_path / "tests/fixtures/scenarios/policy.md").write_text("changed")
    registry = {
        "sources": {
            "policy": {
                "path": "tests/fixtures/scenarios/policy.md",
                "split": "development",
                "format": "markdown",
                "role": "policy",
                "sha256": "0" * 64,
            }
        }
    }
    (tmp_path / "evals/source-registry.json").write_text(json.dumps(registry))
    with pytest.raises(ValueError, match="hash"):
        prepare(tmp_path, "changed", "scope")


@pytest.mark.anyio
@pytest.mark.parametrize("fail", [False, True])
async def test_experiment_records_candidates_or_safe_failures_without_scoring_itself(fail):
    metrics = ModelMetrics(1, 12.0, 20, 10, ("req_test",), ("resp_test",))

    class FakeAdapter:
        async def interpret(self, **kwargs):
            assert "test-secret" not in kwargs["source_text"] + kwargs["instructions"]
            if fail:
                raise ModelFailure(
                    OperationalError(
                        code=ErrorCode.THROTTLED,
                        message="Quota unavailable.",
                        action="Enable project quota.",
                        retryable=False,
                    ),
                    metrics,
                )
            candidate = ScopeCandidate(
                request=CandidateRequest(
                    procedure=None,
                    procedure_code=None,
                    anatomical_target=None,
                    laterality=None,
                    payer=None,
                    plan=None,
                    service_date=None,
                    assessment_cutoff=None,
                ),
                status="unresolved",
                rationale="Controlled transport response, not a semantic expectation.",
                citations=(),
                unresolved_fields=("procedure",),
            )
            return ModelCandidate(candidate, "test-model", "scope-v1", metrics)

    settings = OpenAISettings(api_key=SecretStr("test-secret"), model="test-model")
    result = await run_experiment(
        prepare(ROOT, "venous_matched", "scope"), settings, adapter=FakeAdapter()
    )
    assert result["status"] == ("failed" if fail else "candidate_received")
    assert result["semantic_validation"] == "not_performed"
    assert result["production_assessment"] is False
    assert "test-secret" not in json.dumps(result)
    assert result["metrics"]["attempts"] == 1


def test_cli_prepares_valid_case_without_loading_credentials(tmp_path, monkeypatch, capsys):
    item = prepare(ROOT, "venous_matched", "scope")
    monkeypatch.setattr(experiment, "prepare", lambda *args: item)

    def unexpected_credentials(**kwargs):
        raise AssertionError("Preparation must not access credentials or the provider")

    monkeypatch.setattr(OpenAISettings, "from_environment", unexpected_credentials)
    monkeypatch.setattr(sys, "argv", ["experiment", "--root", str(tmp_path)])
    assert experiment.main() == 0
    assert "no provider call was made" in capsys.readouterr().out
    output = tuple((tmp_path / "data/model-experiments").glob("*/input.json"))
    assert len(output) == 1
    assert json.loads(output[0].read_text())["status"] == "prepared"


def test_cli_reports_invalid_case_without_a_traceback(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.llm.experiment",
            "--case",
            "unknown",
            "--env-file",
            str(tmp_path / "missing.env"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "Check the development case" in result.stderr
    assert "Traceback" not in result.stderr
