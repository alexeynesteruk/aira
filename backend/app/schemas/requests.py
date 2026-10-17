"""Selected request, staff metadata annotations, and applicability."""

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from .base import Identifier, NonEmptyText, StrictModel, VersionedModel
from .documents import SourceSpan


class RequestField(StrEnum):
    PROCEDURE = "procedure"
    PROCEDURE_CODE = "procedure_code"
    ANATOMICAL_TARGET = "anatomical_target"
    LATERALITY = "laterality"
    PAYER = "payer"
    PLAN = "plan"
    SERVICE_DATE = "service_date"
    ASSESSMENT_CUTOFF = "assessment_cutoff"


class PolicyScopeField(StrEnum):
    POLICY_SCOPE = "policy_scope"
    POLICY_EFFECTIVE_PERIOD = "policy_effective_period"
    PLAN_EXCEPTION = "plan_exception"


type ClarificationField = RequestField | PolicyScopeField


class FieldSources(StrictModel):
    field: RequestField
    sources: tuple[SourceSpan, ...] = Field(min_length=1)


class RequestContext(VersionedModel):
    procedure: NonEmptyText | None = None
    procedure_code: NonEmptyText | None = None
    anatomical_target: NonEmptyText | None = None
    laterality: NonEmptyText | None = None
    payer: NonEmptyText | None = None
    plan: NonEmptyText | None = None
    service_date: date | None = None
    assessment_cutoff: date | None = None
    field_sources: tuple[FieldSources, ...] = ()
    unresolved_fields: tuple[RequestField, ...] = ()

    @model_validator(mode="after")
    def unique_fields(self) -> Self:
        fields = [item.field for item in self.field_sources]
        if len(fields) != len(set(fields)):
            raise ValueError("combine a request field's citations in one source record")
        if len(self.unresolved_fields) != len(set(self.unresolved_fields)):
            raise ValueError("unresolved request fields must be unique")
        return self


class AnnotationBase(StrictModel):
    annotation_id: Identifier
    origin: Literal["staff"] = "staff"
    created_at: AwareDatetime
    original_sources: tuple[SourceSpan, ...] = ()
    resolves_conflict: bool = False
    resolution_reason: NonEmptyText | None = None

    @model_validator(mode="after")
    def explained_resolution(self) -> Self:
        if self.resolves_conflict and (not self.original_sources or not self.resolution_reason):
            raise ValueError("a conflict resolution needs original sources and an explicit reason")
        return self


class TextAnnotation(AnnotationBase):
    kind: Literal["text"] = "text"
    field: Literal[
        "procedure", "procedure_code", "anatomical_target", "laterality", "payer", "plan"
    ]
    value: NonEmptyText


class DateAnnotation(AnnotationBase):
    kind: Literal["date"] = "date"
    field: Literal["service_date", "assessment_cutoff"]
    value: date


type MetadataAnnotation = Annotated[TextAnnotation | DateAnnotation, Field(discriminator="kind")]


class ApplicabilityStatus(StrEnum):
    APPLICABLE = "applicable"
    MISMATCH = "mismatch"
    UNRESOLVED = "unresolved"


class ApplicabilityResult(StrictModel):
    status: ApplicabilityStatus
    rationale: NonEmptyText
    sources: tuple[SourceSpan, ...] = ()
    unresolved_fields: tuple[ClarificationField, ...] = ()

    @model_validator(mode="after")
    def supported_scope(self) -> Self:
        if self.status == ApplicabilityStatus.UNRESOLVED:
            if not self.unresolved_fields:
                raise ValueError("unresolved applicability must identify fields needing input")
        elif self.unresolved_fields:
            raise ValueError("resolved applicability cannot contain unresolved scope fields")
        if self.status != ApplicabilityStatus.UNRESOLVED and not self.sources:
            raise ValueError("a resolved applicability finding requires source evidence")
        return self
