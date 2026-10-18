"""Production stage interpreter and CLI slice over a mocked transport.

Every Responses-API body here is scripted test data quoting real native text —
it is not model output and proves nothing about live semantic quality. No test
contacts a provider: the real AsyncOpenAI SDK client runs on httpx.MockTransport
with SDK retries disabled, as in test_openai_adapter.py.
"""

import hashlib
import json
import sqlite3
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from openai import AsyncOpenAI
from pydantic import SecretStr

import app.cli as cli
from app.assessment.stages import InterpretationFailure, StageInputs, render_stage_input
from app.assessment.workflow import (
    WorkflowEngine,
    WorkflowLimits,
    workflow_parser_fingerprint,
)
from app.cli import run_assessment, write_outputs
from app.documents import NativePdfConfig, extract_pdf, inspect_pdf
from app.llm.config import OpenAISettings
from app.llm.interpreter import (
    OpenAIStageInterpreter,
    openai_configuration,
    prompt_reference,
)
from app.llm.openai_adapter import OpenAIAdapter
from app.llm.prompts import PROMPTS
from app.schemas import (
    ApplicabilityStatus,
    AssessmentExport,
    AssessmentOutcome,
    ConfigurationProvenance,
    CreateAssessmentRequest,
    DocumentRecord,
    DocumentRole,
    ErrorCode,
    ExtractionRecord,
    ModelProvider,
    RunPhase,
    RunStatus,
)
from app.storage import LocalStore

ROOT = Path(__file__).resolve().parents[2]
POLICY_PDF = ROOT / "examples/guidelines/bcbs_fl_02-33000-31_2025-08-15.pdf"
CHART_PDF = ROOT / "examples/charts/robert_mitchell_chart_final.pdf"
CREATED_AT = datetime(2026, 10, 18, tzinfo=UTC)

# Exact quotes, each unique on its page in the supplied documents.
POLICY_SCOPE_QUOTE = (1, "Subject: Treatments for Varicose Veins/Venous")
CHART_SCOPE_QUOTE = (1, "PATIENT MEDICAL CHART")
POLICY_CRITERION_QUOTE = (3, "Treatment of telangiectasia such as spider veins")
CHART_FACT_QUOTE = (3, "HR: 44 bpm, regular")
CHART_PROCEDURE_QUOTE = (3, "ambulatory Holter monitor")
CHART_PAYER_QUOTE = (1, "Payer: UnitedHealthcare")
CHART_PLAN_QUOTE = (1, "AARP Medicare Advantage Choice")

POLICY_ID = "policy-doc"
CHART_ID = "chart-doc"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _parse(
    path: Path, role: DocumentRole, document_id: str
) -> tuple[DocumentRecord, ExtractionRecord, bytes]:
    raw = path.read_bytes()
    document = inspect_pdf(
        raw,
        document_id=document_id,
        filename=path.name,
        role=role,
        created_at=CREATED_AT,
    )
    return document, extract_pdf(raw, document, created_at=CREATED_AT), raw


@pytest.fixture(scope="module")
def sources() -> dict[str, tuple[DocumentRecord, ExtractionRecord, bytes]]:
    return {
        "policy": _parse(POLICY_PDF, DocumentRole.POLICY, POLICY_ID),
        "chart": _parse(CHART_PDF, DocumentRole.CHART, CHART_ID),
    }


@pytest.fixture
def inputs(
    sources: dict[str, tuple[DocumentRecord, ExtractionRecord, bytes]],
) -> StageInputs:
    return StageInputs(
        sources["policy"][0], sources["chart"][0], sources["policy"][1], sources["chart"][1]
    )


@pytest.fixture
def store(
    tmp_path: Path, sources: dict[str, tuple[DocumentRecord, ExtractionRecord, bytes]]
) -> LocalStore:
    store = LocalStore(tmp_path / "store")
    for record, extraction, raw in sources.values():
        store.put_document(record, raw)
        store.put_extraction(extraction)
    return store


def _settings() -> OpenAISettings:
    return OpenAISettings(api_key=SecretStr("test-key-not-real"), model="test-model")


def _envelope(text: str, response_id: str) -> dict[str, object]:
    return {
        "id": response_id,
        "object": "response",
        "created_at": 1.0,
        "model": "test-model",
        "status": "completed",
        "error": None,
        "parallel_tool_calls": False,
        "tools": [],
        "tool_choice": "none",
        "output": [
            {
                "id": "msg_test",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            }
        ],
        "usage": {
            "input_tokens": 31,
            "output_tokens": 9,
            "total_tokens": 40,
            "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0},
        },
    }


