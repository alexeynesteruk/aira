"""Provider transport values are untrusted until source and domain checks pass.

This module has no provider, HTTP, storage, or workflow side effects. Conversion
does not prove semantic entailment or discover omitted policy prose.
"""

import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import date

from pydantic import ValidationError

from app.evidence import (
    CitationError,
    CitationResolver,
    normalize_whitespace,
    predicate_support_reasons,
    validate_findings,
)
from app.schemas import (
    AllNode,
    AnyNode,
    ApplicabilityResult,
    ApplicabilityStatus,
    CandidateCitation,
    CandidateCriterion,
    CandidateFact,
    CandidateRequest,
    ChartCandidate,
    ChartData,
    ChartFact,
    ClarificationField,
    Criterion,
    CriterionNode,
    DatePredicate,
    DocumentRole,
    ErrorCode,
    EvidenceCandidate,
    EvidenceReference,
    EvidenceRelation,
    EvidenceStatus,
    FactPolarity,
    FactProvenance,
    FieldSources,
    Finding,
    FindingsCandidate,
    IssueCategory,
    MetadataAnnotation,
    NarrativePredicate,
    NumericPredicate,
    OperationalError,
    Policy,
    PolicyCandidate,
    PolicyNode,
    PolicyScopeField,
    PolicySection,
    Predicate,
    RequestContext,
    RequestField,
    ReviewIssue,
    RunPhase,
    ScopeCandidate,
    SourceSpan,
    StrictModel,
)


class CandidateConversionError(ValueError):
    """Operationally invalid stage output; never represented as missing evidence."""

    def __init__(self, code: ErrorCode, phase: RunPhase, reason: str) -> None:
        super().__init__(reason)
        self.error = OperationalError(
            code=code,
            stage=phase,
            message=reason,
            retryable=False,
            action="Retry the assessment. This attempt is kept.",
        )


@contextmanager
def _guard(phase: RunPhase) -> Iterator[None]:
    try:
        yield
    except CandidateConversionError:
        raise
    except CitationError as error:
        raise CandidateConversionError(
            ErrorCode.CITATION_INVALID, phase, "Candidate citation failed: " + error.code
        ) from error
    except ValidationError as error:
        locations = ", ".join(
            ".".join(str(part) for part in item["loc"]) for item in error.errors()
        )
        raise CandidateConversionError(
            ErrorCode.INVALID_OUTPUT,
            phase,
            "Candidate violates the domain contract at: " + locations,
        ) from error
    except ValueError as error:
        raise CandidateConversionError(ErrorCode.INVALID_OUTPUT, phase, str(error)) from error


