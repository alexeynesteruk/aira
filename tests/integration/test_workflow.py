"""Workflow runs over the real engine, parser output, and store with a scripted interpreter.

ControlledInterpreter and the shared helpers live in tests/support.py (imported
as ``support`` through the pytest pythonpath setting): it resolves its scripted
quotes through a CitationResolver on the run's real extractions, so its domain
records carry source-valid spans unless a test scripts corruption. This is
controlled orchestration evidence — it makes no provider calls and asserts
nothing about live-model accuracy.
"""

import asyncio
import sqlite3
from pathlib import Path

import pytest
from support import (
    CREATED_AT,
    ControlledInterpreter,
    configuration,
    parse_sources,
    started,
    submission,
    until,
)

from app.assessment import EvaluationResult, evaluate_policy
from app.assessment.stages import DocumentInputs, render_document_input
from app.assessment.workflow import (
    _VALIDATION_VERSION,
    EvidenceArtifact,
    InterpretationFailure,
    ScopeArtifact,
    WorkflowAdmissionError,
    WorkflowEngine,
    WorkflowLimits,
)
from app.documents import inspect_pdf
from app.schemas import (
    ApplicabilityStatus,
    AssessmentOutcome,
    ChartData,
    CreateAssessmentRequest,
    DocumentRecord,
    DocumentRole,
    ErrorCode,
    ExtractionRecord,
    OperationalError,
    Policy,
    RequestField,
    RunPhase,
    RunStatus,
    StageUsage,
    TextAnnotation,
)
from app.storage import LocalStore, StorageReferenceError


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
def sources() -> dict[str, tuple[DocumentRecord, ExtractionRecord, bytes]]:
    return parse_sources()


@pytest.fixture
def store(
    tmp_path: Path, sources: dict[str, tuple[DocumentRecord, ExtractionRecord, bytes]]
) -> LocalStore:
    store = LocalStore(tmp_path / "store")
    for record, extraction, raw in sources.values():
        store.put_document(record, raw)
        store.put_extraction(extraction)
    return store


@pytest.mark.anyio
async def test_supplied_pair_completes_as_mismatch_under_default_limits(
    store: LocalStore,
    sources: dict[str, tuple[DocumentRecord, ExtractionRecord, bytes]],
) -> None:
    """A01 regression: each whole-document extraction fits the default context guardrail."""
    policy_document, policy_extraction, _ = sources["policy"]
    chart_document, chart_extraction, _ = sources["chart"]
    rendered_policy = len(render_document_input(DocumentInputs(policy_document, policy_extraction)))
    rendered_chart = len(render_document_input(DocumentInputs(chart_document, chart_extraction)))
    assert 0 < rendered_policy < WorkflowLimits().max_context_characters
    assert 0 < rendered_chart < WorkflowLimits().max_context_characters

    interpreter = ControlledInterpreter()
    engine = await started(store, interpreter)
    try:
        run = await engine.wait((await engine.submit(submission())).run_id)
    finally:
        await engine.close()

    assert run.status == RunStatus.COMPLETED
    assert run.result is not None
    assert run.result.outcome == AssessmentOutcome.APPLICABILITY_MISMATCH
    assert run.result.policy is None
    assert run.result.findings == ()
    assert interpreter.calls == {"scope": 1, "policy": 1, "chart": 1, "evidence": 0}
    assert run.progress.completed_phases == (
        RunPhase.EXTRACTING,
        RunPhase.INTERPRETING_POLICY,
        RunPhase.EXTRACTING_CHART,
        RunPhase.CHECKING_APPLICABILITY,
    )
    assert len(store.list_policy_rule_sets()) == 1


@pytest.mark.anyio
async def test_unresolved_scope_requests_named_input_and_stops(store: LocalStore) -> None:
    interpreter = ControlledInterpreter(
        scope_status=ApplicabilityStatus.UNRESOLVED,
        unresolved_fields=(RequestField.PLAN,),
    )
    engine = await started(store, interpreter)
    try:
        run = await engine.wait((await engine.submit(submission())).run_id)
    finally:
        await engine.close()

    assert run.status == RunStatus.NEEDS_INPUT
    assert run.applicability is not None
    assert run.applicability.unresolved_fields == (RequestField.PLAN,)
    assert run.result is None
    assert interpreter.calls == {"scope": 1, "policy": 1, "chart": 1, "evidence": 0}


