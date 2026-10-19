"""Document extractions are independent of assessment and survive restart."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from support import configuration, document_quote

from app.assessment.stages import (
    ChartInterpretation,
    DocumentInputs,
    EvidenceInterpretation,
    PolicyInterpretation,
    ScopeInterpretation,
    StageInputs,
    render_document_input,
    render_stage_input,
)
from app.assessment.workflow import InterpretationFailure, WorkflowEngine, WorkflowLimits
from app.documents import inspect_pdf
from app.schemas import (
    ApplicabilityResult,
    ApplicabilityStatus,
    ChartData,
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
    FactPolarity,
    Finding,
    NarrativePredicate,
    OperationalError,
    Policy,
    PolicySection,
    RequestContext,
    RunPhase,
    RunStatus,
    TextAnnotation,
    VersionReference,
)
from app.schemas.builds import BuildRequest
from app.storage import LocalStore, StorageConflict

ROOT = Path(__file__).resolve().parents[2]
POLICY_V1 = ROOT / "examples/guidelines/bcbs_fl_02-33000-31_2025-08-15.pdf"
POLICY_V2 = ROOT / "examples/guidelines/bcbs_fl_02-33000-31_2026-01-01.pdf"
CHART_A = ROOT / "examples/charts/robert_mitchell_chart_final.pdf"
CHART_B = ROOT / "examples/synthetic/monitor_chart.pdf"
CREATED_AT = datetime(2026, 10, 18, tzinfo=UTC)


def _first_quote(document: DocumentRecord, extraction) -> object:
    for page in extraction.pages:
        for block in page.blocks:
            text = " ".join(block.text.split())
            if text:
                return document_quote(document, extraction, page.page, block.text)
    raise AssertionError(f"{document.document_id} has no native text")


class RecordingInterpreter:
    """Scripted interpreter. Payloads are the real rendered stage inputs."""

    def __init__(self) -> None:
        self.calls = {"policy": 0, "chart": 0, "scope": 0, "evidence": 0}
        self.policy_payloads: list[str] = []
        self.chart_payloads: list[str] = []
        self.assessment_payloads: list[str] = []

    async def policy(self, inputs: DocumentInputs) -> PolicyInterpretation:
        self.calls["policy"] += 1
        rendered = render_document_input(inputs)
        self.policy_payloads.append(rendered)
        assert inputs.document.role == DocumentRole.POLICY
        span = _first_quote(inputs.document, inputs.extraction)
        criterion = Criterion(
            criterion_id="criterion-recorded",
            wording="Recorded requirement.",
            interpretation="Does the chart document the recorded requirement?",
            sources=(span,),
            predicate=NarrativePredicate(question="Is the recorded requirement documented?"),
        )
        return PolicyInterpretation(
            policy=Policy(
                policy_id="recorded-policy",
                document_id=inputs.document.document_id,
                document_sha256=inputs.document.sha256,
                title="Recorded policy",
                scope_summary="Whole-guideline script.",
                criteria=(criterion,),
                nodes=(
                    CriterionNode(
                        node_id="root", criterion_id=criterion.criterion_id, sources=(span,)
                    ),
                ),
                root_id="root",
                sections=(
                    PolicySection(
                        section_id="requirements",
                        heading="Requirements",
                        sources=(span,),
                        disposition="requirements",
                        criterion_ids=(criterion.criterion_id,),
                        explanation="The recorded criterion is a requirement.",
                    ),
                ),
            )
        )

    async def chart(self, inputs: DocumentInputs) -> ChartInterpretation:
        self.calls["chart"] += 1
        rendered = render_document_input(inputs)
        self.chart_payloads.append(rendered)
        assert inputs.document.role == DocumentRole.CHART
        span = _first_quote(inputs.document, inputs.extraction)
        return ChartInterpretation(
            chart=ChartData(
                document_id=inputs.document.document_id,
                document_sha256=inputs.document.sha256,
                facts=(
                    ChartFact(
                        fact_id="fact-recorded",
                        proposition="The chart records a sourced fact.",
                        sources=(span,),
                        polarity=FactPolarity.AFFIRMED,
                    ),
                ),
            )
        )

    async def scope(self, inputs: StageInputs) -> ScopeInterpretation:
        self.calls["scope"] += 1
        rendered = render_stage_input(inputs, "scope")
        self.assessment_payloads.append(rendered)
        assert inputs.policy is not None and inputs.chart is not None
        return ScopeInterpretation(
            request=RequestContext(procedure="recorded procedure", payer="Fixture payer"),
            applicability=ApplicabilityResult(
                status=ApplicabilityStatus.APPLICABLE,
                rationale="Saved artifacts establish applicability.",
                sources=(
                    inputs.policy.criteria[0].sources[0],
                    inputs.chart.facts[0].sources[0],
                ),
            ),
        )

    async def evidence(self, inputs: StageInputs, policy: Policy) -> EvidenceInterpretation:
        self.calls["evidence"] += 1
        self.assessment_payloads.append(render_stage_input(inputs, "evidence", policy))
        assert inputs.chart is not None
        fact_id = inputs.chart.facts[0].fact_id
        return EvidenceInterpretation(
            facts=inputs.chart.facts,
            findings=tuple(
                Finding(
                    criterion_id=criterion.criterion_id,
                    status=EvidenceStatus.MET,
                    rationale="The saved fact supports the recorded requirement.",
                    evidence=(
                        EvidenceReference(fact_id=fact_id, relation=EvidenceRelation.SUPPORTING),
                    ),
                )
                for criterion in policy.criteria
            ),
        )


def _upload(store: LocalStore, path: Path, role: DocumentRole, document_id: str) -> DocumentRecord:
    raw = path.read_bytes()
    document = inspect_pdf(
        raw, document_id=document_id, filename=path.name, role=role, created_at=CREATED_AT
    )
    store.put_document(document, raw)
    return document


def _named(limits: WorkflowLimits, **versions: str) -> ConfigurationProvenance:
    base = configuration(limits)
    prompts = tuple(
        VersionReference(name=name, version=versions.get(name, "1"))
        for name in ("policy", "chart", "scope", "evidence")
    )
    return base.model_copy(update={"prompts": prompts})


async def _engine(
    store: LocalStore, interpreter: RecordingInterpreter, config: ConfigurationProvenance
):
    limits = WorkflowLimits()
    # configuration() baked the default limits into the parser fingerprint.
    engine = WorkflowEngine(store, interpreter, config, limits=limits)
    await engine.start()
    return engine


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_extractions_reuse_across_patients_requests_and_restarts(tmp_path: Path) -> None:
    limits = WorkflowLimits()
    store = LocalStore(tmp_path / "store")
    policy = _upload(store, POLICY_V1, DocumentRole.POLICY, "policy-v1")
    chart_a = _upload(store, CHART_A, DocumentRole.CHART, "chart-a")
    chart_b = _upload(store, CHART_B, DocumentRole.CHART, "chart-b")
    interpreter = RecordingInterpreter()
    config = _named(limits)
    engine = await _engine(store, interpreter, config)
    try:
        first = await engine.wait(
            (
                await engine.submit(
                    CreateAssessmentRequest(
                        policy_document_id=policy.document_id,
                        chart_document_id=chart_a.document_id,
                    )
                )
            ).run_id
        )
        second = await engine.wait(
            (
                await engine.submit(
                    CreateAssessmentRequest(
                        policy_document_id=policy.document_id,
                        chart_document_id=chart_b.document_id,
                    )
                )
            ).run_id
        )
        assert interpreter.calls == {"policy": 1, "chart": 2, "scope": 2, "evidence": 2}
        assert first.status == second.status == RunStatus.COMPLETED
        assert (
            second.result is not None and second.result.facts[0].sources[0].document_id == "chart-b"
        )
        assert (
            first.result is not None and first.result.facts[0].sources[0].document_id == "chart-a"
        )

        changed = _upload(store, POLICY_V2, DocumentRole.POLICY, "policy-v2")
        third = await engine.wait(
            (
                await engine.submit(
                    CreateAssessmentRequest(
                        policy_document_id=changed.document_id,
                        chart_document_id=chart_a.document_id,
                    )
                )
            ).run_id
        )
        assert third.status == RunStatus.COMPLETED
        assert interpreter.calls["policy"] == 2
        assert interpreter.calls["chart"] == 2
        assert third.result is not None
        assert third.result.policy is not None
        assert third.result.policy.document_id == "policy-v2"
        assert third.result.facts[0].sources[0].document_id == "chart-a"

        annotated = await engine.wait(
            (
                await engine.submit(
                    CreateAssessmentRequest(
                        policy_document_id=policy.document_id,
                        chart_document_id=chart_a.document_id,
                        annotations=(
                            TextAnnotation(
                                annotation_id="staff-plan",
                                field="plan",
                                value="Staff plan",
                                created_at=CREATED_AT,
                            ),
                        ),
                    )
                )
            ).run_id
        )
        assert annotated.status == RunStatus.COMPLETED
        assert interpreter.calls["policy"] == 2
        assert interpreter.calls["chart"] == 2
        assert interpreter.calls["scope"] == 4
        assert interpreter.calls["evidence"] == 4

        duplicate = _upload(store, POLICY_V1, DocumentRole.POLICY, "policy-duplicate")
        assert duplicate.sha256 == policy.sha256
        rebound = await engine.wait(
            (
                await engine.submit(
                    CreateAssessmentRequest(
                        policy_document_id=duplicate.document_id,
                        chart_document_id=chart_a.document_id,
                    )
                )
            ).run_id
        )
        assert interpreter.calls["policy"] == 2
        assert rebound.result is not None and rebound.result.policy is not None
        assert rebound.result.policy.document_id == "policy-duplicate"
        assert rebound.result.policy.criteria[0].sources[0].document_id == "policy-duplicate"
    finally:
        await engine.close()

    reopened = LocalStore(store.root)
    restarted = RecordingInterpreter()
    again = await _engine(reopened, restarted, config)
    try:
        rerun = await again.wait(
            (
                await again.submit(
                    CreateAssessmentRequest(
                        policy_document_id="policy-v1", chart_document_id="chart-a"
                    )
                )
            ).run_id
        )
    finally:
        await again.close()
    assert rerun.status == RunStatus.COMPLETED
    assert restarted.calls == {"policy": 0, "chart": 0, "scope": 0, "evidence": 0}

    policy_packet = interpreter.policy_payloads[0]
    chart_packet = interpreter.chart_payloads[0]
    assert "chart-a" not in policy_packet and "robert_mitchell" not in policy_packet
    assert "policy-v1" not in chart_packet and "bcbs_fl" not in chart_packet
    assert "selected_request" not in policy_packet
    assert "staff_annotations" not in chart_packet
    for packet in interpreter.assessment_payloads:
        body = packet
        assert '"input_kind":"saved_document_interpretations"' in body
        assert "robert_mitchell_chart_final" not in body
        assert "bcbs_fl_02-33000-31_2025-08-15" not in body

    # A policy-prompt change rebuilds only the guideline.
    # An assessment-prompt change rebuilds neither extraction.
    policy_prompt = _named(limits, policy="2")
    focused = RecordingInterpreter()
    prompted = await _engine(LocalStore(store.root), focused, policy_prompt)
    try:
        await prompted.wait(
            (
                await prompted.submit(
                    CreateAssessmentRequest(
                        policy_document_id="policy-v1", chart_document_id="chart-a"
                    )
                )
            ).run_id
        )
    finally:
        await prompted.close()
    assert focused.calls["policy"] == 1
    assert focused.calls["chart"] == 0

    assessment_prompt = _named(limits, scope="2", evidence="2")
    stable = RecordingInterpreter()
    prompted = await _engine(LocalStore(store.root), stable, assessment_prompt)
    try:
        await prompted.wait(
            (
                await prompted.submit(
                    CreateAssessmentRequest(
                        policy_document_id="policy-v1", chart_document_id="chart-a"
                    )
                )
            ).run_id
        )
    finally:
        await prompted.close()
    assert stable.calls["policy"] == 0
    assert stable.calls["chart"] == 0
    assert stable.calls["scope"] == 1

    stored = LocalStore(store.root)
    rule_sets = stored.list_policy_rule_sets(document_id="policy-v1")
    assert rule_sets
    stored.approve_policy_rule_set(str(rule_sets[0]["rule_set_id"]), reviewer="staff")
    approved = RecordingInterpreter()
    prompted = await _engine(stored, approved, config)
    try:
        await prompted.wait(
            (
                await prompted.submit(
                    CreateAssessmentRequest(
                        policy_document_id="policy-v1", chart_document_id="chart-a"
                    )
                )
            ).run_id
        )
    finally:
        await prompted.close()
    assert approved.calls["policy"] == 0
    assert approved.calls["chart"] == 0


@pytest.mark.anyio
async def test_bad_artifacts_are_not_reused_and_the_other_document_stays(tmp_path: Path) -> None:
    """Build manifests are authoritative; corruption fails closed until explicit rebuild."""
    store = LocalStore(tmp_path / "store")
    policy = _upload(store, POLICY_V1, DocumentRole.POLICY, "policy-v1")
    chart = _upload(store, CHART_A, DocumentRole.CHART, "chart-a")
    config = _named(WorkflowLimits())
    engine = await _engine(store, RecordingInterpreter(), config)
    first = await engine.wait(
        (
            await engine.submit(
                CreateAssessmentRequest(
                    policy_document_id=policy.document_id, chart_document_id=chart.document_id
                )
            )
        ).run_id
    )
    await engine.close()
    assert first.status == RunStatus.COMPLETED
    with sqlite3.connect(store.database_path) as connection:
        digest = connection.execute(
            "SELECT payload_sha256 FROM document_builds WHERE build_id=?", (first.policy_build_id,)
        ).fetchone()[0]
    (store.root / "objects" / digest).unlink()
    restored = RecordingInterpreter()
    engine = await _engine(LocalStore(store.root), restored, config)
    try:
        failed = await engine.wait(
            (
                await engine.submit(
                    CreateAssessmentRequest(
                        policy_document_id=policy.document_id, chart_document_id=chart.document_id
                    )
                )
            ).run_id
        )
        assert failed.status == RunStatus.FAILED and failed.error.code == ErrorCode.STATE_CONFLICT
        assert restored.calls["policy"] == 0
        rebuilt = await engine.builds.wait(
            (await engine.builds.submit(policy.document_id, BuildRequest(rebuild=True))).build_id
        )
        assert rebuilt.status == "completed"
        run = await engine.wait(
            (
                await engine.submit(
                    CreateAssessmentRequest(
                        policy_document_id=policy.document_id,
                        chart_document_id=chart.document_id,
                        policy_build_id=rebuilt.build_id,
                        chart_build_id=first.chart_build_id,
                    )
                )
            ).run_id
        )
        assert run.status == RunStatus.COMPLETED, run.error
        assert restored.calls["policy"] == 1 and restored.calls["chart"] == 0
        engine.builds.review(rebuilt.build_id, approve=False)
        with pytest.raises(StorageConflict, match="rejected"):
            await engine.builds.prepare(policy, rebuilt.build_id)
        assert store.get_build(first.chart_build_id).chart is not None
    finally:
        await engine.close()


@pytest.mark.anyio
async def test_an_extraction_failure_is_not_recorded_as_missing(tmp_path: Path) -> None:
    class FailingChart(RecordingInterpreter):
        async def chart(self, inputs: DocumentInputs) -> ChartInterpretation:
            await super().chart(inputs)
            raise InterpretationFailure(
                OperationalError(
                    code=ErrorCode.EXTRACTION_FAILED,
                    message="The chart model call failed.",
                    retryable=True,
                    action="Retry the assessment.",
                )
            )

    store = LocalStore(tmp_path / "store")
    _upload(store, POLICY_V1, DocumentRole.POLICY, "policy-v1")
    _upload(store, CHART_A, DocumentRole.CHART, "chart-a")
    interpreter = FailingChart()
    engine = await _engine(store, interpreter, _named(WorkflowLimits()))
    try:
        run = await engine.wait(
            (
                await engine.submit(
                    CreateAssessmentRequest(
                        policy_document_id="policy-v1", chart_document_id="chart-a"
                    )
                )
            ).run_id
        )
    finally:
        await engine.close()
    assert run.status == RunStatus.FAILED
    assert run.result is None
    assert run.error is not None
    assert run.error.code == ErrorCode.EXTRACTION_FAILED
    assert run.error.stage == RunPhase.EXTRACTING_CHART
    assert "missing" not in run.error.code.value
