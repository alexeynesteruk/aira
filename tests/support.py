"""Shared test doubles and helpers for workflow/API integration tests.

ControlledInterpreter is a test double for StageInterpreter: it resolves its
scripted quotes through a CitationResolver on the run's real extractions, so its
domain records carry source-valid spans unless a test scripts corruption. This
is controlled orchestration evidence — it makes no provider calls and asserts
nothing about live-model accuracy.

Import path: backend/pyproject.toml sets ``pythonpath = ["../tests"]`` so test
files import this module as ``support`` from both tests/unit and
tests/integration without a conftest or package scaffolding.
"""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from app.assessment.stages import (
    EvidenceInterpretation,
    PolicyInterpretation,
    ScopeInterpretation,
    StageInputs,
)
from app.assessment.workflow import (
    InterpretationFailure,
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
    CandidateCitation,
    ChartFact,
    ConfigurationProvenance,
    CreateAssessmentRequest,
    Criterion,
    CriterionNode,
    DocumentRecord,
    DocumentRole,
    EvidenceReference,
    EvidenceRelation,
    EvidenceStatus,
    ExtractionRecord,
    FactPolarity,
    Finding,
    InferenceSettings,
    NarrativePredicate,
    Policy,
    PolicySection,
    RequestContext,
    RequestField,
    RunPhase,
    SourceSpan,
    VersionReference,
)
from app.storage import LocalStore

ROOT = Path(__file__).resolve().parents[1]
POLICY_PDF = ROOT / "examples/guidelines/bcbs_fl_02-33000-31_2025-08-15.pdf"
POLICY_2026_PDF = ROOT / "examples/guidelines/bcbs_fl_02-33000-31_2026-01-01.pdf"
CHART_PDF = ROOT / "examples/charts/robert_mitchell_chart_final.pdf"
IMAGE_ONLY_PDF = ROOT / "tests/fixtures/pdf/image-only.pdf"
ENCRYPTED_PDF = ROOT / "tests/fixtures/pdf/encrypted.pdf"
CREATED_AT = datetime(2026, 10, 18, tzinfo=UTC)

# Quotes are exact native-text passages, each unique on its page.
POLICY_SCOPE_QUOTE = (1, "Subject: Treatments for Varicose Veins/Venous")
CHART_SCOPE_QUOTE = (1, "PATIENT MEDICAL CHART")
POLICY_CRITERION_QUOTE = (3, "Treatment of telangiectasia such as spider veins")
CHART_FACT_QUOTE = (3, "HR: 44 bpm, regular")


def parse_pdf(
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


def parse_sources() -> dict[str, tuple[DocumentRecord, ExtractionRecord, bytes]]:
    return {
        "policy": parse_pdf(POLICY_PDF, DocumentRole.POLICY, "policy-doc"),
        "chart": parse_pdf(CHART_PDF, DocumentRole.CHART, "chart-doc"),
    }


def configuration(
    limits: WorkflowLimits | None = None, parser_config: NativePdfConfig | None = None
) -> ConfigurationProvenance:
    return ConfigurationProvenance(
        parser=VersionReference(name="pdfplumber", version=PARSER_VERSION),
        parser_configuration_sha256=workflow_parser_fingerprint(
            parser_config or NativePdfConfig(), limits or WorkflowLimits()
        ),
        prompts=(VersionReference(name="controlled", version="1"),),
        model_id="controlled-interpreter",
        sdk_version="test-harness",
        inference=InferenceSettings(max_output_tokens=4096),
    )


def submission(**changes: object) -> CreateAssessmentRequest:
    return CreateAssessmentRequest(
        **{"policy_document_id": "policy-doc", "chart_document_id": "chart-doc", **changes}
    )


async def started(
    store: LocalStore, interpreter: "ControlledInterpreter", limits: WorkflowLimits | None = None
) -> WorkflowEngine:
    engine = WorkflowEngine(store, interpreter, configuration(limits), limits=limits)
    await engine.start()
    return engine


async def until(predicate: Callable[[], bool], message: str) -> None:
    for _ in range(400):
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError(message)


def resolver(inputs: StageInputs) -> CitationResolver:
    return CitationResolver(
        (inputs.policy_document, inputs.chart_document),
        (inputs.policy_extraction, inputs.chart_extraction),
    )


def quote(inputs: StageInputs, document: DocumentRecord, page: int, text: str) -> SourceSpan:
    return resolver(inputs).resolve(
        CandidateCitation(document_id=document.document_id, page=page, quote=text)
    )


def corrupted(span: SourceSpan) -> SourceSpan:
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
        policy_span = quote(inputs, inputs.policy_document, *POLICY_SCOPE_QUOTE)
        chart_span = quote(inputs, inputs.chart_document, *CHART_SCOPE_QUOTE)
        if self.corrupt_stage == RunPhase.CHECKING_APPLICABILITY:
            policy_span = corrupted(policy_span)
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
        span = quote(inputs, inputs.policy_document, *POLICY_CRITERION_QUOTE)
        if self.corrupt_stage == RunPhase.INTERPRETING_POLICY:
            span = corrupted(span)
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
        span = quote(inputs, inputs.chart_document, *CHART_FACT_QUOTE)
        if self.corrupt_stage == RunPhase.MAPPING_EVIDENCE:
            span = corrupted(span)
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