type _Body = dict[str, object] | httpx.Response | Callable[[dict[str, object]], dict[str, object]]


def _adapter(bodies: dict[str, _Body], requests: list[httpx.Request]) -> OpenAIAdapter:
    """Adapter over the real SDK; bodies are keyed by strict schema name."""

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        name = json.loads(request.content)["text"]["format"]["name"]
        body = bodies[name]
        if isinstance(body, httpx.Response):
            return body
        if callable(body):
            body = body(json.loads(json.loads(request.content)["input"]))
        return httpx.Response(
            200,
            json=_envelope(json.dumps(body), f"resp-{name}"),
            headers={"x-request-id": f"req-{name}"},
        )

    client = AsyncOpenAI(
        api_key="test-key-not-real",
        base_url="https://api.openai.com/v1",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
    )
    return OpenAIAdapter(_settings(), client=client)


def _citation(document_id: str, page_quote: tuple[int, str]) -> dict[str, object]:
    return {"document_id": document_id, "page": page_quote[0], "quote": page_quote[1]}


def _scope_candidate(
    policy_id: str, chart_id: str, status: str, *, corrupt: bool = False
) -> dict[str, object]:
    scope_citations = [
        _citation(policy_id, POLICY_SCOPE_QUOTE),
        _citation(chart_id, CHART_SCOPE_QUOTE),
    ]
    if corrupt:
        scope_citations[0] = _citation(
            policy_id, (1, "This exact passage was never written in the policy.")
        )
    return {
        "schema_version": "0.1.0",
        "request": {
            "procedure": "ambulatory Holter monitor",
            "procedure_code": None,
            "anatomical_target": None,
            "laterality": None,
            "payer": "UnitedHealthcare",
            "plan": "AARP Medicare Advantage Choice PPO",
            "service_date": None,
            "assessment_cutoff": None,
        },
        "status": status,
        "rationale": (
            "The cited policy covers varicose-vein treatment, not the requested cardiac monitoring."
            if status == "mismatch"
            else "The scripted request fields match the cited scope."
        ),
        "citations": scope_citations,
        "unresolved_fields": [],
        "field_sources": [
            {
                "field": "procedure",
                "citations": [_citation(chart_id, CHART_PROCEDURE_QUOTE)],
            },
            {"field": "payer", "citations": [_citation(chart_id, CHART_PAYER_QUOTE)]},
            {"field": "plan", "citations": [_citation(chart_id, CHART_PLAN_QUOTE)]},
        ],
    }


def _policy_candidate(policy_id: str) -> dict[str, object]:
    citation = _citation(policy_id, POLICY_CRITERION_QUOTE)
    return {
        "schema_version": "0.1.0",
        "title": "Treatments for Varicose Veins/Venous Insufficiency",
        "scope_summary": "Medical-necessity criteria for varicose-vein treatments.",
        "identifier": "02-33000-31",
        "revision_date": "2025-08-15",
        "effective_from": None,
        "effective_to": None,
        "criteria": [
            {
                "criterion_id": "telangiectasia-cosmetic",
                "wording": "Treatment of telangiectasia is considered cosmetic.",
                "interpretation": "Does the chart document the cited requirement?",
                "citations": [citation],
                "context": [],
                "predicate_kind": "narrative",
                "operator": None,
                "threshold": None,
                "unit": None,
                "date_boundary": None,
                "date_role": None,
            }
        ],
        "nodes": [
            {
                "node_id": "root",
                "kind": "criterion",
                "children": [],
                "criterion_id": "telangiectasia-cosmetic",
                "citations": [citation],
            }
        ],
        "root_id": "root",
        "sections": [
            {
                "section_id": "position",
                "heading": "Position statement",
                "citations": [citation],
                "disposition": "requirements",
                "criterion_ids": ["telangiectasia-cosmetic"],
                "explanation": "The single scripted criterion is the requirement.",
            }
        ],
        "interpretation_issues": [],
    }


def _evidence_candidate(chart_id: str, *, corrupt: bool = False) -> dict[str, object]:
    citation = _citation(
        chart_id,
        (3, "This exact passage was never written in the chart.") if corrupt else CHART_FACT_QUOTE,
    )
    return {
        "schema_version": "0.1.0",
        "facts": [
            {
                "fact_id": "heart-rate",
                "proposition": "The chart documents a resting heart rate of 44 bpm.",
                "citations": [citation],
                "polarity": "affirmed",
                "provenance": "direct",
                "value": None,
                "unit": None,
                "event_date": None,
                "documentation_date": None,
                "anatomical_target": None,
                "laterality": None,
                "context": [],
                "uncertainty": [],
                "conflicting_fact_ids": [],
            }
        ],
        "findings": [
            {
                "criterion_id": "telangiectasia-cosmetic",
                "status": "met",
                "rationale": "The cited vital-sign entry is scripted as supporting.",
                "evidence": [{"fact_id": "heart-rate", "relation": "supporting"}],
                "unresolved_reasons": [],
            }
        ],
    }


