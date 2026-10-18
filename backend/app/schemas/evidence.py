"""Chart facts and criterion findings; no clinical inference runs here."""

from datetime import date
from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from .base import FiniteNumber, Identifier, NonEmptyText, Sha256, StrictModel, VersionedModel
from .documents import SourceSpan


class FactPolarity(StrEnum):
    AFFIRMED = "affirmed"
    NEGATED = "negated"
    UNCERTAIN = "uncertain"


class FactProvenance(StrEnum):
    DIRECT = "direct"
    CLINICIAN_SUMMARY = "clinician_summary"


class ChartFact(StrictModel):
    fact_id: Identifier
    proposition: NonEmptyText
    sources: tuple[SourceSpan, ...] = Field(min_length=1)
    polarity: FactPolarity
    provenance: FactProvenance = FactProvenance.DIRECT
    value: FiniteNumber | None = None
    unit: NonEmptyText | None = None
    event_date: date | None = None
    documentation_date: date | None = None
    anatomical_target: NonEmptyText | None = None
    laterality: NonEmptyText | None = None
    context: tuple[NonEmptyText, ...] = ()
    uncertainty: tuple[NonEmptyText, ...] = ()
    conflicting_fact_ids: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def preserve_quantity(self) -> Self:
        if self.unit is not None and self.value is None:
            raise ValueError("a unit cannot exist without its documented numeric value")
        if self.fact_id in self.conflicting_fact_ids:
            raise ValueError("a fact cannot conflict with itself")
        return self


class ChartData(VersionedModel):
    """Document-only extraction, reusable across guidelines and requests."""

    document_id: Identifier
    document_sha256: Sha256
    facts: tuple[ChartFact, ...]
    interpretation_issues: tuple[NonEmptyText, ...] = ()

    @model_validator(mode="after")
    def own_facts(self) -> Self:
        ids = {fact.fact_id for fact in self.facts}
        if len(ids) != len(self.facts):
            raise ValueError("chart fact identifiers must be unique")
        for fact in self.facts:
            if not set(fact.conflicting_fact_ids) <= ids:
                raise ValueError("chart conflict references an unknown fact")
            for source in fact.sources:
                if (source.document_id, source.document_sha256) != (
                    self.document_id,
                    self.document_sha256,
                ):
                    raise ValueError("chart facts must belong to their original document")
        return self


class EvidenceStatus(StrEnum):
    MET = "met"
    NOT_MET = "not_met"
    MISSING = "missing"
    CONFLICTING = "conflicting"
    NEEDS_REVIEW = "needs_review"


class EvidenceRelation(StrEnum):
    SUPPORTING = "supporting"
    CONTRADICTING = "contradicting"
    CONTEXT = "context"


class EvidenceReference(StrictModel):
    fact_id: Identifier
    relation: EvidenceRelation


class Finding(StrictModel):
    criterion_id: Identifier
    status: EvidenceStatus
    rationale: NonEmptyText
    evidence: tuple[EvidenceReference, ...] = ()
    unresolved_reasons: tuple[NonEmptyText, ...] = ()

    @model_validator(mode="after")
    def coherent_evidence(self) -> Self:
        fact_ids = [reference.fact_id for reference in self.evidence]
        if len(fact_ids) != len(set(fact_ids)):
            raise ValueError("a finding may reference each fact only once")
        relations = {reference.relation for reference in self.evidence}
        if self.status == EvidenceStatus.MET and EvidenceRelation.SUPPORTING not in relations:
            raise ValueError("met requires supporting evidence")
        if (
            self.status == EvidenceStatus.NOT_MET
            and EvidenceRelation.CONTRADICTING not in relations
        ):
            raise ValueError("not_met requires contrary evidence")
        opposing = {EvidenceRelation.SUPPORTING, EvidenceRelation.CONTRADICTING}
        if self.status == EvidenceStatus.CONFLICTING and not opposing.issubset(relations):
            raise ValueError("conflicting requires distinct supporting and contrary evidence")
        if self.status in (EvidenceStatus.MET, EvidenceStatus.NOT_MET):
            if self.unresolved_reasons:
                raise ValueError("resolved findings cannot hide unresolved reasons")
            if opposing.issubset(relations):
                raise ValueError("opposing evidence must remain a conflicting finding")
        elif not self.unresolved_reasons:
            raise ValueError("unknown findings require an explicit unresolved reason")
        if self.status == EvidenceStatus.MISSING and relations.intersection(opposing):
            raise ValueError("missing cannot contain decisive supporting or contrary evidence")
        return self
