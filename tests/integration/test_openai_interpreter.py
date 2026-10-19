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
from app.assessment.stages import (
    DocumentInputs,
    InterpretationFailure,
    StageInputs,
    render_stage_input,
)
from app.assessment.workflow import (
    WorkflowEngine,
    WorkflowLimits,
    workflow_parser_fingerprint,
)
from app.cli import run_assessment, write_outputs
from app.documents import NativePdfConfig, extract_pdf, inspect_pdf
from app.evidence import CitationResolver
from app.llm.config import OpenAISettings
from app.llm.interpreter import (
    OpenAIStageInterpreter,
    openai_configuration,
    prompt_reference,
)
from app.llm.openai_adapter import OpenAIAdapter
from app.llm.prompts import PROMPTS
from app.policies import convert_chart, convert_policy
from app.schemas import (
    ApplicabilityStatus,
    AssessmentExport,
    AssessmentOutcome,
    ChartCandidate,
    ConfigurationProvenance,
    CreateAssessmentRequest,
    DocumentRecord,
    DocumentRole,
    ErrorCode,
    ExtractionRecord,
    ModelProvider,
    PolicyCandidate,
    RequestField,
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
    base = StageInputs(
        sources["policy"][0], sources["chart"][0], sources["policy"][1], sources["chart"][1]
    )
    policy = convert_policy(
        PolicyCandidate.model_validate_json(json.dumps(_policy_candidate(POLICY_ID))),
        CitationResolver((base.policy_document,), (base.policy_extraction,)),
        policy_id="saved-policy",
    )
    chart_candidate = _evidence_candidate(CHART_ID)
    chart = convert_chart(
        ChartCandidate.model_validate_json(
            json.dumps(
                {
                    "schema_version": "0.1.0",
                    "facts": chart_candidate["facts"],
                    "interpretation_issues": [],
                }
            )
        ),
        CitationResolver((base.chart_document,), (base.chart_extraction,)),
        document_sha256=base.chart_document.sha256,
    )
    return replace(base, policy=policy, chart=chart)


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


def _adapter(
    bodies: dict[str, _Body], requests: list[httpx.Request], *, transport="responses"
) -> OpenAIAdapter:
    """Adapter over the real SDK; bodies are keyed by strict schema name."""

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        payload = json.loads(request.content)
        name = (
            payload["text"]["format"]["name"]
            if transport == "responses"
            else payload["response_format"]["json_schema"]["name"]
        )
        source_text = (
            payload["input"] if transport == "responses" else payload["messages"][-1]["content"]
        )
        packet = json.loads(source_text)
        if name in bodies:
            body = bodies[name]
        elif name == "SectionCandidate":
            units = packet["primary"]
            matching = [unit for unit in units if POLICY_CRITERION_QUOTE[1] in unit["text"]]
            document_id = packet["document_id"]
            fragment = _policy_candidate(document_id) if matching else None
            body = dict(
                schema_version="0.1.0",
                fragment=fragment,
                definitions=[],
                dependencies=[],
                issues=[],
                dispositions=[
                    dict(
                        unit_id=unit["unit_id"],
                        kind="requirements" if unit in matching else "context",
                        explanation="Scripted full-block classification.",
                    )
                    for unit in units
                ],
            )
        elif name == "ReconciliationCandidate":
            policies = [
                (item["section_id"], item["policy"])
                for item in packet["sections"]
                if item["policy"]
            ]
            body = dict(
                schema_version="0.1.0",
                nodes=[],
                resolutions=[],
                issues=[],
                paths=[
                    dict(
                        path_id="scripted",
                        title="Scripted procedure",
                        scope="Scripted scope",
                        root_id=policy["root_id"],
                        citations=policy["citations"],
                    )
                    for _, policy in policies
                ],
            )
        elif name == "AuditCandidate":
            body = dict(
                schema_version="0.1.0",
                checked_unit_ids=[item["unit_id"] for item in packet["source"]["primary"]],
                missing_conditions=[],
                issues=[],
            )
        elif name == "PagePlanCandidate":
            body = {"schema_version": "0.1.0", "pages": []}
        elif name == "ChartCandidate":
            document_id = packet["documents"][0]["document_id"]
            evidence = _evidence_candidate(str(document_id))
            body = {
                "schema_version": "0.1.0",
                "facts": evidence["facts"],
                "interpretation_issues": [],
            }
        elif name == "FindingsCandidate":
            findings = _evidence_candidate(CHART_ID)["findings"]
            for item in findings:
                item["criterion_id"] = packet["criteria"][0]["criterion_id"]
            body = {"schema_version": "0.1.0", "findings": findings}
        else:
            body = bodies[name]
        if isinstance(body, httpx.Response):
            return body
        if callable(body):
            body = body(packet)
        return httpx.Response(
            200,
            json=_envelope(json.dumps(body), f"resp-{name}")
            if transport == "responses"
            else {
                "id": f"resp-{name}",
                "object": "chat.completion",
                "created": 1,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": json.dumps(body)},
                    }
                ],
                "usage": {"prompt_tokens": 31, "completion_tokens": 9, "total_tokens": 40},
            },
            headers={"x-request-id": f"req-{name}"},
        )

    settings = _settings().model_copy(
        update={
            "transport": transport,
            "backend": "openai" if transport == "responses" else "litellm",
            "base_url": "https://api.openai.com/v1"
            if transport == "responses"
            else "http://127.0.0.1:4000/v1",
        }
    )
    client = AsyncOpenAI(
        api_key="test-key-not-real",
        base_url=settings.base_url,
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
    )
    return OpenAIAdapter(settings, client=client)


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
        chart = await interpreter.chart(
            DocumentInputs(inputs.chart_document, inputs.chart_extraction)
        )
        interpreted_evidence = await interpreter.evidence(
            replace(inputs, policy=interpreted_policy.policy, chart=chart.chart),
            interpreted_policy.policy,
        )
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

    evidence_request = next(
        item
        for item in requests
        if json.loads(item.content)["text"]["format"]["name"] == "FindingsCandidate"
    )
    packet = json.loads(json.loads(evidence_request.content)["input"])
    assert [item["criterion_id"] for item in packet["criteria"]] == ["telangiectasia-cosmetic"]
    facts = interpreted_evidence.facts
    findings = interpreted_evidence.findings
    assert len(facts) == 1 and facts[0].sources[0].page == CHART_FACT_QUOTE[0]
    assert [finding.status.value for finding in findings] == ["met"]
    assert findings[0].evidence[0].fact_id == facts[0].fact_id


