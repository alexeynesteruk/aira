"""Workflow runs over the real engine, parser output, and store with a scripted interpreter.

ControlledInterpreter is a test double for StageInterpreter: it resolves its
scripted quotes through a CitationResolver on the run's real extractions, so its
domain records carry source-valid spans unless a test scripts corruption. This
is controlled orchestration evidence — it makes no provider calls and asserts
nothing about live-model accuracy.
"""

import asyncio
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.assessment import EvaluationResult, evaluate_policy
from app.assessment.stage_input import render_stage_input
from app.assessment.workflow import (
    _VALIDATION_VERSION,
    EvidenceArtifact,
    EvidenceInterpretation,
    InterpretationFailure,
    PolicyInterpretation,
    ScopeArtifact,
    ScopeInterpretation,
    StageInputs,
    WorkflowAdmissionError,
    WorkflowEngine,
    WorkflowLimits,
    workflow_parser_fingerprint,
)
from app.documents import NativePdfConfig, extract_pdf, inspect_pdf
from app.documents.native import PARSER_VERSION
from app.evidence import CitationResolver
from app.schemas import (
    ApplicabilityResult,
    ApplicabilityStatus,
    AssessmentOutcome,
    CandidateCitation,
    ChartFact,
    ConfigurationProvenance,
    CreateAssessmentRequest,
    Criterion,
    CriterionNode,
    DocumentRecord,
    DocumentRole,
    ErrorCode,
    EvidenceReference,
    EvidenceRelation,
    EvidenceStatus,
    ExtractionRecord,
    FactPolarity,
    Finding,
    InferenceSettings,
    NarrativePredicate,
    OperationalError,
    Policy,
    PolicySection,
    RequestContext,
    RequestField,
    RunPhase,
    RunStatus,
    SourceSpan,
    StageUsage,
    TextAnnotation,
    VersionReference,
)
from app.storage import LocalStore, StorageReferenceError

ROOT = Path(__file__).resolve().parents[2]
POLICY_PDF = ROOT / "examples/guidelines/bcbs_fl_02-33000-31_2025-08-15.pdf"
CHART_PDF = ROOT / "examples/charts/robert_mitchell_chart_final.pdf"
IMAGE_ONLY_PDF = ROOT / "tests/fixtures/pdf/image-only.pdf"
CREATED_AT = datetime(2026, 10, 18, tzinfo=UTC)

# Quotes are exact native-text passages, each unique on its page.
POLICY_SCOPE_QUOTE = (1, "Subject: Treatments for Varicose Veins/Venous")
CHART_SCOPE_QUOTE = (1, "PATIENT MEDICAL CHART")
POLICY_CRITERION_QUOTE = (3, "Treatment of telangiectasia such as spider veins")
CHART_FACT_QUOTE = (3, "HR: 44 bpm, regular")


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
        "policy": _parse(POLICY_PDF, DocumentRole.POLICY, "policy-doc"),
        "chart": _parse(CHART_PDF, DocumentRole.CHART, "chart-doc"),
    }


@pytest.fixture
def store(
    tmp_path: Path, sources: dict[str, tuple[DocumentRecord, ExtractionRecord, bytes]]
) -> LocalStore:
    store = LocalStore(tmp_path / "store")
    for record, extraction, raw in sources.values():
        store.put_document(record, raw)
        store.put_extraction(extraction)
    return store


def _configuration(limits: WorkflowLimits | None = None) -> ConfigurationProvenance:
    return ConfigurationProvenance(
        parser=VersionReference(name="pdfplumber", version=PARSER_VERSION),
        parser_configuration_sha256=workflow_parser_fingerprint(
            NativePdfConfig(), limits or WorkflowLimits()
        ),
        prompts=(VersionReference(name="controlled", version="1"),),
        model_id="controlled-interpreter",
        sdk_version="test-harness",
        inference=InferenceSettings(max_output_tokens=4096),
    )


def _submission(**changes: object) -> CreateAssessmentRequest:
    return CreateAssessmentRequest(
        **{"policy_document_id": "policy-doc", "chart_document_id": "chart-doc", **changes}
    )


async def _started(
    store: LocalStore, interpreter: "ControlledInterpreter", limits: WorkflowLimits | None = None
) -> WorkflowEngine:
    engine = WorkflowEngine(store, interpreter, _configuration(limits), limits=limits)
    await engine.start()
    return engine


