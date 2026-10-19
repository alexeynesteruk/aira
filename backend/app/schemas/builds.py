"""Document preparation contracts. No patient request enters a guideline build."""

from typing import Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from .base import Identifier, NonEmptyText, Sha256, StrictModel, VersionedModel
from .documents import DocumentRole, ExtractionRecord, SourceSpan
from .evidence import ChartData
from .policies import Policy
from .provider import CandidateCitation, CandidatePolicyNode, PolicyCandidate
from .runs import ConfigurationProvenance, OperationalError, StageUsage


class BuildRequest(VersionedModel):
    parent_build_id: Identifier | None = None
    rebuild: bool = False


class SourceUnit(StrictModel):
    unit_id: Identifier
    source: SourceSpan
    heading: str = ""
    table_id: str | None = None


class SectionPlan(StrictModel):
    section_id: Identifier
    primary: tuple[SourceUnit, ...] = Field(min_length=1)
    context: tuple[SourceUnit, ...] = ()


class BlockDisposition(StrictModel):
    unit_id: str
    kind: Literal["requirements", "definition", "context", "non_normative", "unresolved"]
    explanation: str


class DefinitionCandidate(StrictModel):
    term: str
    meaning: str
    citations: tuple[CandidateCitation, ...]


class DependencyCandidate(StrictModel):
    reference_id: str
    target: str
    kind: Literal["definition", "exception", "scope", "continuation", "reference"]
    citations: tuple[CandidateCitation, ...]


class SectionCandidate(VersionedModel):
    dispositions: tuple[BlockDisposition, ...]
    fragment: PolicyCandidate | None
    definitions: tuple[DefinitionCandidate, ...]
    dependencies: tuple[DependencyCandidate, ...]
    issues: tuple[str, ...]


class SectionResult(StrictModel):
    section_id: Identifier
    plan: SectionPlan
    candidate: SectionCandidate
    policy: Policy | None = None


class PathCandidate(StrictModel):
    path_id: str
    title: str
    scope: str
    root_id: str
    citations: tuple[CandidateCitation, ...]


class DependencyResolution(StrictModel):
    reference_id: str
    target_section_ids: tuple[str, ...]
    explanation: str
    status: Literal["resolved", "unresolved", "conflicting"]


class ReconciliationCandidate(VersionedModel):
    # Only connective nodes may be added. Local rules/edges are immutable inputs.
    nodes: tuple[CandidatePolicyNode, ...]
    paths: tuple[PathCandidate, ...]
    resolutions: tuple[DependencyResolution, ...]
    issues: tuple[str, ...]


class ReconciliationGroup(StrictModel):
    group_id: str
    section_ids: tuple[str, ...]
    result: ReconciliationCandidate


class AuditCandidate(VersionedModel):
    checked_unit_ids: tuple[str, ...]
    missing_conditions: tuple[str, ...]
    issues: tuple[str, ...]


class CoverageEntry(StrictModel):
    section_id: Identifier
    unit_id: Identifier
    source: SourceSpan
    disposition: NonEmptyText
    explanation: NonEmptyText
    audited: bool


class BuildStep(StrictModel):
    name: str
    checkpoint_key: Sha256
    input_sha256: Sha256
    output_sha256: Sha256
    cached: bool
    configuration: ConfigurationProvenance


class BuildRecord(VersionedModel):
    contract_version: Literal["document-build-v1"] = "document-build-v1"
    build_id: Identifier
    parent_build_id: Identifier | None = None
    generation_id: Identifier | None = None
    document_id: Identifier
    document_sha256: Sha256
    role: DocumentRole
    fingerprint: Sha256
    configuration: ConfigurationProvenance
    build_limits: dict[str, int | float] = Field(default_factory=dict)
    created_at: AwareDatetime
    updated_at: AwareDatetime
    status: Literal["queued", "running", "completed", "failed", "interrupted"]
    phase: str = "queued"
    completed_sections: int = Field(default=0, ge=0)
    total_sections: int = Field(default=0, ge=0)
    cached: bool = False
    reused_from_build_id: Identifier | None = None
    review_status: Literal["draft", "approved", "rejected"] = "draft"
    extraction: ExtractionRecord | None = None
    policy: Policy | None = None
    chart: ChartData | None = None
    steps: tuple[BuildStep, ...] = ()
    coverage: tuple[CoverageEntry, ...] = ()
    resolutions: tuple[DependencyResolution, ...] = ()
    issues: tuple[str, ...] = ()
    usage: tuple[StageUsage, ...] = ()
    error: OperationalError | None = None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.parent_build_id == self.build_id:
            raise ValueError("a build cannot be its own parent")
        if self.completed_sections > self.total_sections:
            raise ValueError("build progress exceeds its section count")
        if self.status in ("failed", "interrupted") and self.error is None:
            raise ValueError("stopped build requires operational diagnostics")
        if self.status not in ("failed", "interrupted") and self.error is not None:
            raise ValueError("operational errors require a failed or interrupted build")
        if self.status == "completed":
            if self.extraction is None or self.completed_sections != self.total_sections:
                raise ValueError("a completed build requires complete extraction and section work")
            if (self.role == DocumentRole.POLICY) != (self.policy is not None):
                raise ValueError("completed policy builds require exactly their policy result")
            if (self.role == DocumentRole.CHART) != (self.chart is not None):
                raise ValueError("completed chart builds require exactly their chart result")
            if self.role == DocumentRole.POLICY and not self.coverage:
                raise ValueError("completed guideline builds require source coverage")
        elif self.policy is not None or self.chart is not None:
            raise ValueError("partial build results cannot appear as completed artifacts")
        if self.review_status == "approved" and self.status != "completed":
            raise ValueError("only a completed build can be approved")
        for value in (self.extraction, self.policy, self.chart):
            if value is not None and (value.document_id, value.document_sha256) != (
                self.document_id,
                self.document_sha256,
            ):
                raise ValueError("build artifact belongs to another document")
        return self


class BuildList(StrictModel):
    builds: tuple[BuildRecord, ...]


class BuildStepResponse(VersionedModel):
    receipt: BuildStep
    value: SectionCandidate | ReconciliationCandidate | AuditCandidate | ChartData | Policy