def _configuration() -> tuple[ConfigurationProvenance, WorkflowLimits]:
    limits = WorkflowLimits()
    return (
        openai_configuration(
            _settings(),
            workflow_parser_fingerprint(NativePdfConfig(), limits),
        ),
        limits,
    )


@pytest.mark.anyio
async def test_scope_request_content_and_mismatch_conversion(inputs: StageInputs) -> None:
    requests: list[httpx.Request] = []
    adapter = _adapter(
        {"ScopeCandidate": _scope_candidate(POLICY_ID, CHART_ID, "mismatch")}, requests
    )
    interpreter = OpenAIStageInterpreter(adapter)
    try:
        result = await interpreter.scope(inputs)
    finally:
        await adapter.close()

    assert len(requests) == 1
    body = json.loads(requests[0].content)
    assert requests[0].url.path == "/v1/responses"
    assert body["instructions"] == PROMPTS["scope"].instructions
    assert body["input"] == render_stage_input(inputs, "scope")
    assert body["text"]["format"]["type"] == "json_schema"
    assert body["text"]["format"]["strict"] is True
    assert body["store"] is False

    assert result.applicability.status == ApplicabilityStatus.MISMATCH
    documents = {source.document_id for source in result.applicability.sources}
    assert documents == {POLICY_ID, CHART_ID}
    assert all(source.extraction_id for source in result.applicability.sources)
    assert result.request.procedure == "ambulatory Holter monitor"
    usage = result.usage
    assert usage is not None
    assert usage.phase == RunPhase.CHECKING_APPLICABILITY
    assert usage.attempts == 1
    assert (usage.input_tokens, usage.output_tokens) == (31, 9)
    assert usage.provider_request_ids == ("req-ScopeCandidate",)
    assert usage.provider_response_ids == ("resp-ScopeCandidate",)
    assert usage.model_id == "test-model"


@pytest.mark.anyio
async def test_policy_and_evidence_stages_convert_candidates(
    inputs: StageInputs,
    sources: dict[str, tuple[DocumentRecord, ExtractionRecord, bytes]],
) -> None:
    requests: list[httpx.Request] = []
    adapter = _adapter(
        {
            "PolicyCandidate": _policy_candidate(POLICY_ID),
            "EvidenceCandidate": _evidence_candidate(CHART_ID),
        },
        requests,
    )
    interpreter = OpenAIStageInterpreter(adapter)
    try:
        interpreted_policy = await interpreter.policy(inputs)
        interpreted_evidence = await interpreter.evidence(inputs, interpreted_policy.policy)
    finally:
        await adapter.close()

    policy = interpreted_policy.policy
    expected_id = (
        "policy-"
        + hashlib.sha256(
            f"{sources['policy'][1].extraction_id}|{prompt_reference('policy').version}".encode()
        ).hexdigest()[:24]
    )
    assert policy.policy_id == expected_id
    assert policy.document_id == POLICY_ID
    for record in (*policy.criteria, *policy.nodes, *policy.sections):
        assert all(
            source.page == POLICY_CRITERION_QUOTE[0] and source.document_id == POLICY_ID
            for source in record.sources
        )

    evidence_input = json.loads(requests[1].content)["input"]
    packet = json.loads(evidence_input)
    assert [item["document_id"] for item in packet["documents"]] == [CHART_ID]
    assert [item["criterion_id"] for item in packet["criteria"]] == ["telangiectasia-cosmetic"]
    facts = interpreted_evidence.facts
    findings = interpreted_evidence.findings
    assert len(facts) == 1 and facts[0].sources[0].page == CHART_FACT_QUOTE[0]
    assert [finding.status.value for finding in findings] == ["met"]
    assert findings[0].evidence[0].fact_id == facts[0].fact_id


@pytest.mark.anyio
async def test_an_invented_scope_quote_fails_as_citation_invalid(
    inputs: StageInputs,
) -> None:
    adapter = _adapter(
        {"ScopeCandidate": _scope_candidate(POLICY_ID, CHART_ID, "mismatch", corrupt=True)},
        [],
    )
    interpreter = OpenAIStageInterpreter(adapter)
    try:
        with pytest.raises(InterpretationFailure) as error:
            await interpreter.scope(inputs)
    finally:
        await adapter.close()

    assert error.value.error.code == ErrorCode.CITATION_INVALID
    assert error.value.error.stage == RunPhase.CHECKING_APPLICABILITY
    usage = error.value.usage
    assert usage is not None
    assert usage.attempts == 1 and usage.input_tokens == 31


