"""Stage contracts and the rendered text a stage actually consumes.

The StageInterpreter protocol is the workflow's model boundary: implementations
return typed interpretations, never provider response envelopes. Provenance
(hashes, source spans, block identifiers, geometry, and extraction revisions)
stays in storage as the audit trail; the model reads page-ordered native block
text plus the staff-supplied request context only. The evidence stage
additionally receives the interpreted policy criteria.
"""

import json
from dataclasses import dataclass
from datetime import date
from typing import Literal, Protocol

from app.schemas import (
    ApplicabilityResult,
    ChartData,
    ChartFact,
    Criterion,
    DocumentRecord,
    ExtractionRecord,
    Finding,
    MetadataAnnotation,
    OperationalError,
    Policy,
    RequestContext,
    ReviewIssue,
    StageUsage,
)

type StageName = Literal[
    "scope",
    "policy",
    "policy_index",
    "policy_page",
    "policy_section",
    "policy_reconcile",
    "policy_merge",
    "policy_audit",
    "chart",
    "evidence",
]


@dataclass(frozen=True)
class DocumentInputs:
    """An extraction process has access to exactly one original document."""

    document: DocumentRecord
    extraction: ExtractionRecord


@dataclass(frozen=True)
class ChartInterpretation:
    chart: ChartData
    usage: StageUsage | None = None


@dataclass(frozen=True)
class StageInputs:
    policy_document: DocumentRecord
    chart_document: DocumentRecord
    policy_extraction: ExtractionRecord
    chart_extraction: ExtractionRecord
    request_context: RequestContext | None = None
    annotations: tuple[MetadataAnnotation, ...] = ()
    policy: Policy | None = None
    chart: ChartData | None = None


@dataclass(frozen=True)
class ScopeInterpretation:
    request: RequestContext
    applicability: ApplicabilityResult
    usage: StageUsage | None = None
    policy_path_id: str | None = None


@dataclass(frozen=True)
class PolicyInterpretation:
    policy: Policy
    usage: StageUsage | None = None


@dataclass(frozen=True)
class EvidenceInterpretation:
    facts: tuple[ChartFact, ...]
    findings: tuple[Finding, ...]
    issues: tuple[ReviewIssue, ...] = ()
    usage: StageUsage | None = None


class StageInterpreter(Protocol):
    async def scope(self, inputs: StageInputs) -> ScopeInterpretation: ...

    async def policy(self, inputs: DocumentInputs) -> PolicyInterpretation: ...

    async def chart(self, inputs: DocumentInputs) -> ChartInterpretation: ...

    async def evidence(self, inputs: StageInputs, policy: Policy) -> EvidenceInterpretation: ...


class InterpretationFailure(Exception):
    """Safe provider/conversion failure retaining reported usage, even on failure."""

    def __init__(self, error: OperationalError, usage: StageUsage | None = None):
        super().__init__(error.message)
        self.error = error
        self.usage = usage


def _request(request: RequestContext) -> dict[str, object]:
    return {
        "procedure": request.procedure,
        "procedure_code": request.procedure_code,
        "anatomical_target": request.anatomical_target,
        "laterality": request.laterality,
        "payer": request.payer,
        "plan": request.plan,
        "service_date": request.service_date.isoformat() if request.service_date else None,
        "assessment_cutoff": (
            request.assessment_cutoff.isoformat() if request.assessment_cutoff else None
        ),
        "unresolved_fields": [field.value for field in request.unresolved_fields],
    }


def _annotation(annotation: MetadataAnnotation) -> dict[str, object]:
    value: object = annotation.value
    if isinstance(value, date):
        value = value.isoformat()
    return {
        "field": annotation.field,
        "value": value,
        "resolves_conflict": annotation.resolves_conflict,
        "resolution_reason": annotation.resolution_reason,
    }


def _document(document: DocumentRecord, extraction: ExtractionRecord) -> dict[str, object]:
    return {
        "document_id": document.document_id,
        "role": document.role.value,
        "filename": document.filename,
        "page_count": document.page_count,
        "pages": [
            {
                "page": page.page,
                "quality": page.quality.value,
                "blocks": [block.text for block in page.blocks],
            }
            for page in extraction.pages
        ],
    }


def _criterion(criterion: Criterion) -> dict[str, object]:
    return {
        "criterion_id": criterion.criterion_id,
        "wording": criterion.wording,
        "interpretation": criterion.interpretation,
        "context": list(criterion.context),
        "predicate": (criterion.predicate.model_dump(mode="json") if criterion.predicate else None),
    }