def _date(value: str | None, field: str) -> date | None:
    if value is None:
        return None
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        raise ValueError(field + " requires a literal ISO calendar date YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(field + " is not a valid calendar date") from error


def _citations(
    candidates: Sequence[CandidateCitation],
    resolver: CitationResolver,
    document_id: str | None,
    *,
    required: bool = True,
) -> tuple[SourceSpan, ...]:
    if required and not candidates:
        raise ValueError("This domain record requires its own source citations")
    return tuple(
        resolver.resolve(candidate, expected_document_id=document_id) for candidate in candidates
    )


def _clarification(value: str) -> ClarificationField:
    try:
        return RequestField(value)
    except ValueError:
        try:
            return PolicyScopeField(value)
        except ValueError as error:
            raise ValueError("Scope references an unknown clarification field") from error


class ScopeConversion(StrictModel):
    request: RequestContext
    extracted_request: RequestContext
    applicability: ApplicabilityResult
    annotations: tuple[MetadataAnnotation, ...] = ()


class EvidenceConversion(StrictModel):
    facts: tuple[ChartFact, ...]
    findings: tuple[Finding, ...]
    candidate_findings: tuple[Finding, ...]


def _request_values(
    request: CandidateRequest,
) -> tuple[dict[str, object], tuple[RequestField, ...]]:
    """Parse request fields. An unreadable date becomes an unresolved field.

    Service date and assessment cutoff must be literal YYYY-MM-DD values. A
    missing date stays null. A present value that is not that form is not a
    failed run: staff can read the chart and enter the date.
    """
    values: dict[str, object] = {}
    unreadable: list[RequestField] = []
    for field in RequestField:
        raw = getattr(request, field.value)
        if field in (RequestField.SERVICE_DATE, RequestField.ASSESSMENT_CUTOFF):
            try:
                values[field.value] = _date(raw, field.value)
            except ValueError:
                values[field.value] = None
                unreadable.append(field)
        else:
            values[field.value] = raw
    return values, tuple(unreadable)


def _unreadable_date_message(fields: Sequence[ClarificationField]) -> str:
    labels = {
        RequestField.SERVICE_DATE: "service date",
        RequestField.ASSESSMENT_CUTOFF: "assessment cutoff",
    }
    names = [labels[field] for field in fields]
    if len(names) == 1:
        subject, verb = f"The {names[0]}", "was"
    else:
        subject, verb = "The " + " and ".join(names), "were"
    return (
        f"{subject} {verb} not a calendar date in YYYY-MM-DD form. "
        "Enter the date from the chart to continue."
    )


def _same_value(left: object, right: object) -> bool:
    if isinstance(left, str) and isinstance(right, str):
        return normalize_whitespace(left).casefold() == normalize_whitespace(right).casefold()
    return left == right


def convert_scope(
    candidate: ScopeCandidate,
    resolver: CitationResolver,
    annotations: Sequence[MetadataAnnotation] = (),
) -> ScopeConversion:
    """Convert scoped request metadata, preserving source and staff provenance.

    Every extracted non-null field needs its own chart citations. A candidate
    value may instead exactly match an explicit staff annotation without a chart
    citation; it then remains absent from extracted_request. A changed cited value
    invalidates the candidate scope judgment and requires scope reassessment.
    """
    with _guard(RunPhase.CHECKING_APPLICABILITY):
        chart_id = resolver.document_id_for_role(DocumentRole.CHART)
        policy_id = resolver.document_id_for_role(DocumentRole.POLICY)
        selected, unreadable_dates = _request_values(candidate.request)
        original = dict(selected)
        named = tuple(_clarification(field) for field in candidate.unresolved_fields)
        if len(set(named)) != len(named):
            raise ValueError("Scope clarification fields must be unique")
        if candidate.status != "unresolved" and named:
            raise ValueError("A resolved scope cannot list unresolved fields")
        unresolved = tuple(dict.fromkeys((*named, *unreadable_dates)))
        annotation_by_field = {annotation.field: annotation for annotation in annotations}
        if len(annotation_by_field) != len(annotations):
            raise ValueError("Submit one selected annotation per metadata field")
        if len({annotation.annotation_id for annotation in annotations}) != len(annotations):
            raise ValueError("Annotation identifiers must be unique")
        for annotation in annotations:
            for source in annotation.original_sources:
                resolver.validate(source, expected_document_id=chart_id)
        sources: list[FieldSources] = []
        seen: set[RequestField] = set()
        for record in candidate.field_sources:
            field = RequestField(record.field)
            if field in seen:
                raise ValueError("Request field sources must be grouped once per field")
            seen.add(field)
            if selected[field.value] is None and field not in unresolved:
                raise ValueError("A null cited field must be explicitly unresolved")
            sources.append(
                FieldSources(field=field, sources=_citations(record.citations, resolver, chart_id))
            )
        by_source = {record.field.value: record.sources for record in sources}
        for field in RequestField:
            value = selected[field.value]
            if value is not None and field not in seen:
                staff_value = annotation_by_field.get(field.value)
                if staff_value is None or not _same_value(value, staff_value.value):
                    raise ValueError(
                        "An extracted request value lacks field-level source citations"
                    )
                original[field.value] = None
        changed_fields: list[RequestField] = []
        for annotation in annotations:
            field = RequestField(annotation.field)
            old_value = original[field.value]
            field_sources = by_source.get(field.value, ())
            differs = old_value is not None and not _same_value(old_value, annotation.value)
            known_conflict = bool(field_sources) and field in unresolved
            if differs or known_conflict:
                if not annotation.resolves_conflict or not annotation.resolution_reason:
                    raise ValueError(
                        "A conflicting metadata choice needs an explicit resolution reason"
                    )
                preserved = {
                    resolver.validate(source, expected_document_id=chart_id).model_dump_json()
                    for source in annotation.original_sources
                }
                if any(source.model_dump_json() not in preserved for source in field_sources):
                    raise ValueError("Metadata conflict resolution must preserve all field sources")
            # A staff date replaces an unreadable model value. That is the
            # clarification itself, not a new scope conflict.
            if field not in unreadable_dates and not _same_value(
                selected[field.value], annotation.value
            ):
                changed_fields.append(field)
            selected[field.value] = annotation.value
        source_request = RequestContext.model_validate(
            {
                **original,
                "field_sources": tuple(sources),
                "unresolved_fields": tuple(
                    field for field in unresolved if isinstance(field, RequestField)
                ),
            }
        )
        request_unresolved = tuple(
            field
            for field in source_request.unresolved_fields
            if field.value not in annotation_by_field
        )
        request = RequestContext.model_validate(
            {**selected, "field_sources": tuple(sources), "unresolved_fields": request_unresolved}
        )
        scope_sources = _citations(candidate.citations, resolver, None, required=False)
        if candidate.status != "unresolved":
            if policy_id not in {source.document_id for source in scope_sources}:
                raise ValueError("A resolved scope judgment requires cited policy scope")
            if not annotations and chart_id not in {source.document_id for source in scope_sources}:
                raise ValueError("A resolved scope judgment requires cited request evidence")
        open_unresolved = tuple(
            field for field in unresolved if field.value not in annotation_by_field
        )
        pending_dates = tuple(field for field in open_unresolved if field in unreadable_dates)
        applicability = ApplicabilityResult(
            status=ApplicabilityStatus(candidate.status),
            rationale=candidate.rationale,
            sources=scope_sources,
            unresolved_fields=open_unresolved if candidate.status == "unresolved" else (),
        )
        if pending_dates:
            applicability = ApplicabilityResult(
                status=ApplicabilityStatus.UNRESOLVED,
                rationale=_unreadable_date_message(pending_dates),
                sources=scope_sources,
                unresolved_fields=open_unresolved,
            )
        elif changed_fields:
            applicability = ApplicabilityResult(
                status=ApplicabilityStatus.UNRESOLVED,
                rationale=(
                    "Selected metadata changed after the candidate scope judgment; reassess scope."
                ),
                sources=scope_sources,
                unresolved_fields=tuple(dict.fromkeys((*open_unresolved, *changed_fields))),
            )
        if applicability.status == ApplicabilityStatus.APPLICABLE and request.procedure is None:
            raise ValueError("Applicable scope requires one selected procedure")
        return ScopeConversion(
            request=request,
            extracted_request=source_request,
            applicability=applicability,
            annotations=tuple(annotations),
        )


def _predicate(candidate: CandidateCriterion) -> tuple[Predicate | None, str | None]:
    boundary = _date(candidate.date_boundary, "date_boundary")
    if candidate.predicate_kind == "unsupported":
        return None, "The policy condition has unsupported semantics and requires interpretation."
    if candidate.predicate_kind == "narrative":
        if any(
            value is not None
            for value in (
                candidate.operator,
                candidate.threshold,
                candidate.unit,
                candidate.date_boundary,
                candidate.date_role,
            )
        ):
            raise ValueError(
                "A narrative predicate must not carry hidden numeric or date operators"
            )
        return NarrativePredicate(question=candidate.interpretation), None
    if not candidate.context:
        return None, "The comparison has no explicit source-bound context."
    if candidate.predicate_kind == "numeric":
        if candidate.date_boundary is not None or candidate.date_role is not None:
            raise ValueError("A numeric predicate must not carry date parameters")
        if candidate.operator not in {"gt", "gte", "lt", "lte", "eq"}:
            return None, "The numeric comparison operator is unsupported."
        if candidate.threshold is None or candidate.unit is None:
            return None, "The numeric comparison lacks an explicit threshold or unit."
        return NumericPredicate.model_validate(
            {
                "operator": candidate.operator,
                "threshold": candidate.threshold,
                "unit": candidate.unit,
                "context": candidate.context[0],
            }
        ), None
    if candidate.threshold is not None or candidate.unit is not None:
        raise ValueError("A date predicate must not carry numeric parameters")
    if candidate.operator not in {"before", "on_or_before", "after", "on_or_after", "on"}:
        return None, "The date comparison operator is unsupported."
    if boundary is None or candidate.date_role is None:
        return None, "The date comparison lacks an explicit boundary or role."
    return DatePredicate.model_validate(
        {
            "operator": candidate.operator,
            "boundary": boundary,
            "date_role": candidate.date_role,
            "context": candidate.context[0],
        }
    ), None


def convert_policy(
    candidate: PolicyCandidate, resolver: CitationResolver, *, policy_id: str
) -> Policy:
    """Resolve every governing record, enforce graph shape, and expose known blockers."""
    with _guard(RunPhase.INTERPRETING_POLICY):
        document_id = resolver.document_id_for_role(DocumentRole.POLICY)
        criteria: list[Criterion] = []
        issues: list[ReviewIssue] = []
        for index, item in enumerate(candidate.criteria):
            sources = _citations(item.citations, resolver, document_id)
            predicate, unsupported = _predicate(item)
            criterion = Criterion(
                criterion_id=item.criterion_id,
                wording=item.wording,
                interpretation=item.interpretation,
                sources=sources,
                context=item.context,
                predicate=predicate,
            )
            criteria.append(criterion)
            reasons = predicate_support_reasons(criterion)
            if unsupported or reasons:
                issues.append(
                    ReviewIssue(
                        issue_id=f"conversion-criterion-{index:04d}",
                        category=IssueCategory.INTERPRETATION,
                        message=unsupported
                        or "Unsupported or unverified policy predicate: " + ", ".join(reasons),
                        action=(
                            "Review the cited governing condition before using a favorable result."
                        ),
                        blocks_readiness=True,
                        sources=sources,
                        criterion_ids=(criterion.criterion_id,),
                    )
                )
        nodes: list[PolicyNode] = []
        for node in candidate.nodes:
            sources = _citations(node.citations, resolver, document_id)
            if node.kind == "criterion":
                if node.children or node.criterion_id is None:
                    raise ValueError("A criterion node needs one criterion ID and no children")
                nodes.append(
                    CriterionNode(
                        node_id=node.node_id, criterion_id=node.criterion_id, sources=sources
                    )
                )
            else:
                if node.criterion_id is not None:
                    raise ValueError("A logical group cannot also identify a criterion")
                node_class = AllNode if node.kind == "all" else AnyNode
                nodes.append(
                    node_class(node_id=node.node_id, children=node.children, sources=sources)
                )
        sections = tuple(
            PolicySection(
                section_id=item.section_id,
                heading=item.heading,
                sources=_citations(item.citations, resolver, document_id),
                disposition=item.disposition,
                criterion_ids=item.criterion_ids,
                explanation=item.explanation,
            )
            for item in candidate.sections
        )
        covered = {
            criterion_id
            for section in sections
            if section.disposition == "requirements"
            for criterion_id in section.criterion_ids
        }
        if covered != {criterion.criterion_id for criterion in criteria}:
            raise ValueError("Requirement sections must account for every extracted criterion")
        issues.extend(
            ReviewIssue(
                issue_id=f"conversion-interpretation-{index:04d}",
                category=IssueCategory.INTERPRETATION,
                message=message,
                action="Review the unresolved policy interpretation.",
                blocks_readiness=True,
            )
            for index, message in enumerate(candidate.interpretation_issues)
        )
        if not criteria:
            raise ValueError("An interpreted policy must contain at least one criterion")
        policy = Policy(
            policy_id=policy_id,
            document_id=document_id,
            document_sha256=criteria[0].sources[0].document_sha256,
            title=candidate.title,
            scope_summary=candidate.scope_summary,
            identifier=candidate.identifier,
            revision_date=_date(candidate.revision_date, "revision_date"),
            effective_from=_date(candidate.effective_from, "effective_from"),
            effective_to=_date(candidate.effective_to, "effective_to"),
            criteria=tuple(criteria),
            nodes=tuple(nodes),
            root_id=candidate.root_id,
            sections=sections,
            issues=tuple(issues),
        )
        resolver.validate_policy(policy)
        return policy


def _facts(
    candidates: Sequence[CandidateFact], resolver: CitationResolver
) -> tuple[ChartFact, ...]:
    chart_id = resolver.document_id_for_role(DocumentRole.CHART)
    return tuple(
        ChartFact(
            fact_id=item.fact_id,
            proposition=item.proposition,
            sources=_citations(item.citations, resolver, chart_id),
            polarity=FactPolarity(item.polarity),
            provenance=FactProvenance(item.provenance),
            value=item.value,
            unit=item.unit,
            event_date=_date(item.event_date, "event_date"),
            documentation_date=_date(item.documentation_date, "documentation_date"),
            anatomical_target=item.anatomical_target,
            laterality=item.laterality,
            context=item.context,
            uncertainty=item.uncertainty,
            conflicting_fact_ids=item.conflicting_fact_ids,
        )
        for item in candidates
    )


def convert_evidence(
    candidate: EvidenceCandidate,
    policy: Policy,
    resolver: CitationResolver,
    request: RequestContext | None = None,
) -> EvidenceConversion:
    """Convert source-grounded facts and validate findings without staff clinical edits."""
    with _guard(RunPhase.MAPPING_EVIDENCE):
        facts = _facts(candidate.facts, resolver)
        findings = tuple(
            Finding(
                criterion_id=item.criterion_id,
                status=EvidenceStatus(item.status),
                rationale=item.rationale,
                evidence=tuple(
                    EvidenceReference(
                        fact_id=reference.fact_id, relation=EvidenceRelation(reference.relation)
                    )
                    for reference in item.evidence
                ),
                unresolved_reasons=item.unresolved_reasons,
            )
            for item in candidate.findings
        )
        validated = validate_findings(policy, facts, findings, resolver, request)
        return EvidenceConversion(facts=facts, findings=validated, candidate_findings=findings)


def convert_chart(
    candidate: ChartCandidate, resolver: CitationResolver, *, document_sha256: str
) -> ChartData:
    with _guard(RunPhase.EXTRACTING_CHART):
        facts = _facts(candidate.facts, resolver)
        document = resolver.document_id_for_role(DocumentRole.CHART)
        # Resolve the original hash even when the chart contains no facts.
        return ChartData(
            document_id=document,
            document_sha256=document_sha256,
            facts=facts,
            interpretation_issues=candidate.interpretation_issues,
        )


def convert_findings(
    candidate: FindingsCandidate,
    policy: Policy,
    facts: tuple[ChartFact, ...],
    resolver: CitationResolver,
    request: RequestContext | None = None,
) -> EvidenceConversion:
    with _guard(RunPhase.MAPPING_EVIDENCE):
        findings = tuple(
            Finding(
                criterion_id=item.criterion_id,
                status=EvidenceStatus(item.status),
                rationale=item.rationale,
                evidence=tuple(
                    EvidenceReference(fact_id=ref.fact_id, relation=EvidenceRelation(ref.relation))
                    for ref in item.evidence
                ),
                unresolved_reasons=item.unresolved_reasons,
            )
            for item in candidate.findings
        )
        validated = validate_findings(policy, facts, findings, resolver, request)
        return EvidenceConversion(facts=facts, findings=validated, candidate_findings=findings)