@pytest.mark.anyio
@pytest.mark.parametrize("missing_finding", [False, True])
async def test_applicable_run_completes_every_phase_with_persisted_evaluation(
    store: LocalStore, missing_finding: bool
) -> None:
    interpreter = ControlledInterpreter(
        scope_status=ApplicabilityStatus.APPLICABLE, missing_finding=missing_finding
    )
    engine = await started(store, interpreter)
    try:
        run = await engine.wait((await engine.submit(submission())).run_id)
    finally:
        await engine.close()

    assert run.status == RunStatus.COMPLETED
    assert run.progress.completed_phases == (
        RunPhase.EXTRACTING,
        RunPhase.INTERPRETING_POLICY,
        RunPhase.EXTRACTING_CHART,
        RunPhase.CHECKING_APPLICABILITY,
        RunPhase.MAPPING_EVIDENCE,
        RunPhase.VALIDATING,
        RunPhase.EVALUATING,
    )
    assert interpreter.calls == {"scope": 1, "policy": 1, "chart": 1, "evidence": 1}
    interpreted = {
        usage.phase: usage
        for usage in run.usage
        if usage.phase
        in {
            RunPhase.CHECKING_APPLICABILITY,
            RunPhase.INTERPRETING_POLICY,
            RunPhase.EXTRACTING_CHART,
            RunPhase.MAPPING_EVIDENCE,
        }
    }
    assert len(interpreted) == 4
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
        RunPhase.EXTRACTING_CHART: ChartData,
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
    # The run's saved evaluation carries the exact persisted artifact so the UI
    # and export can render OR-path states without re-evaluating.
    assert result.evaluation is not None
    assert result.evaluation == evaluation.value


@pytest.mark.anyio
async def test_a_corrupted_citation_fails_without_publishing_the_stage(
    store: LocalStore,
) -> None:
    interpreter = ControlledInterpreter(corrupt_stage=RunPhase.CHECKING_APPLICABILITY)
    engine = await started(store, interpreter)
    try:
        run = await engine.wait((await engine.submit(submission())).run_id)
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
    engine = await started(store, interpreter)
    try:
        run = await engine.wait((await engine.submit(submission())).run_id)
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
    limits = WorkflowLimits(stage_timeout_seconds=5)
    interpreter = ControlledInterpreter(sleep=60)
    engine = await started(store, interpreter, limits)
    try:
        run = await engine.wait((await engine.submit(submission())).run_id)
    finally:
        await engine.close()

    assert run.status == RunStatus.FAILED
    assert run.error is not None
    assert run.error.code == ErrorCode.TIMEOUT
    assert run.error.retryable is True
    assert run.error.stage == RunPhase.INTERPRETING_POLICY


@pytest.mark.anyio
async def test_an_unusable_chart_fails_during_extraction(
    tmp_path: Path,
    sources: dict[str, tuple[DocumentRecord, ExtractionRecord, bytes]],
) -> None:
    store = LocalStore(tmp_path / "store")
    policy_document, policy_extraction, policy_raw = sources["policy"]
    store.put_document(policy_document, policy_raw)
    store.put_extraction(policy_extraction)
    raw = Path(__file__).resolve().parents[2] / "tests/fixtures/pdf/vector-only.pdf"
    raw = raw.read_bytes()
    store.put_document(
        inspect_pdf(
            raw,
            document_id="chart-image",
            filename="vector-only.pdf",
            role=DocumentRole.CHART,
            created_at=CREATED_AT,
        ),
        raw,
    )
    interpreter = ControlledInterpreter()
    engine = await started(store, interpreter)
    try:
        run = await engine.wait(
            (await engine.submit(submission(chart_document_id="chart-image"))).run_id
        )
    finally:
        await engine.close()

    assert run.status == RunStatus.FAILED
    assert run.error is not None
    assert run.error.code == ErrorCode.EXTRACTION_FAILED
    assert run.error.stage == RunPhase.EXTRACTING
    assert interpreter.calls == {"scope": 0, "policy": 0, "chart": 0, "evidence": 0}