async def _until(predicate: Callable[[], bool], message: str) -> None:
    for _ in range(400):
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError(message)


def _resolver(inputs: StageInputs) -> CitationResolver:
    return CitationResolver(
        (inputs.policy_document, inputs.chart_document),
        (inputs.policy_extraction, inputs.chart_extraction),
    )


def _quote(inputs: StageInputs, document: DocumentRecord, page: int, quote: str) -> SourceSpan:
    return _resolver(inputs).resolve(
        CandidateCitation(document_id=document.document_id, page=page, quote=quote)
    )


def _corrupted(span: SourceSpan) -> SourceSpan:
    return span.model_copy(update={"excerpt": "corrupted excerpt"})


class ControlledInterpreter:
    """Scriptable test StageInterpreter producing source-valid domain records."""

    def __init__(
        self,
        *,
        scope_status: ApplicabilityStatus = ApplicabilityStatus.MISMATCH,
        unresolved_fields: tuple[RequestField, ...] = (),
        missing_finding: bool = False,
        failure: InterpretationFailure | None = None,
        failing_stage: RunPhase | None = None,
        corrupt_stage: RunPhase | None = None,
        sleep: float | None = None,
        gate: asyncio.Event | None = None,
    ) -> None:
        self.calls = {"scope": 0, "policy": 0, "evidence": 0}
        self.scope_status = scope_status
        self.unresolved_fields = unresolved_fields
        self.missing_finding = missing_finding
        self.failure = failure
        self.failing_stage = failing_stage
        self.corrupt_stage = corrupt_stage
        self.sleep = sleep
        self.gate = gate

    async def _enter(self, stage: str, phase: RunPhase) -> None:
        self.calls[stage] += 1
        if self.gate is not None:
            await self.gate.wait()
        if self.sleep is not None:
            await asyncio.sleep(self.sleep)
        if self.failing_stage == phase and self.failure is not None:
            raise self.failure

    async def scope(self, inputs: StageInputs) -> ScopeInterpretation:
        await self._enter("scope", RunPhase.CHECKING_APPLICABILITY)
        policy_span = _quote(inputs, inputs.policy_document, *POLICY_SCOPE_QUOTE)
        chart_span = _quote(inputs, inputs.chart_document, *CHART_SCOPE_QUOTE)
        if self.corrupt_stage == RunPhase.CHECKING_APPLICABILITY:
            policy_span = _corrupted(policy_span)
        if self.scope_status == ApplicabilityStatus.UNRESOLVED:
            applicability = ApplicabilityResult(
                status=ApplicabilityStatus.UNRESOLVED,
                rationale="The submitted request cannot be resolved from the cited records.",
                sources=(),
                unresolved_fields=self.unresolved_fields,
            )
        else:
            applicability = ApplicabilityResult(
                status=self.scope_status,
                rationale="A scripted scope judgment citing both source documents.",
                sources=(policy_span, chart_span),
            )
        return ScopeInterpretation(
            request=RequestContext(
                procedure="endovenous vein ablation",
                payer="Fixture payer",
                unresolved_fields=self.unresolved_fields,
            ),
            applicability=applicability,
        )

    async def policy(self, inputs: StageInputs) -> PolicyInterpretation:
        await self._enter("policy", RunPhase.INTERPRETING_POLICY)
        span = _quote(inputs, inputs.policy_document, *POLICY_CRITERION_QUOTE)
        if self.corrupt_stage == RunPhase.INTERPRETING_POLICY:
            span = _corrupted(span)
        criterion = Criterion(
            criterion_id="criterion-telangiectasia",
            wording="Treatment of telangiectasia is considered cosmetic.",
            interpretation="The scripted criterion reuses a cited governing sentence.",
            sources=(span,),
            predicate=NarrativePredicate(
                question="Does the chart document the scripted requirement?"
            ),
        )
        return PolicyInterpretation(
            policy=Policy(
                policy_id="controlled-policy",
                document_id=inputs.policy_document.document_id,
                document_sha256=inputs.policy_document.sha256,
                title="Controlled policy",
                scope_summary="Scripted scope summary for the controlled interpreter.",
                criteria=(criterion,),
                nodes=(
                    CriterionNode(
                        node_id="root",
                        criterion_id=criterion.criterion_id,
                        sources=(span,),
                    ),
                ),
                root_id="root",
                sections=(
                    PolicySection(
                        section_id="requirements",
                        heading="Scripted requirements",
                        sources=(span,),
                        disposition="requirements",
                        criterion_ids=(criterion.criterion_id,),
                        explanation="The single scripted criterion is a requirement.",
                    ),
                ),
            )
        )

    async def evidence(self, inputs: StageInputs, policy: Policy) -> EvidenceInterpretation:
        await self._enter("evidence", RunPhase.MAPPING_EVIDENCE)
        span = _quote(inputs, inputs.chart_document, *CHART_FACT_QUOTE)
        if self.corrupt_stage == RunPhase.MAPPING_EVIDENCE:
            span = _corrupted(span)
        fact = ChartFact(
            fact_id="fact-heart-rate",
            proposition="The chart documents a resting heart rate of 44 bpm.",
            sources=(span,),
            polarity=FactPolarity.AFFIRMED,
        )
        findings = tuple(
            Finding(
                criterion_id=criterion.criterion_id,
                status=(EvidenceStatus.MISSING if self.missing_finding else EvidenceStatus.MET),
                rationale=(
                    "The chart does not document the scripted requirement."
                    if self.missing_finding
                    else "The cited measurement satisfies the scripted requirement."
                ),
                evidence=()
                if self.missing_finding
                else (
                    EvidenceReference(fact_id=fact.fact_id, relation=EvidenceRelation.SUPPORTING),
                ),
                unresolved_reasons=("No supporting documentation was cited.",)
                if self.missing_finding
                else (),
            )
            for criterion in policy.criteria
        )
        return EvidenceInterpretation(facts=(fact,), findings=findings)


