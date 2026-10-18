"""Flat provider candidates, deliberately weaker than validated domain records.

These shapes do not resolve citations, validate graphs, or prove evidence support.
WP-05 must verify/adapt their JSON Schema against the selected provider transport.
"""

from typing import Literal

from .base import StrictModel, VersionedModel


class CandidateCitation(StrictModel):
    document_id: str
    page: int
    quote: str


class CandidateRequest(StrictModel):
    procedure: str | None
    procedure_code: str | None
    anatomical_target: str | None
    laterality: str | None
    payer: str | None
    plan: str | None
    service_date: str | None
    assessment_cutoff: str | None


class CandidateFieldSources(StrictModel):
    field: Literal[
        "procedure",
        "procedure_code",
        "anatomical_target",
        "laterality",
        "payer",
        "plan",
        "service_date",
        "assessment_cutoff",
    ]
    citations: tuple[CandidateCitation, ...]


class ScopeCandidate(VersionedModel):
    request: CandidateRequest
    status: Literal["applicable", "mismatch", "unresolved"]
    rationale: str
    citations: tuple[CandidateCitation, ...]
    unresolved_fields: tuple[str, ...]
    field_sources: tuple[CandidateFieldSources, ...] = ()
    policy_path_id: str | None = None


class CandidateCriterion(StrictModel):
    criterion_id: str
    wording: str
    interpretation: str
    citations: tuple[CandidateCitation, ...]
    context: tuple[str, ...]
    predicate_kind: Literal["narrative", "numeric", "date", "unsupported"]
    operator: str | None
    threshold: float | None
    unit: str | None
    date_boundary: str | None
    date_role: str | None


class CandidatePolicyNode(StrictModel):
    node_id: str
    kind: Literal["all", "any", "criterion"]
    children: tuple[str, ...]
    criterion_id: str | None
    citations: tuple[CandidateCitation, ...]


class CandidatePolicySection(StrictModel):
    section_id: str
    heading: str
    citations: tuple[CandidateCitation, ...]
    disposition: Literal["requirements", "context", "out_of_scope", "unresolved"]
    criterion_ids: tuple[str, ...]
    explanation: str


class CandidatePageRole(StrictModel):
    page: int
    use: Literal["requirements", "definitions", "skip"]
    reason: str


class PagePlanCandidate(VersionedModel):
    """Which guideline pages contain rules. An omitted page is still read."""

    pages: tuple[CandidatePageRole, ...]


class PolicyCandidate(VersionedModel):
    title: str
    scope_summary: str
    identifier: str | None
    revision_date: str | None
    effective_from: str | None
    effective_to: str | None
    criteria: tuple[CandidateCriterion, ...]
    nodes: tuple[CandidatePolicyNode, ...]
    root_id: str
    sections: tuple[CandidatePolicySection, ...]
    interpretation_issues: tuple[str, ...]


class CandidateFact(StrictModel):
    fact_id: str
    proposition: str
    citations: tuple[CandidateCitation, ...]
    polarity: Literal["affirmed", "negated", "uncertain"]
    provenance: Literal["direct", "clinician_summary"]
    value: float | None
    unit: str | None
    event_date: str | None
    documentation_date: str | None
    anatomical_target: str | None
    laterality: str | None
    context: tuple[str, ...]
    uncertainty: tuple[str, ...]
    conflicting_fact_ids: tuple[str, ...]


class CandidateEvidenceReference(StrictModel):
    fact_id: str
    relation: Literal["supporting", "contradicting", "context"]


class CandidateFinding(StrictModel):
    criterion_id: str
    status: Literal["met", "not_met", "missing", "conflicting", "needs_review"]
    rationale: str
    evidence: tuple[CandidateEvidenceReference, ...]
    unresolved_reasons: tuple[str, ...]


class EvidenceCandidate(VersionedModel):
    facts: tuple[CandidateFact, ...]
    findings: tuple[CandidateFinding, ...]


class ChartCandidate(VersionedModel):
    facts: tuple[CandidateFact, ...]
    interpretation_issues: tuple[str, ...] = ()


class FindingsCandidate(VersionedModel):
    """Assessment can refer to saved facts but cannot create new ones."""

    findings: tuple[CandidateFinding, ...]
