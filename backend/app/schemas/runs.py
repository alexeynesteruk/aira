"""Run lifecycle, provenance, and assessment result contracts."""

from enum import StrEnum
from typing import Self

from pydantic import AwareDatetime, Field, model_validator

from .base import (
    FiniteNumber,
    Identifier,
    NonEmptyText,
    NonNegativeInt,
    PositiveInt,
    Sha256,
    StrictModel,
    VersionedModel,
)
from .evidence import ChartFact, EvidenceStatus, Finding
from .policies import Policy, ReviewIssue
from .requests import ApplicabilityResult, ApplicabilityStatus, MetadataAnnotation, RequestContext


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    NEEDS_INPUT = "needs_input"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class RunPhase(StrEnum):
    EXTRACTING = "extracting"
    CHECKING_APPLICABILITY = "checking_applicability"
    INTERPRETING_POLICY = "interpreting_policy"
    MAPPING_EVIDENCE = "mapping_evidence"
    VALIDATING = "validating"
    EVALUATING = "evaluating"


class AssessmentOutcome(StrEnum):
    APPLICABILITY_MISMATCH = "applicability_mismatch"
    DOCUMENTED_REQUIREMENTS_SATISFIED = "documented_requirements_satisfied"
    DOCUMENTATION_GAPS_OR_CONTRARY_EVIDENCE = "documentation_gaps_or_contrary_evidence"
    REVIEW_REQUIRED = "review_required"