@pytest.mark.anyio
async def test_an_uncited_request_field_fails_as_invalid_output(
    inputs: StageInputs,
) -> None:
    candidate = _scope_candidate(POLICY_ID, CHART_ID, "mismatch")
    candidate["field_sources"] = []  # non-null request fields lose their citations
    adapter = _adapter({"ScopeCandidate": candidate}, [])
    interpreter = OpenAIStageInterpreter(adapter)
    try:
        with pytest.raises(InterpretationFailure) as error:
            await interpreter.scope(inputs)
    finally:
        await adapter.close()

    assert error.value.error.code == ErrorCode.INVALID_OUTPUT
    assert error.value.error.stage == RunPhase.CHECKING_APPLICABILITY


@pytest.mark.anyio
async def test_quota_exhaustion_maps_to_non_retryable_throttled(
    inputs: StageInputs,
) -> None:
    adapter = _adapter(
        {
            "ScopeCandidate": httpx.Response(
                429,
                json={"error": {"type": "insufficient_quota", "code": None, "message": "x"}},
            )
        },
        [],
    )
    interpreter = OpenAIStageInterpreter(adapter)
    try:
        with pytest.raises(InterpretationFailure) as error:
            await interpreter.scope(inputs)
    finally:
        await adapter.close()

    assert error.value.error.code == ErrorCode.THROTTLED
    assert error.value.error.retryable is False
    usage = error.value.usage
    assert usage is not None
    assert usage.attempts == 1
    assert usage.input_tokens is None


def test_prompt_identity_tracks_text_and_configuration_names_the_real_parser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference = prompt_reference("scope")
    assert reference.name == "scope"
    assert reference.version.startswith(PROMPTS["scope"].version + "+")
    monkeypatch.setitem(
        PROMPTS, "scope", replace(PROMPTS["scope"], instructions="changed instructions")
    )
    assert prompt_reference("scope").version != reference.version
    monkeypatch.undo()

    configuration, _ = _configuration()
    assert configuration.provider == ModelProvider.OPENAI
    assert configuration.region is None
    assert [item.name for item in configuration.prompts] == [
        "scope",
        "policy",
        "evidence",
    ]
    engine = WorkflowEngine(
        LocalStore(tmp_path / "store"),
        OpenAIStageInterpreter(_adapter({}, [])),
        configuration,
    )
    assert engine.configuration == configuration


def _submission() -> CreateAssessmentRequest:
    return CreateAssessmentRequest(policy_document_id=POLICY_ID, chart_document_id=CHART_ID)


@pytest.mark.anyio
async def test_workflow_completes_mismatch_through_the_mocked_transport(
    store: LocalStore,
) -> None:
    requests: list[httpx.Request] = []
    adapter = _adapter(
        {"ScopeCandidate": _scope_candidate(POLICY_ID, CHART_ID, "mismatch")}, requests
    )
    configuration, limits = _configuration()
    engine = WorkflowEngine(store, OpenAIStageInterpreter(adapter), configuration, limits=limits)
    await engine.start()
    try:
        run = await engine.wait((await engine.submit(_submission())).run_id)
    finally:
        await engine.close()
        await adapter.close()

    assert run.status == RunStatus.COMPLETED
    assert run.result is not None
    assert run.result.outcome == AssessmentOutcome.APPLICABILITY_MISMATCH
    scope_usage = [usage for usage in run.usage if usage.phase == RunPhase.CHECKING_APPLICABILITY]
    assert len(scope_usage) == 1
    assert scope_usage[0].model_id == "test-model"
    assert scope_usage[0].input_tokens == 31
    assert len(requests) == 1


@pytest.mark.anyio
async def test_workflow_runs_the_full_applicable_path(store: LocalStore) -> None:
    requests: list[httpx.Request] = []
    adapter = _adapter(
        {
            "ScopeCandidate": _scope_candidate(POLICY_ID, CHART_ID, "applicable"),
            "PolicyCandidate": _policy_candidate(POLICY_ID),
            "EvidenceCandidate": _evidence_candidate(CHART_ID),
        },
        requests,
    )
    configuration, limits = _configuration()
    engine = WorkflowEngine(store, OpenAIStageInterpreter(adapter), configuration, limits=limits)
    await engine.start()
    try:
        run = await engine.wait((await engine.submit(_submission())).run_id)
    finally:
        await engine.close()
        await adapter.close()

    assert run.status == RunStatus.COMPLETED
    assert run.result is not None
    assert run.result.outcome == AssessmentOutcome.DOCUMENTED_REQUIREMENTS_SATISFIED
    assert len(requests) == 3
    interpreted = {
        usage.phase for usage in run.usage if usage.model_id == "test-model" and usage.attempts >= 1
    }
    assert interpreted == {
        RunPhase.CHECKING_APPLICABILITY,
        RunPhase.INTERPRETING_POLICY,
        RunPhase.MAPPING_EVIDENCE,
    }