@pytest.mark.anyio
async def test_a_tiny_context_limit_fails_before_interpretation(store: LocalStore) -> None:
    limits = WorkflowLimits(max_context_characters=200)
    interpreter = ControlledInterpreter()
    engine = await started(store, interpreter, limits)
    try:
        run = await engine.wait((await engine.submit(submission())).run_id)
    finally:
        await engine.close()

    assert run.status == RunStatus.FAILED
    assert run.error is not None
    assert run.error.code == ErrorCode.UNSUPPORTED_INPUT
    assert run.error.stage == RunPhase.INTERPRETING_POLICY
    assert interpreter.calls == {"scope": 0, "policy": 0, "chart": 0, "evidence": 0}


@pytest.mark.anyio
async def test_a_saturated_queue_rejects_admission_retryably(store: LocalStore) -> None:
    gate = asyncio.Event()
    interpreter = ControlledInterpreter(gate=gate)
    engine = await started(store, interpreter, WorkflowLimits(max_pending=1))
    try:
        first = await engine.submit(submission())
        await until(
            lambda: interpreter.calls["policy"] == 1,
            "the worker never reached the blocking interpreter",
        )
        second = await engine.submit(submission())
        with pytest.raises(WorkflowAdmissionError) as error:
            await engine.submit(submission())
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
    engine = WorkflowEngine(store, ControlledInterpreter(), configuration())
    with pytest.raises(WorkflowAdmissionError) as cold:
        await engine.submit(submission())
    assert cold.value.error.code == ErrorCode.CONFIGURATION_MISSING

    await engine.start()
    await engine.close()
    with pytest.raises(WorkflowAdmissionError) as closed:
        await engine.submit(submission())
    assert closed.value.error.code == ErrorCode.CONFIGURATION_MISSING


@pytest.mark.anyio
async def test_submit_rejects_swapped_roles_without_creating_a_run(
    store: LocalStore,
) -> None:
    engine = await started(store, ControlledInterpreter())
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
    engine = await started(store, interpreter)
    submitted = await engine.submit(submission())
    await until(
        lambda: interpreter.calls["policy"] == 1,
        "the run never reached the blocking interpreter",
    )
    await engine.close()

    run = store.get_run(submitted.run_id)
    assert run.status == RunStatus.INTERRUPTED
    assert run.error is not None
    assert run.error.code == ErrorCode.INTERRUPTED
    assert run.error.retryable is True
    assert run.phase == RunPhase.INTERPRETING_POLICY
    history = store.run_history(submitted.run_id)
    assert history[-1].status == RunStatus.INTERRUPTED
    assert [snapshot.status for snapshot in history[:2]] == [
        RunStatus.QUEUED,
        RunStatus.RUNNING,
    ]


@pytest.mark.anyio
async def test_a_clarification_submission_links_to_its_parent(store: LocalStore) -> None:
    engine = await started(store, ControlledInterpreter())
    try:
        parent = await engine.wait((await engine.submit(submission())).run_id)
        assert parent.status == RunStatus.COMPLETED
        annotation = TextAnnotation(
            annotation_id="staff-payer",
            field="payer",
            value="Staff recorded payer",
            created_at=CREATED_AT,
        )
        submitted = await engine.submit(
            submission(parent_run_id=parent.run_id, annotations=(annotation,))
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
    engine = await started(store, interpreter)
    try:
        first = await engine.wait((await engine.submit(submission())).run_id)
        assert interpreter.calls == {"scope": 1, "policy": 1, "chart": 1, "evidence": 1}
        second = await engine.wait((await engine.submit(submission())).run_id)
        assert interpreter.calls == {"scope": 1, "policy": 1, "chart": 1, "evidence": 1}
        annotation = TextAnnotation(
            annotation_id="staff-plan",
            field="plan",
            value="Staff recorded plan",
            created_at=CREATED_AT,
        )
        third = await engine.wait(
            (await engine.submit(submission(annotations=(annotation,)))).run_id
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
        RunPhase.EXTRACTING_CHART,
        RunPhase.MAPPING_EVIDENCE,
    ):
        assert cached[phase].attempts == 0
    # A changed annotation repeats assessment work and leaves both extractions in place.
    assert third.input_fingerprint != second.input_fingerprint
    assert interpreter.calls == {"scope": 2, "policy": 1, "chart": 1, "evidence": 2}
    third_attempts = {usage.phase: usage.attempts for usage in third.usage}
    assert third_attempts[RunPhase.INTERPRETING_POLICY] == 0
    assert third_attempts[RunPhase.EXTRACTING_CHART] == 0