@pytest.mark.anyio
async def test_supplied_pair_completes_as_mismatch_under_default_limits(
    store: LocalStore,
    sources: dict[str, tuple[DocumentRecord, ExtractionRecord, bytes]],
) -> None:
    """A01 regression: the rendered scope input fits the default context guardrail."""
    policy_document, policy_extraction, _ = sources["policy"]
    chart_document, chart_extraction, _ = sources["chart"]
    inputs = StageInputs(policy_document, chart_document, policy_extraction, chart_extraction)
    rendered_scope = len(render_stage_input(inputs, "scope"))
    assert 0 < rendered_scope < WorkflowLimits().max_context_characters

    interpreter = ControlledInterpreter()
    engine = await _started(store, interpreter)
    try:
        run = await engine.wait((await engine.submit(_submission())).run_id)
    finally:
        await engine.close()

    assert run.status == RunStatus.COMPLETED
    assert run.result is not None
    assert run.result.outcome == AssessmentOutcome.APPLICABILITY_MISMATCH
    assert run.result.policy is None
    assert run.result.findings == ()
    assert interpreter.calls == {"scope": 1, "policy": 0, "evidence": 0}
    assert run.progress.completed_phases == (
        RunPhase.EXTRACTING,
        RunPhase.CHECKING_APPLICABILITY,
    )


@pytest.mark.anyio
async def test_unresolved_scope_requests_named_input_and_stops(store: LocalStore) -> None:
    interpreter = ControlledInterpreter(
        scope_status=ApplicabilityStatus.UNRESOLVED,
        unresolved_fields=(RequestField.PLAN,),
    )
    engine = await _started(store, interpreter)
    try:
        run = await engine.wait((await engine.submit(_submission())).run_id)
    finally:
        await engine.close()

    assert run.status == RunStatus.NEEDS_INPUT
    assert run.applicability is not None
    assert run.applicability.unresolved_fields == (RequestField.PLAN,)
    assert run.result is None
    assert interpreter.calls == {"scope": 1, "policy": 0, "evidence": 0}


