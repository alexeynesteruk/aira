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

type StageName = Literal["scope", "policy", "evidence"]


@dataclass(frozen=True)
class StageInputs:
    policy_document: DocumentRecord
    chart_document: DocumentRecord
    policy_extraction: ExtractionRecord
    chart_extraction: ExtractionRecord
    request_context: RequestContext | None = None
    annotations: tuple[MetadataAnnotation, ...] = ()


@dataclass(frozen=True)
class ScopeInterpretation:
    request: RequestContext
    applicability: ApplicabilityResult
    usage: StageUsage | None = None


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

    async def policy(self, inputs: StageInputs) -> PolicyInterpretation: ...

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


def render_stage_input(inputs: StageInputs, stage: StageName, policy: Policy | None = None) -> str:
    """Render one stage's model input as compact JSON text.

    Scope reads both documents (policy first), policy reads only the policy
    document, and evidence reads only the chart plus the interpreted criteria.
    A supplied policy is only valid for the evidence stage, which requires it.
    """
    if stage == "evidence" and policy is None:
        raise ValueError("The evidence stage requires the interpreted policy")
    if stage != "evidence" and policy is not None:
        raise ValueError("Only the evidence stage consumes an interpreted policy")
    if stage == "policy":
        documents = [_document(inputs.policy_document, inputs.policy_extraction)]
    elif stage == "scope":
        documents = [
            _document(inputs.policy_document, inputs.policy_extraction),
            _document(inputs.chart_document, inputs.chart_extraction),
        ]
    else:
        documents = [_document(inputs.chart_document, inputs.chart_extraction)]
    packet: dict[str, object] = {
        "input_kind": "native_pdf_text_blocks",
        "selected_request": (_request(inputs.request_context) if inputs.request_context else None),
        "staff_annotations": [_annotation(item) for item in inputs.annotations],
        "documents": documents,
    }
    if policy is not None:
        packet["criteria"] = [_criterion(item) for item in policy.criteria]
    return json.dumps(packet, ensure_ascii=False, separators=(",", ":"))