@pytest.mark.anyio
async def test_one_invalid_scope_candidate_is_repaired_once(inputs: StageInputs) -> None:
    calls = {"n": 0}
    valid = _scope_candidate(POLICY_ID, CHART_ID, "mismatch")
    invalid = _scope_candidate(POLICY_ID, CHART_ID, "mismatch", corrupt=True)

    def sequenced(_packet: dict[str, object]) -> dict[str, object]:
        calls["n"] += 1
        return invalid if calls["n"] == 1 else valid

    requests: list[httpx.Request] = []
    adapter = _adapter({"ScopeCandidate": sequenced}, requests)
    interpreter = OpenAIStageInterpreter(adapter)
    try:
        interpreted = await interpreter.scope(inputs)
    finally:
        await adapter.close()

    assert interpreted.applicability.status == ApplicabilityStatus.MISMATCH
    assert interpreted.usage is not None and interpreted.usage.attempts == 2
    assert len(requests) == 2
    first = json.loads(requests[0].content)
    second = json.loads(requests[1].content)
    assert "Validation failure" not in first["instructions"]
    assert "Validation failure" in second["instructions"]
    assert "citation_invalid" in second["instructions"]


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
    assert usage.attempts == 2 and usage.input_tokens == 62
    assert error.value.error.retryable is True