@pytest.mark.anyio
@pytest.mark.parametrize("missing_finding", [False, True])
async def test_applicable_run_completes_every_phase_with_persisted_evaluation(
    store: LocalStore, missing_finding: bool
) -> None:
    interpreter = ControlledInterpreter(
        scope_status=ApplicabilityStatus.APPLICABLE, missing_finding=missing_finding
    )
    engine = await _started(store, interpreter)
    try:
        run = await engine.wait((await engine.submit(_submission())).run_id)
    finally:
        await engine.close()

    assert run.status == RunStatus.COMPLETED
    assert run.progress.completed_phases == tuple(RunPhase)
    assert interpreter.calls == {"scope": 1, "policy": 1, "evidence": 1}
    interpreted = {
        usage.phase: usage
        for usage in run.usage
        if usage.phase
        in {
            RunPhase.CHECKING_APPLICABILITY,
            RunPhase.INTERPRETING_POLICY,
            RunPhase.MAPPING_EVIDENCE,
        }
    }
    assert len(interpreted) == 3
    assert all(usage.attempts >= 1 for usage in interpreted.values())

    result = run.result
    assert result is not None and result.policy is not None
    expected = evaluate_policy(result.policy, result.findings, result.applicability, result.issues)
    assert result.outcome == expected.outcome
    assert result.logical_value == expected.logical_value
    assert result.outcome == (
        AssessmentOutcome.DOCUMENTATION_GAPS_OR_CONTRARY_EVIDENCE
        if missing_finding
        else AssessmentOutcome.DOCUMENTED_REQUIREMENTS_SATISFIED
    )

    # Artifact keys bind the run's request_context as it stood at publish time;
    # the finished run's record holds the scope-resolved request, so look the
    # persisted phase artifacts up by identity instead of recomputing keys.
    phases = {
        RunPhase.CHECKING_APPLICABILITY: ScopeArtifact,
        RunPhase.INTERPRETING_POLICY: Policy,
        RunPhase.MAPPING_EVIDENCE: EvidenceArtifact,
        RunPhase.EVALUATING: EvaluationResult,
    }
    connection = sqlite3.connect(store.database_path)
    try:
        rows = connection.execute(
            "SELECT phase, artifact_id FROM artifacts WHERE run_id=?", (run.run_id,)
        ).fetchall()
    finally:
        connection.close()
    by_phase = {RunPhase(str(phase)): str(artifact_id) for phase, artifact_id in rows}
    assert set(by_phase) == set(phases)
    evaluation = store.get_artifact(by_phase[RunPhase.EVALUATING], EvaluationResult)
    assert evaluation.value.outcome == result.outcome


@pytest.mark.anyio
async def test_a_corrupted_citation_fails_without_publishing_the_stage(
    store: LocalStore,
) -> None:
    interpreter = ControlledInterpreter(corrupt_stage=RunPhase.CHECKING_APPLICABILITY)
    engine = await _started(store, interpreter)
    try:
        run = await engine.wait((await engine.submit(_submission())).run_id)
    finally:
        await engine.close()

    assert run.status == RunStatus.FAILED
    assert run.error is not None
    assert run.error.code == ErrorCode.CITATION_INVALID
    assert run.error.stage == RunPhase.CHECKING_APPLICABILITY
    assert run.result is None
    extraction_ids = tuple(
        extraction.extraction_id
        for extraction in (
            store.list_extractions("policy-doc")[0],
            store.list_extractions("chart-doc")[0],
        )
    )
    assert (
        store.find_artifact(
            run.run_id,
            RunPhase.CHECKING_APPLICABILITY,
            ScopeArtifact,
            extraction_ids=extraction_ids,
            validation_version=_VALIDATION_VERSION,
        )
        is None
    )


@pytest.mark.anyio
async def test_interpreter_failure_carries_its_error_and_usage(store: LocalStore) -> None:
    failure = InterpretationFailure(
        OperationalError(
            code=ErrorCode.THROTTLED,
            message="Controlled provider throttle.",
            retryable=True,
            action="Retry the assessment later.",
        ),
        usage=StageUsage(
            phase=RunPhase.CHECKING_APPLICABILITY,
            attempts=3,
            duration_ms=12.0,
            input_tokens=100,
            output_tokens=25,
        ),
    )
    interpreter = ControlledInterpreter(
        failure=failure, failing_stage=RunPhase.CHECKING_APPLICABILITY
    )
    engine = await _started(store, interpreter)
    try:
        run = await engine.wait((await engine.submit(_submission())).run_id)
    finally:
        await engine.close()

    assert run.status == RunStatus.FAILED
    assert run.error is not None
    assert run.error.code == ErrorCode.THROTTLED
    assert run.error.retryable is True
    assert run.error.stage == RunPhase.CHECKING_APPLICABILITY
    recorded = run.usage[-1]
    assert recorded.phase == RunPhase.CHECKING_APPLICABILITY
    assert (recorded.attempts, recorded.input_tokens, recorded.output_tokens) == (3, 100, 25)