@pytest.mark.anyio
async def test_an_invented_evidence_quote_fails_after_policy_was_saved(
    store: LocalStore,
) -> None:
    adapter = _adapter(
        {
            "ScopeCandidate": _scope_candidate(POLICY_ID, CHART_ID, "applicable"),
            "PolicyCandidate": _policy_candidate(POLICY_ID),
            "EvidenceCandidate": _evidence_candidate(CHART_ID, corrupt=True),
        },
        [],
    )
    configuration, limits = _configuration()
    engine = WorkflowEngine(store, OpenAIStageInterpreter(adapter), configuration, limits=limits)
    await engine.start()
    try:
        run = await engine.wait((await engine.submit(_submission())).run_id)
    finally:
        await engine.close()
        await adapter.close()

    assert run.status == RunStatus.FAILED
    assert run.error is not None
    assert run.error.code == ErrorCode.CITATION_INVALID
    assert run.error.stage == RunPhase.MAPPING_EVIDENCE
    connection = sqlite3.connect(store.database_path)
    try:
        saved = connection.execute(
            "SELECT phase FROM artifacts WHERE run_id=?", (run.run_id,)
        ).fetchall()
    finally:
        connection.close()
    assert {str(phase) for (phase,) in saved} == {
        RunPhase.CHECKING_APPLICABILITY.value,
        RunPhase.INTERPRETING_POLICY.value,
    }


@pytest.mark.anyio
async def test_cli_run_writes_run_export_and_checklist(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def scope_body(packet: dict[str, object]) -> dict[str, object]:
        ids = {item["role"]: item["document_id"] for item in packet["documents"]}
        return _scope_candidate(ids["policy"], ids["chart"], "mismatch")

    adapter = _adapter({"ScopeCandidate": scope_body}, requests)
    store = LocalStore(tmp_path / "store")
    configuration, _ = _configuration()
    try:
        run = await run_assessment(
            POLICY_PDF,
            CHART_PDF,
            store=store,
            interpreter=OpenAIStageInterpreter(adapter),
            configuration=configuration,
        )
    finally:
        await adapter.close()

    assert run.status == RunStatus.COMPLETED
    written = write_outputs(store, run, tmp_path / "out")
    assert {path.name for path in written} == {"run.json", "export.json", "checklist.md"}
    export = AssessmentExport.model_validate_json((tmp_path / "out" / "export.json").read_text())
    assert export.run.run_id == run.run_id
    assert "applicability_mismatch" in (tmp_path / "out" / "checklist.md").read_text()


@pytest.mark.anyio
async def test_cli_writes_only_the_run_record_for_a_failed_run(tmp_path: Path) -> None:
    adapter = _adapter(
        {
            "ScopeCandidate": httpx.Response(
                429,
                json={"error": {"type": "insufficient_quota", "code": None, "message": "x"}},
            )
        },
        [],
    )
    store = LocalStore(tmp_path / "store")
    configuration, _ = _configuration()
    try:
        run = await run_assessment(
            POLICY_PDF,
            CHART_PDF,
            store=store,
            interpreter=OpenAIStageInterpreter(adapter),
            configuration=configuration,
        )
    finally:
        await adapter.close()

    assert run.status == RunStatus.FAILED
    written = write_outputs(store, run, tmp_path / "out")
    assert {path.name for path in written} == {"run.json"}


def test_main_requires_configuration_before_any_provider_contact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AIRA_MODEL", raising=False)
    constructed: list[object] = []
    monkeypatch.setattr(cli, "OpenAIAdapter", lambda *args, **kwargs: constructed.append(object()))
    exit_code = cli.main(
        [
            "assess",
            "--policy",
            str(POLICY_PDF),
            "--chart",
            str(CHART_PDF),
            "--data-dir",
            str(tmp_path / "data"),
            "--env-file",
            str(tmp_path / "missing.env"),
        ]
    )
    assert exit_code == 2
    assert constructed == []
    assert "Configure OPENAI_API_KEY and AIRA_MODEL" in capsys.readouterr().err
