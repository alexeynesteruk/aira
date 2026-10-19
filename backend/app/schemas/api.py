"""Framework-independent request, response, health, and export contracts."""

from enum import StrEnum
from typing import Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from .base import Identifier, NonEmptyText, Sha256, StrictModel, VersionedModel
from .documents import DocumentRecord, DocumentRole, ExtractedPage, ExtractionRecord
from .requests import MetadataAnnotation, RequestContext
from .runs import ModelProvider, OperationalError, RunPhase, RunRecord, RunStatus


class CreateAssessmentRequest(VersionedModel):
    policy_build_id: Identifier | None = None
    chart_build_id: Identifier | None = None
    policy_document_id: Identifier
    chart_document_id: Identifier
    request_context: RequestContext | None = None
    annotations: tuple[MetadataAnnotation, ...] = ()
    parent_run_id: Identifier | None = None

    @model_validator(mode="after")
    def distinct_inputs(self) -> Self:
        if self.policy_document_id == self.chart_document_id:
            raise ValueError("policy and chart must use distinct role-scoped document IDs")
        return self


class AssessmentAccepted(VersionedModel):
    run_id: Identifier
    status: Literal["queued", "running"]
    phase: RunPhase | None = None
    status_url: NonEmptyText

    @model_validator(mode="after")
    def accepted_state(self) -> Self:
        if (self.status == "running") != (self.phase is not None):
            raise ValueError("only a running accepted job has a phase")
        if self.status_url != f"/api/assessments/{self.run_id}":
            raise ValueError("status URL must identify the accepted run")
        return self


class DocumentResponse(VersionedModel):
    document: DocumentRecord
    extractions: tuple[ExtractionRecord, ...] = ()

    @model_validator(mode="after")
    def own_extractions(self) -> Self:
        for extraction in self.extractions:
            if (
                extraction.document_id != self.document.document_id
                or extraction.document_sha256 != self.document.sha256
                or len(extraction.pages) != self.document.page_count
            ):
                raise ValueError("extraction must account for its original document")
        return self


class PageResponse(VersionedModel):
    document_id: Identifier
    extraction_id: Identifier
    page: ExtractedPage


class ErrorResponse(VersionedModel):
    request_id: Identifier
    error: OperationalError
    run_id: Identifier | None = None


class LivenessResponse(StrictModel):
    status: Literal["alive"] = "alive"


class VerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    FAILED = "failed"


class ProviderVerification(StrictModel):
    backend: Literal["openai", "litellm"] | None = None
    transport: Literal["responses", "chat_completions"] | None = None
    endpoint_sha256: Sha256 | None = None
    status: VerificationStatus = VerificationStatus.UNVERIFIED
    provider: ModelProvider = ModelProvider.OPENAI
    checked_at: AwareDatetime | None = None
    model_id: NonEmptyText | None = None
    region: NonEmptyText | None = None
    detail: NonEmptyText | None = None

    @model_validator(mode="after")
    def dated_verification(self) -> Self:
        if self.status != VerificationStatus.UNVERIFIED:
            if self.checked_at is None or self.model_id is None:
                raise ValueError("provider verification requires time and model context")
        elif self.checked_at is not None:
            raise ValueError("unverified provider cannot have a completed check timestamp")
        if self.provider == ModelProvider.OPENAI and self.region is not None:
            raise ValueError("OpenAI verification does not use a region")
        return self


class ReadinessResponse(VersionedModel):
    ready: bool
    missing_prerequisites: tuple[NonEmptyText, ...] = ()
    provider: ProviderVerification = Field(default_factory=ProviderVerification)

    @model_validator(mode="after")
    def actionable_readiness(self) -> Self:
        if self.ready == bool(self.missing_prerequisites):
            raise ValueError("readiness must agree with missing local prerequisites")
        return self


class AssessmentExport(VersionedModel):
    exported_at: AwareDatetime
    run: RunRecord
    documents: tuple[DocumentRecord, ...] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def exportable_run(self) -> Self:
        if self.run.status not in (RunStatus.COMPLETED, RunStatus.NEEDS_INPUT):
            raise ValueError("only completed or needs_input runs have checklist exports")
        by_role = {document.role: document for document in self.documents}
        if set(by_role) != {DocumentRole.POLICY, DocumentRole.CHART}:
            raise ValueError("export requires one policy and one chart document")
        policy = by_role[DocumentRole.POLICY]
        chart = by_role[DocumentRole.CHART]
        if (
            policy.document_id != self.run.policy_document_id
            or policy.sha256 != self.run.policy_sha256
            or chart.document_id != self.run.chart_document_id
            or chart.sha256 != self.run.chart_sha256
        ):
            raise ValueError("export document identities must match the saved run")
        return self