@pytest.mark.anyio
async def test_stage_timeout_fails_the_run_retryably(store: LocalStore) -> None:
    limits = WorkflowLimits(stage_timeout_seconds=0.05)
    interpreter = ControlledInterpreter(sleep=60)
    engine = await _started(store, interpreter, limits)
    try:
        run = await engine.wait((await engine.submit(_submission())).run_id)
    finally:
        await engine.close()

    assert run.status == RunStatus.FAILED
    assert run.error is not None
    assert run.error.code == ErrorCode.TIMEOUT
    assert run.error.retryable is True
    assert run.error.stage == RunPhase.CHECKING_APPLICABILITY


@pytest.mark.anyio
async def test_an_unusable_chart_fails_during_extraction(
    tmp_path: Path,
    sources: dict[str, tuple[DocumentRecord, ExtractionRecord, bytes]],
) -> None:
    store = LocalStore(tmp_path / "store")
    policy_document, policy_extraction, policy_raw = sources["policy"]
    store.put_document(policy_document, policy_raw)
    store.put_extraction(policy_extraction)
    raw = IMAGE_ONLY_PDF.read_bytes()
    store.put_document(
        inspect_pdf(
            raw,
            document_id="chart-image",
            filename="image-only.pdf",
            role=DocumentRole.CHART,
            created_at=CREATED_AT,
        ),
        raw,
    )
    interpreter = ControlledInterpreter()
    engine = await _started(store, interpreter)
    try:
        run = await engine.wait(
            (await engine.submit(_submission(chart_document_id="chart-image"))).run_id
        )
    finally:
        await engine.close()

    assert run.status == RunStatus.FAILED
    assert run.error is not None
    assert run.error.code == ErrorCode.EXTRACTION_FAILED
    assert run.error.stage == RunPhase.EXTRACTING
    assert interpreter.calls == {"scope": 0, "policy": 0, "evidence": 0}


@pytest.mark.anyio
async def test_a_tiny_context_limit_fails_before_interpretation(store: LocalStore) -> None:
    limits = WorkflowLimits(max_context_characters=200)
    interpreter = ControlledInterpreter()
    engine = await _started(store, interpreter, limits)
    try:
        run = await engine.wait((await engine.submit(_submission())).run_id)
    finally:
        await engine.close()

    assert run.status == RunStatus.FAILED
    assert run.error is not None
    assert run.error.code == ErrorCode.UNSUPPORTED_INPUT
    assert run.error.stage == RunPhase.CHECKING_APPLICABILITY
    assert interpreter.calls == {"scope": 0, "policy": 0, "evidence": 0}


@pytest.mark.anyio
async def test_a_saturated_queue_rejects_admission_retryably(store: LocalStore) -> None:
    gate = asyncio.Event()
    interpreter = ControlledInterpreter(gate=gate)
    engine = await _started(store, interpreter, WorkflowLimits(max_pending=1))
    try:
        first = await engine.submit(_submission())
        await _until(
            lambda: interpreter.calls["scope"] == 1,
            "the worker never reached the blocking interpreter",
        )
        second = await engine.submit(_submission())
        with pytest.raises(WorkflowAdmissionError) as error:
            await engine.submit(_submission())
        assert error.value.error.code == ErrorCode.QUEUE_FULL
        assert error.value.error.retryable is True
        gate.set()
        assert (await engine.wait(first.run_id)).status == RunStatus.COMPLETED
        assert (await engine.wait(second.run_id)).status == RunStatus.COMPLETED
    finally:
        gate.set()
        await engine.close()


@pytest.mark.anyio
async def test_admission_requires_a_running_engine(store: LocalStore) -> None:
    engine = WorkflowEngine(store, ControlledInterpreter(), _configuration())
    with pytest.raises(WorkflowAdmissionError) as cold:
        await engine.submit(_submission())
    assert cold.value.error.code == ErrorCode.CONFIGURATION_MISSING

    await engine.start()
    await engine.close()
    with pytest.raises(WorkflowAdmissionError) as closed:
        await engine.submit(_submission())
    assert closed.value.error.code == ErrorCode.CONFIGURATION_MISSING