def _sourced(value: object) -> object:
    """Render saved interpretations with original quotes but no parser internals."""
    if isinstance(value, dict):
        result: dict[str, object] = {}
        for key, item in value.items():
            if key == "sources" and isinstance(item, list):
                result["citations"] = [
                    {
                        "document_id": source["document_id"],
                        "page": source["page"],
                        "quote": source["excerpt"],
                    }
                    for source in item
                ]
            elif key not in {"document_sha256", "policy_id"}:
                result[key] = _sourced(item)
        return result
    if isinstance(value, list):
        return [_sourced(item) for item in value]
    return value


def render_document_input(inputs: DocumentInputs) -> str:
    return json.dumps(
        {
            "input_kind": "pdf_text_blocks",
            "documents": [_document(inputs.document, inputs.extraction)],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _scope_policy(policy: Policy) -> dict[str, object]:
    """Paths and criterion wording for applicability.

    The compiled review ledger and executable nodes repeat quotes already stored
    on the paths and criteria. Sending those copies pushes a full guideline past
    the stage character limit. Evaluation still applies every saved review issue.
    """
    rendered = _sourced(policy.model_dump(mode="json"))
    if not isinstance(rendered, dict):
        raise ValueError("A policy rendering must be an object")
    for name in ("issues", "nodes", "sections"):
        rendered.pop(name, None)
    return rendered


def render_stage_input(
    inputs: StageInputs | DocumentInputs, stage: StageName, policy: Policy | None = None
) -> str:
    """Document extraction is isolated; assessment consumes saved interpretations."""
    if isinstance(inputs, DocumentInputs):
        if stage not in ("policy", "chart") or policy is not None:
            raise ValueError("Document inputs are only valid for policy or chart extraction")
        return render_document_input(inputs)
    # Kept for experiment/test callers; no request or annotations enter extraction.
    if stage in ("policy", "chart"):
        if policy is not None:
            raise ValueError("Only the evidence stage accepts a policy argument")
        own = (
            DocumentInputs(inputs.policy_document, inputs.policy_extraction)
            if stage == "policy"
            else DocumentInputs(inputs.chart_document, inputs.chart_extraction)
        )
        return render_document_input(own)
    if stage == "scope" and policy is not None:
        raise ValueError("Only the evidence stage accepts a policy argument")
    if stage == "evidence" and policy is None:
        raise ValueError("The evidence stage requires the interpreted policy")
    selected_policy = policy if stage == "evidence" else inputs.policy
    if stage == "scope" and inputs.chart is None:
        documents = [_document(inputs.chart_document, inputs.chart_extraction)]
        if selected_policy is None:
            documents.insert(0, _document(inputs.policy_document, inputs.policy_extraction))
        packet: dict[str, object] = {
            "input_kind": "native_pdf_text_blocks",
            "selected_request": _request(inputs.request_context)
            if inputs.request_context
            else None,
            "staff_annotations": [_annotation(item) for item in inputs.annotations],
            "documents": documents,
        }
        if selected_policy is not None:
            packet["policy"] = _scope_policy(selected_policy)
        return json.dumps(packet, ensure_ascii=False, separators=(",", ":"))
    if stage == "evidence" and inputs.chart is None and selected_policy is not None:
        return json.dumps(
            {
                "input_kind": "native_pdf_text_blocks",
                "selected_request": (
                    _request(inputs.request_context) if inputs.request_context else None
                ),
                "staff_annotations": [_annotation(item) for item in inputs.annotations],
                "documents": [_document(inputs.chart_document, inputs.chart_extraction)],
                "criteria": [_criterion(item) for item in selected_policy.criteria],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    if selected_policy is None or inputs.chart is None:
        raise ValueError("Assessment requires the saved policy and chart interpretations")
    packet = {
        "input_kind": "saved_document_interpretations",
        "selected_request": _request(inputs.request_context) if inputs.request_context else None,
        "staff_annotations": [_annotation(item) for item in inputs.annotations],
        "chart": _sourced(inputs.chart.model_dump(mode="json")),
    }
    if stage == "scope":
        packet["policy"] = _scope_policy(selected_policy)
    else:
        packet["criteria"] = [_criterion(item) for item in selected_policy.criteria]
    return json.dumps(packet, ensure_ascii=False, separators=(",", ":"))