@pytest.mark.anyio
async def test_an_uncited_request_field_is_dropped_and_a_cited_mismatch_stands(
    inputs: StageInputs,
) -> None:
    """A cited mismatch is not an operational failure when field quotes are absent.

    The values are removed and named for staff. Scope quotes are not copied onto
    them, and the stage does not spend a repair call.
    """
    candidate = _scope_candidate(POLICY_ID, CHART_ID, "mismatch")
    candidate["field_sources"] = []
    adapter = _adapter({"ScopeCandidate": candidate}, [])
    interpreter = OpenAIStageInterpreter(adapter)
    try:
        interpreted = await interpreter.scope(inputs)
    finally:
        await adapter.close()

    assert interpreted.applicability.status == ApplicabilityStatus.MISMATCH
    assert interpreted.request.procedure is None
    assert interpreted.request.payer is None
    assert interpreted.request.plan is None
    assert set(interpreted.request.unresolved_fields) == {
        RequestField.PROCEDURE,
        RequestField.PAYER,
        RequestField.PLAN,
    }
    assert interpreted.usage is not None and interpreted.usage.attempts == 1


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
        "policy_index",
        "policy_page",
        "policy_section",
        "policy_reconcile",
        "policy_merge",
        "policy_audit",
        "chart",
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
        {
            "ScopeCandidate": _scope_candidate(POLICY_ID, CHART_ID, "mismatch"),
            "PolicyCandidate": _policy_candidate(POLICY_ID),
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
    assert run.result.outcome == AssessmentOutcome.APPLICABILITY_MISMATCH
    scope_usage = [usage for usage in run.usage if usage.phase == RunPhase.CHECKING_APPLICABILITY]
    assert len(scope_usage) == 1
    assert scope_usage[0].model_id == "test-model"
    assert scope_usage[0].input_tokens == 31
    names = [json.loads(item.content)["text"]["format"]["name"] for item in requests]
    assert names[0] == "SectionCandidate"
    assert "ReconciliationCandidate" in names
    assert "AuditCandidate" in names
    assert "ScopeCandidate" in names


@pytest.mark.anyio
@pytest.mark.parametrize("transport", ["responses", "chat_completions"])
async def test_workflow_runs_the_full_applicable_path(store: LocalStore, transport) -> None:
    requests: list[httpx.Request] = []
    adapter = _adapter(
        {
            "ScopeCandidate": _scope_candidate(POLICY_ID, CHART_ID, "applicable"),
            "PolicyCandidate": _policy_candidate(POLICY_ID),
            "EvidenceCandidate": _evidence_candidate(CHART_ID),
        },
        requests,
        transport=transport,
    )
    _, limits = _configuration()
    configuration = openai_configuration(
        adapter.settings, workflow_parser_fingerprint(NativePdfConfig(), limits)
    )
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
    names = [
        json.loads(item.content)["text"]["format"]["name"]
        if transport == "responses"
        else json.loads(item.content)["response_format"]["json_schema"]["name"]
        for item in requests
    ]
    assert all(str(item.url).startswith(adapter.settings.base_url) for item in requests)
    assert all(item.headers["authorization"] == "Bearer test-key-not-real" for item in requests)
    assert "SectionCandidate" in names
    assert "ReconciliationCandidate" in names
    assert "AuditCandidate" in names
    assert "ChartCandidate" in names
    assert "FindingsCandidate" in names
    interpreted = {
        usage.phase for usage in run.usage if usage.model_id == "test-model" and usage.attempts >= 1
    }
    assert {
        RunPhase.CHECKING_APPLICABILITY,
        RunPhase.INTERPRETING_POLICY,
        RunPhase.EXTRACTING_CHART,
        RunPhase.MAPPING_EVIDENCE,
    } <= interpreted


@pytest.mark.anyio
async def test_an_invented_evidence_quote_fails_after_policy_was_saved(
    store: LocalStore,
) -> None:
    requests: list[httpx.Request] = []
    adapter = _adapter(
        {
            "ScopeCandidate": _scope_candidate(POLICY_ID, CHART_ID, "applicable"),
            "PolicyCandidate": _policy_candidate(POLICY_ID),
            "ChartCandidate": {
                "schema_version": "0.1.0",
                "facts": _evidence_candidate(CHART_ID, corrupt=True)["facts"],
                "interpretation_issues": [],
            },
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

    assert run.status == RunStatus.FAILED
    assert run.error is not None
    assert run.error.code == ErrorCode.CITATION_INVALID
    assert run.error.stage == RunPhase.EXTRACTING_CHART
    connection = sqlite3.connect(store.database_path)
    try:
        saved = connection.execute(
            "SELECT phase FROM artifacts WHERE run_id=?", (run.run_id,)
        ).fetchall()
    finally:
        connection.close()
    assert RunPhase.INTERPRETING_POLICY.value in {str(phase) for (phase,) in saved}
    assert RunPhase.EXTRACTING_CHART.value not in {str(phase) for (phase,) in saved}


@pytest.mark.anyio
async def test_a_wrong_page_scope_quote_fails_as_citation_invalid(
    inputs: StageInputs,
) -> None:
    candidate = _scope_candidate(POLICY_ID, CHART_ID, "mismatch")
    candidate["citations"][1] = _citation(CHART_ID, (2, CHART_SCOPE_QUOTE[1]))
    adapter = _adapter({"ScopeCandidate": candidate}, [])
    interpreter = OpenAIStageInterpreter(adapter)
    try:
        with pytest.raises(InterpretationFailure) as error:
            await interpreter.scope(inputs)
    finally:
        await adapter.close()

    assert error.value.error.code == ErrorCode.CITATION_INVALID
    assert error.value.error.stage == RunPhase.CHECKING_APPLICABILITY
    assert error.value.error.retryable is True


@pytest.mark.anyio
async def test_a_wrong_document_citation_fails_as_citation_invalid(
    inputs: StageInputs,
) -> None:
    candidate = _scope_candidate(POLICY_ID, CHART_ID, "mismatch")
    candidate["field_sources"][0]["citations"] = [_citation(POLICY_ID, POLICY_SCOPE_QUOTE)]
    adapter = _adapter({"ScopeCandidate": candidate}, [])
    interpreter = OpenAIStageInterpreter(adapter)
    try:
        with pytest.raises(InterpretationFailure) as error:
            await interpreter.scope(inputs)
    finally:
        await adapter.close()

    assert error.value.error.code == ErrorCode.CITATION_INVALID
    assert error.value.error.stage == RunPhase.CHECKING_APPLICABILITY


@pytest.mark.anyio
async def test_a_real_irrelevant_quote_fails_predicate_validation_and_is_not_satisfied(
    store: LocalStore,
) -> None:
    def findings_body(packet: dict[str, object]) -> dict[str, object]:
        return {
            "schema_version": "0.1.0",
            "findings": [
                {
                    "criterion_id": packet["criteria"][0]["criterion_id"],
                    "status": "met",
                    "rationale": "Model claims the vital sign entry satisfies the requirement.",
                    "evidence": [{"fact_id": "heart-rate", "relation": "supporting"}],
                    "unresolved_reasons": [],
                }
            ],
        }

    chart_candidate = {
        "schema_version": "0.1.0",
        "facts": [
            {
                "fact_id": "heart-rate",
                "proposition": "Heart rate entry.",
                "citations": [_citation(CHART_ID, CHART_FACT_QUOTE)],
                "polarity": "affirmed",
                "provenance": "direct",
                "value": None,
                "unit": None,
                "event_date": None,
                "documentation_date": None,
                "anatomical_target": None,
                "laterality": None,
                "context": ["vein"],
                "uncertainty": [],
                "conflicting_fact_ids": [],
            }
        ],
        "interpretation_issues": [],
    }

    def section_body(packet: dict[str, object]) -> dict[str, object]:
        units = packet["primary"]
        matching = [unit for unit in units if POLICY_CRITERION_QUOTE[1] in unit["text"]]
        document_id = packet["document_id"]
        policy = _policy_candidate(str(document_id))
        policy["criteria"][0]["context"] = ["vein"]
        fragment = policy if matching else None
        return dict(
            schema_version="0.1.0",
            fragment=fragment,
            definitions=[],
            dependencies=[],
            issues=[],
            dispositions=[
                dict(
                    unit_id=unit["unit_id"],
                    kind="requirements" if unit in matching else "context",
                    explanation="Scripted full-block classification.",
                )
                for unit in units
            ],
        )

    adapter = _adapter(
        {
            "ScopeCandidate": _scope_candidate(POLICY_ID, CHART_ID, "applicable"),
            "SectionCandidate": section_body,
            "PolicyCandidate": _policy_candidate(POLICY_ID),
            "ChartCandidate": chart_candidate,
            "FindingsCandidate": findings_body,
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

    assert run.status == RunStatus.COMPLETED
    assert run.result is not None
    finding = run.result.findings[0]
    assert finding.status.value == "needs_review"
    assert "unverified_required_context" in finding.unresolved_reasons
    assert run.result.outcome != AssessmentOutcome.DOCUMENTED_REQUIREMENTS_SATISFIED


@pytest.mark.anyio
async def test_cli_run_writes_run_export_and_checklist(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def scope_body(packet: dict[str, object]) -> dict[str, object]:
        if "documents" in packet:
            ids = {item["role"]: item["document_id"] for item in packet["documents"]}
        else:
            ids = {
                "policy": packet["policy"]["document_id"],
                "chart": packet["chart"]["document_id"],
            }
        return _scope_candidate(str(ids["policy"]), str(ids["chart"]), "mismatch")

    def policy_body(packet: dict[str, object]) -> dict[str, object]:
        document_id = packet.get("document_id")
        documents = packet.get("documents")
        if not document_id and isinstance(documents, list) and documents:
            first = documents[0]
            document_id = first.get("document_id") if isinstance(first, dict) else None
        return _policy_candidate(str(document_id))

    adapter = _adapter({"ScopeCandidate": scope_body, "PolicyCandidate": policy_body}, requests)
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
    def policy_body(packet: dict[str, object]) -> dict[str, object]:
        documents = packet["documents"]
        policy_id = documents[0]["document_id"] if isinstance(documents, list) else ""
        return _policy_candidate(str(policy_id))

    adapter = _adapter(
        {
            "PolicyCandidate": policy_body,
            "ScopeCandidate": httpx.Response(
                429,
                json={"error": {"type": "insufficient_quota", "code": None, "message": "x"}},
            ),
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


@pytest.mark.anyio
async def test_chat_transport_keeps_extraction_inputs_and_credentials_isolated(
    tmp_path: Path, inputs: StageInputs
) -> None:
    secret = "sk-isolation-test-key"
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = json.loads(request.content)
        name = body["response_format"]["json_schema"]["name"]
        if name == "PolicyCandidate":
            text = json.dumps(_policy_candidate(POLICY_ID))
        else:
            chart = _evidence_candidate(CHART_ID)
            text = json.dumps(
                {
                    "schema_version": "0.1.0",
                    "facts": chart["facts"],
                    "interpretation_issues": [],
                }
            )
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl_isolation",
                "object": "chat.completion",
                "created": 1,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": text, "refusal": None},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 31, "completion_tokens": 9, "total_tokens": 40},
            },
        )

    client = AsyncOpenAI(
        api_key=secret,
        base_url="https://api.openai.com/v1",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
    )
    adapter = OpenAIAdapter(
        OpenAISettings(api_key=SecretStr(secret), model="test-model", transport="chat_completions"),
        client=client,
    )
    interpreter = OpenAIStageInterpreter(adapter)
    try:
        policy = await interpreter.policy(
            DocumentInputs(inputs.policy_document, inputs.policy_extraction)
        )
        chart = await interpreter.chart(
            DocumentInputs(inputs.chart_document, inputs.chart_extraction)
        )
    finally:
        await adapter.close()

    assert [
        json.loads(item.content)["response_format"]["json_schema"]["name"] for item in requests
    ] == [
        "PolicyCandidate",
        "ChartCandidate",
    ]
    for request in requests:
        raw = request.content.decode()
        assert secret not in raw
        assert request.headers["authorization"] == f"Bearer {secret}"
        packet = json.loads(json.loads(raw)["messages"][1]["content"])
        assert packet["input_kind"] == "pdf_text_blocks"
        assert len(packet["documents"]) == 1
        assert "selected_request" not in packet
        assert "staff_annotations" not in packet
    policy_packet = json.loads(json.loads(requests[0].content)["messages"][1]["content"])
    chart_packet = json.loads(json.loads(requests[1].content)["messages"][1]["content"])
    assert policy_packet["documents"][0]["document_id"] == POLICY_ID
    assert chart_packet["documents"][0]["document_id"] == CHART_ID
    assert CHART_ID not in requests[0].content.decode()
    assert POLICY_ID not in requests[1].content.decode()

    store = LocalStore(tmp_path / "store")
    store.put_document(inputs.policy_document, POLICY_PDF.read_bytes())
    store.put_extraction(inputs.policy_extraction)
    store.put_document(inputs.chart_document, CHART_PDF.read_bytes())
    store.put_extraction(inputs.chart_extraction)
    configuration, _ = _configuration()
    store.put_policy_rule_set(
        inputs.policy_document,
        inputs.policy_extraction,
        policy.policy,
        configuration=configuration,
    )
    store.put_chart_interpretation(
        inputs.chart_document,
        inputs.chart_extraction,
        chart.chart,
        configuration=configuration,
    )
    saved = "\n".join(
        path.read_text(errors="ignore") for path in store.root.rglob("*") if path.is_file()
    )
    assert secret not in saved


@pytest.mark.anyio
@pytest.mark.parametrize("transport", ["responses", "chat_completions"])
async def test_group_merge_uses_the_same_selected_connection(inputs, transport):
    from app.schemas.builds import ReconciliationCandidate, ReconciliationGroup

    candidate = dict(
        schema_version="0.1.0",
        nodes=[],
        resolutions=[],
        issues=[],
        paths=[
            dict(
                path_id="scripted",
                title="Scripted scope",
                scope="Scripted procedure",
                root_id="root",
                citations=[_citation(POLICY_ID, POLICY_CRITERION_QUOTE)],
            )
        ],
    )
    group = ReconciliationGroup(
        group_id="group-1",
        section_ids=("section-1",),
        result=ReconciliationCandidate.model_validate_json(json.dumps(candidate)),
    )
    requests = []
    adapter = _adapter({"ReconciliationCandidate": candidate}, requests, transport=transport)
    try:
        result = await OpenAIStageInterpreter(adapter).merge(
            DocumentInputs(inputs.policy_document, inputs.policy_extraction), (group,), ()
        )
    finally:
        await adapter.close()
    assert result.value.paths[0].path_id == "scripted"
    assert len(requests) == 1
    assert str(requests[0].url) == adapter.settings.base_url + (
        "/responses" if transport == "responses" else "/chat/completions"
    )
    assert requests[0].headers["authorization"] == "Bearer test-key-not-real"
    body = json.loads(requests[0].content)
    packet = json.loads(
        body["input"] if transport == "responses" else body["messages"][-1]["content"]
    )
    assert "groups" in packet and "chart" not in packet and "selected_request" not in packet