@pytest.mark.anyio
async def test_submit_rejects_swapped_roles_without_creating_a_run(
    store: LocalStore,
) -> None:
    engine = await _started(store, ControlledInterpreter())
    try:
        with pytest.raises(StorageReferenceError):
            await engine.submit(
                CreateAssessmentRequest(
                    policy_document_id="chart-doc", chart_document_id="policy-doc"
                )
            )
    finally:
        await engine.close()

    connection = sqlite3.connect(store.database_path)
    try:
        runs = connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    finally:
        connection.close()
    assert runs == 0


@pytest.mark.anyio
async def test_restart_interrupts_a_run_blocked_in_the_interpreter(
    store: LocalStore,
) -> None:
    gate = asyncio.Event()
    interpreter = ControlledInterpreter(scope_status=ApplicabilityStatus.APPLICABLE, gate=gate)
    engine = await _started(store, interpreter)
    submitted = await engine.submit(_submission())
    await _until(
        lambda: interpreter.calls["scope"] == 1,
        "the run never reached the blocking interpreter",
    )
    await engine.close()

    run = store.get_run(submitted.run_id)
    assert run.status == RunStatus.INTERRUPTED
    assert run.error is not None
    assert run.error.code == ErrorCode.INTERRUPTED
    assert run.error.retryable is True
    assert run.phase == RunPhase.CHECKING_APPLICABILITY
    history = store.run_history(submitted.run_id)
    assert history[-1].status == RunStatus.INTERRUPTED
    assert [snapshot.status for snapshot in history[:2]] == [
        RunStatus.QUEUED,
        RunStatus.RUNNING,
    ]


@pytest.mark.anyio
async def test_a_clarification_submission_links_to_its_parent(store: LocalStore) -> None:
    engine = await _started(store, ControlledInterpreter())
    try:
        parent = await engine.wait((await engine.submit(_submission())).run_id)
        assert parent.status == RunStatus.COMPLETED
        annotation = TextAnnotation(
            annotation_id="staff-payer",
            field="payer",
            value="Staff recorded payer",
            created_at=CREATED_AT,
        )
        submitted = await engine.submit(
            _submission(parent_run_id=parent.run_id, annotations=(annotation,))
        )
        child = await engine.wait(submitted.run_id)
    finally:
        await engine.close()

    assert child.run_id != parent.run_id
    assert child.parent_run_id == parent.run_id
    assert child.input_fingerprint != parent.input_fingerprint
    assert child.status == RunStatus.COMPLETED
    assert store.get_run(parent.run_id) == parent


@pytest.mark.anyio
async def test_an_identical_submission_reuses_saved_work(store: LocalStore) -> None:
    interpreter = ControlledInterpreter(scope_status=ApplicabilityStatus.APPLICABLE)
    engine = await _started(store, interpreter)
    try:
        first = await engine.wait((await engine.submit(_submission())).run_id)
        assert interpreter.calls == {"scope": 1, "policy": 1, "evidence": 1}
        second = await engine.wait((await engine.submit(_submission())).run_id)
        assert interpreter.calls == {"scope": 1, "policy": 1, "evidence": 1}
        annotation = TextAnnotation(
            annotation_id="staff-plan",
            field="plan",
            value="Staff recorded plan",
            created_at=CREATED_AT,
        )
        third = await engine.wait(
            (await engine.submit(_submission(annotations=(annotation,)))).run_id
        )
    finally:
        await engine.close()

    assert first.status == second.status == third.status == RunStatus.COMPLETED
    assert len(store.list_extractions("policy-doc")) == 1
    assert len(store.list_extractions("chart-doc")) == 1
    cached = {usage.phase: usage for usage in second.usage}
    for phase in (
        RunPhase.CHECKING_APPLICABILITY,
        RunPhase.INTERPRETING_POLICY,
        RunPhase.MAPPING_EVIDENCE,
    ):
        assert cached[phase].attempts == 0
    # A changed annotation produces a different input fingerprint and misses cache.
    assert third.input_fingerprint != second.input_fingerprint
    assert interpreter.calls == {"scope": 2, "policy": 2, "evidence": 2}