class LogicalValue(StrEnum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"


class ErrorCode(StrEnum):
    ACCESS_DENIED = "access_denied"
    THROTTLED = "throttled"
    TIMEOUT = "timeout"
    REFUSED = "refused"
    INVALID_OUTPUT = "invalid_output"
    CITATION_INVALID = "citation_invalid"
    EXTRACTION_FAILED = "extraction_failed"
    CONFIGURATION_MISSING = "configuration_missing"
    UNSUPPORTED_INPUT = "unsupported_input"
    QUEUE_FULL = "queue_full"
    INTERRUPTED = "interrupted"
    INTERNAL_ERROR = "internal_error"
    NOT_FOUND = "not_found"
    INVALID_REQUEST = "invalid_request"
    STATE_CONFLICT = "state_conflict"


class OperationalError(StrictModel):
    code: ErrorCode
    message: NonEmptyText
    retryable: bool
    action: NonEmptyText
    stage: RunPhase | None = None
    provider_code: NonEmptyText | None = None
    document_id: Identifier | None = None
    page: PositiveInt | None = None


class VersionReference(StrictModel):
    name: NonEmptyText
    version: NonEmptyText


class InferenceSettings(StrictModel):
    max_output_tokens: PositiveInt
    temperature: FiniteNumber | None = Field(default=None, ge=0)
    top_p: FiniteNumber | None = Field(default=None, ge=0, le=1)


class ModelProvider(StrEnum):
    OPENAI = "openai"
    BEDROCK = "bedrock"


class ConfigurationProvenance(VersionedModel):
    parser: VersionReference
    parser_configuration_sha256: Sha256
    prompts: tuple[VersionReference, ...] = Field(min_length=1)
    provider: ModelProvider = ModelProvider.OPENAI
    model_id: NonEmptyText
    region: NonEmptyText | None = None
    sdk_version: NonEmptyText
    inference: InferenceSettings

    @model_validator(mode="after")
    def unique_prompts(self) -> Self:
        if len({item.name for item in self.prompts}) != len(self.prompts):
            raise ValueError("prompt names must be unique in configuration provenance")
        if self.provider == ModelProvider.BEDROCK and self.region is None:
            raise ValueError("Bedrock configuration requires a region")
        if self.provider == ModelProvider.OPENAI and self.region is not None:
            raise ValueError("OpenAI configuration does not use an AWS region")
        return self


class StageUsage(StrictModel):
    phase: RunPhase
    attempts: NonNegativeInt
    duration_ms: FiniteNumber = Field(ge=0)
    input_tokens: NonNegativeInt | None = None
    output_tokens: NonNegativeInt | None = None
    ocr_pages: NonNegativeInt = 0
    provider_request_ids: tuple[NonEmptyText, ...] = ()
    provider_response_ids: tuple[NonEmptyText, ...] = ()
    model_id: NonEmptyText | None = None


class RunProgress(StrictModel):
    completed_phases: tuple[RunPhase, ...] = ()
    completed_pages: NonNegativeInt = 0
    total_pages: NonNegativeInt | None = None

    @model_validator(mode="after")
    def bounded_progress(self) -> Self:
        if self.total_pages is not None and self.completed_pages > self.total_pages:
            raise ValueError("completed pages cannot exceed the known total")
        if len(set(self.completed_phases)) != len(self.completed_phases):
            raise ValueError("completed phases must be unique")
        return self


class AssessmentResult(VersionedModel):
    outcome: AssessmentOutcome
    applicability: ApplicabilityResult
    policy: Policy | None = None
    facts: tuple[ChartFact, ...] = ()
    findings: tuple[Finding, ...] = ()
    logical_value: LogicalValue | None = None
    issues: tuple[ReviewIssue, ...] = ()

    @model_validator(mode="after")
    def coherent_result(self) -> Self:
        if self.outcome == AssessmentOutcome.APPLICABILITY_MISMATCH:
            if self.applicability.status != ApplicabilityStatus.MISMATCH:
                raise ValueError("mismatch outcome requires a mismatch applicability finding")
            if self.policy is not None or self.findings or self.logical_value is not None:
                raise ValueError("mismatch cannot contain a necessity evaluation")
            return self
        if self.applicability.status != ApplicabilityStatus.APPLICABLE:
            raise ValueError("necessity results require resolved applicable scope")
        if self.policy is None or self.logical_value is None:
            raise ValueError("applicable assessment requires policy data and a logical result")
        criteria = {criterion.criterion_id for criterion in self.policy.criteria}
        finding_ids = [finding.criterion_id for finding in self.findings]
        if set(finding_ids) != criteria or len(finding_ids) != len(criteria):
            raise ValueError("each policy criterion requires exactly one finding")
        fact_ids = {fact.fact_id for fact in self.facts}
        if len(fact_ids) != len(self.facts):
            raise ValueError("fact identifiers must be unique")
        for fact in self.facts:
            if not set(fact.conflicting_fact_ids).issubset(fact_ids):
                raise ValueError("fact conflict references an unknown fact")
        for finding in self.findings:
            if any(reference.fact_id not in fact_ids for reference in finding.evidence):
                raise ValueError("finding references an unknown fact")
        if len({issue.issue_id for issue in self.issues}) != len(self.issues):
            raise ValueError("result issue identifiers must be unique")
        for issue in self.issues:
            if not set(issue.criterion_ids).issubset(criteria):
                raise ValueError("result issue references an unknown criterion")
        if self.outcome == AssessmentOutcome.DOCUMENTED_REQUIREMENTS_SATISFIED:
            if self.logical_value != LogicalValue.TRUE:
                raise ValueError("satisfied outcome requires a true evaluated root")
            if any(issue.blocks_readiness for issue in (*self.issues, *self.policy.issues)):
                raise ValueError("blocking issues prohibit a satisfied outcome")
            if any(section.disposition == "unresolved" for section in self.policy.sections):
                raise ValueError("unclassified governing sections prohibit a satisfied outcome")
            if not any(finding.status == EvidenceStatus.MET for finding in self.findings):
                raise ValueError("satisfied outcome requires at least one supported finding")
        return self


class RunRecord(VersionedModel):
    run_id: Identifier
    parent_run_id: Identifier | None = None
    policy_document_id: Identifier
    policy_sha256: Sha256
    chart_document_id: Identifier
    chart_sha256: Sha256
    input_fingerprint: Sha256
    configuration: ConfigurationProvenance
    request_context: RequestContext | None = None
    annotations: tuple[MetadataAnnotation, ...] = ()
    created_at: AwareDatetime
    updated_at: AwareDatetime
    status: RunStatus
    phase: RunPhase | None = None
    progress: RunProgress = Field(default_factory=RunProgress)
    applicability: ApplicabilityResult | None = None
    result: AssessmentResult | None = None
    error: OperationalError | None = None
    usage: tuple[StageUsage, ...] = ()

    @model_validator(mode="after")
    def valid_lifecycle(self) -> Self:
        if self.run_id == self.parent_run_id:
            raise ValueError("a run cannot be its own parent")
        if self.policy_document_id == self.chart_document_id:
            raise ValueError("policy and chart must have distinct role-scoped document IDs")
        if self.updated_at < self.created_at:
            raise ValueError("run update cannot precede creation")
        if len({item.annotation_id for item in self.annotations}) != len(self.annotations):
            raise ValueError("annotation identifiers must be unique")
        if self.status == RunStatus.QUEUED and self.phase is not None:
            raise ValueError("queued work has no running phase")
        if self.status == RunStatus.RUNNING and self.phase is None:
            raise ValueError("running work must identify its phase")
        if self.status == RunStatus.COMPLETED:
            if self.result is None:
                raise ValueError("completed run requires a validated result")
        elif self.result is not None:
            raise ValueError("only completed runs can contain an assessment result")
        if self.status == RunStatus.NEEDS_INPUT:
            if (
                self.applicability is None
                or self.applicability.status != ApplicabilityStatus.UNRESOLVED
            ):
                raise ValueError("needs_input requires unresolved scope with named fields")
        if self.status in (RunStatus.FAILED, RunStatus.INTERRUPTED):
            if self.error is None:
                raise ValueError("failed or interrupted runs require operational diagnostics")
        elif self.error is not None:
            raise ValueError("operational errors belong to failed or interrupted runs")
        if self.status == RunStatus.INTERRUPTED:
            if self.error is not None and self.error.code != ErrorCode.INTERRUPTED:
                raise ValueError("interrupted run requires an interruption diagnostic")
        self._validate_result_identity()
        return self

    def _validate_result_identity(self) -> None:
        inputs = {
            self.policy_document_id: self.policy_sha256,
            self.chart_document_id: self.chart_sha256,
        }
        if self.applicability is not None:
            for source in self.applicability.sources:
                if inputs.get(source.document_id) != source.document_sha256:
                    raise ValueError("scope evidence must belong to the run's inputs")
        if self.result is None:
            return
        for source in self.result.applicability.sources:
            if inputs.get(source.document_id) != source.document_sha256:
                raise ValueError("scope evidence must belong to the run's inputs")
        for issue in self.result.issues:
            for source in issue.sources:
                if inputs.get(source.document_id) != source.document_sha256:
                    raise ValueError("result issue sources must belong to the run's inputs")
        if self.applicability is not None and self.applicability != self.result.applicability:
            raise ValueError("run and result applicability snapshots must agree")
        if self.result.policy is not None:
            if (
                self.result.policy.document_id != self.policy_document_id
                or self.result.policy.document_sha256 != self.policy_sha256
            ):
                raise ValueError("result policy does not belong to the run's policy input")
            if self.request_context is None or self.request_context.procedure is None:
                raise ValueError("applicable result requires a selected procedure")
        for fact in self.result.facts:
            for source in fact.sources:
                if (
                    source.document_id != self.chart_document_id
                    or source.document_sha256 != self.chart_sha256
                ):
                    raise ValueError("result facts must belong to the run's chart input")
