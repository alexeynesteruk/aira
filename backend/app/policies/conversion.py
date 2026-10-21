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
    PolicyPath,
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
        details: list[str] = []
        for item in error.errors()[:8]:
            location = ".".join(str(part) for part in item["loc"])
            detail = f"{location}: {item['msg']}"
            bad = item.get("input")
            if bad is not None and not isinstance(bad, (dict, list, tuple)):
                text = str(bad)
                if len(text) > 80:
                    text = text[:77] + "..."
                detail += f" (received {text!r})"
            details.append(detail)
        raise CandidateConversionError(
            ErrorCode.INVALID_OUTPUT,
            phase,
            "Candidate violates the domain contract at: " + "; ".join(details),
        ) from error
    except ValueError as error:
        raise CandidateConversionError(ErrorCode.INVALID_OUTPUT, phase, str(error)) from error


# A model date that is not literal YYYY-MM-DD is staff work, not a failed extraction.
DATE_CONFIRMATION = (
    "This condition depends on a date, and that date was not given as a literal "
    "calendar date (YYYY-MM-DD)."
)
DATE_CONFIRMATION_ACTION = (
    "Confirm the calendar date (YYYY-MM-DD) from the cited text. "
    "This condition stays unresolved until that date is explicit."
)
POLICY_DATE_CONFIRMATION = (
    "A guideline revision or effective date was not given as a literal calendar date (YYYY-MM-DD)."
)
POLICY_DATE_ACTION = (
    "Confirm that date from the guideline metadata before relying on the policy version."
)
CHART_DATE_CONFIRMATION = (
    "Chart fact {fact_id} uses a date that was not given as a literal calendar date "
    "(YYYY-MM-DD). Confirm that date from the chart before a date comparison can use it."
)


def _date(value: str | None, field: str) -> date | None:
    if value is None:
        return None
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        raise ValueError(field + " requires a literal ISO calendar date YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(field + " is not a valid calendar date") from error


def _literal_date(value: str | None) -> tuple[date | None, bool]:
    """Read one optional date. The second value is true when text was not usable."""
    if value is None:
        return None, False
    try:
        return _date(value, "date"), False
    except ValueError:
        return None, True


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


def _scope_span(
    candidate: CandidateCitation,
    resolver: CitationResolver,
    document_id: str | None,
) -> SourceSpan | None:
    """Resolve one scope or chart citation without trusting an invented block id.

    Those packets show the quote and page, not a reliable block id. A block id
    that is not on that page is ignored once, and the same quote is resolved on
    that same page. A unique match keeps the real block. A quote that is missing
    or still ambiguous is omitted. Other citation failures still raise. This does
    not search another page or join blocks. Policy rules still use strict
    resolution.
    """
    try:
        return resolver.resolve(candidate, expected_document_id=document_id)
    except CitationError as error:
        if error.code != "unknown_block" or not candidate.block_id:
            raise
    try:
        return resolver.resolve(
            candidate.model_copy(update={"block_id": None}),
            expected_document_id=document_id,
        )
    except CitationError as error:
        if error.code in {"quote_not_found", "ambiguous_quote"}:
            return None
        raise


def _scope_spans(
    candidates: Sequence[CandidateCitation],
    resolver: CitationResolver,
    document_id: str | None,
) -> tuple[SourceSpan, ...]:
    spans: list[SourceSpan] = []
    for candidate in candidates:
        span = _scope_span(candidate, resolver, document_id)
        if span is not None:
            spans.append(span)
    return tuple(spans)


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


_OMITTED_CITATION = (
    "A cited chart statement was not kept because its quote did not match one block "
    "on the cited page."
)


def chart_omission_issue(notes: Sequence[str]) -> ReviewIssue | None:
    """A dropped chart statement must block a favorable checklist.

    Date confirmations stay non-blocking. A fact that was removed, or kept
    without one of its citations or conflict partners, is a completeness gap.
    """
    if not any("was not kept" in note for note in notes):
        return None
    return ReviewIssue(
        issue_id="chart-facts-not-kept",
        category=IssueCategory.COMPLETENESS,
        message=(
            "One or more chart statements were not kept because a citation did not "
            "match one block on the cited page. Review the chart before using a "
            "favorable result."
        ),
        action="Open the cited page and confirm the omitted statement.",
        blocks_readiness=True,
    )


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _present_text(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(text for value in values if (text := value.strip()))


def _filled(value: str, fallback: str) -> tuple[str, bool]:
    text = value.strip()
    if text:
        return text, False
    return fallback, True


def _field_label(field: RequestField) -> str:
    labels = {
        RequestField.PROCEDURE: "procedure",
        RequestField.PROCEDURE_CODE: "procedure code",
        RequestField.ANATOMICAL_TARGET: "anatomical target",
        RequestField.LATERALITY: "laterality",
        RequestField.PAYER: "payer",
        RequestField.PLAN: "plan",
        RequestField.SERVICE_DATE: "service date",
        RequestField.ASSESSMENT_CUTOFF: "assessment cutoff",
    }
    return labels[field]


def _unsourced_field_message(fields: Sequence[RequestField]) -> str:
    names = [_field_label(field) for field in fields]
    if len(names) == 1:
        return (
            f"The {names[0]} was not kept because it had no chart citation. "
            "Confirm it from the chart to continue."
        )
    listed = " and ".join(names)
    return (
        f"The {listed} were not kept because they had no chart citation. "
        "Confirm them from the chart to continue."
    )


def _unreadable_date_message(fields: Sequence[ClarificationField]) -> str:
    labels: dict[ClarificationField, str] = {
        RequestField.SERVICE_DATE: "service date",
        RequestField.ASSESSMENT_CUTOFF: "assessment cutoff",
    }
    names = [labels[RequestField(field.value)] for field in fields]
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

    Every kept chart-derived field needs its own chart citations. A value with
    none is dropped and named for staff; scope quotes are not copied onto it.
    A candidate value may instead exactly match an explicit staff annotation
    without a chart citation; it then remains absent from extracted_request.
    A changed cited value invalidates the candidate scope judgment and requires
    scope reassessment. An applicable judgment cannot stand on a dropped field.
    A cited mismatch can. Unreadable dates and unsourced fields remain on the
    request, and they do not replace that mismatch. A block id that is not on
    the cited page is not a source address: the quote is kept only when it
    occurs once on that page.
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
        claimed: set[RequestField] = set()
        for record in candidate.field_sources:
            field = RequestField(record.field)
            if field in claimed:
                raise ValueError("Request field sources must be grouped once per field")
            claimed.add(field)
            if not record.citations:
                raise ValueError("This domain record requires its own source citations")
            # An unknown block id is recovered or omitted inside _scope_spans.
            # A field whose quotes then have no remaining citation is unsourced.
            resolved = _scope_spans(record.citations, resolver, chart_id)
            if not resolved:
                continue
            seen.add(field)
            if selected[field.value] is None and field not in unresolved:
                raise ValueError("A null cited field must be explicitly unresolved")
            sources.append(FieldSources(field=field, sources=resolved))
        by_source = {record.field.value: record.sources for record in sources}
        # A value with no chart citation is not kept, and the scope quotes are not
        # borrowed to supply one. Staff can confirm the field. A cited mismatch can stand.
        unsourced: list[RequestField] = []
        for field in RequestField:
            value = selected[field.value]
            if value is None or field in seen:
                continue
            staff_value = annotation_by_field.get(field.value)
            if staff_value is not None and _same_value(value, staff_value.value):
                original[field.value] = None
                continue
            selected[field.value] = None
            original[field.value] = None
            unsourced.append(field)
        unresolved = tuple(dict.fromkeys((*unresolved, *unsourced)))
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
        scope_sources = _scope_spans(candidate.citations, resolver, None)
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
        if changed_fields:
            applicability = ApplicabilityResult(
                status=ApplicabilityStatus.UNRESOLVED,
                rationale=(
                    "Selected metadata changed after the candidate scope judgment; reassess scope."
                ),
                sources=scope_sources,
                unresolved_fields=tuple(dict.fromkeys((*open_unresolved, *changed_fields))),
            )
        elif pending_dates and candidate.status != "mismatch":
            # A missing calendar date cannot turn a cited procedure or payer
            # mismatch back into an open request. Applicable scope still waits.
            applicability = ApplicabilityResult(
                status=ApplicabilityStatus.UNRESOLVED,
                rationale=_unreadable_date_message(pending_dates),
                sources=scope_sources,
                unresolved_fields=open_unresolved,
            )
        elif unsourced and candidate.status == "applicable":
            applicability = ApplicabilityResult(
                status=ApplicabilityStatus.UNRESOLVED,
                rationale=_unsourced_field_message(unsourced),
                sources=scope_sources,
                unresolved_fields=tuple(dict.fromkeys((*open_unresolved, *unsourced))),
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
    boundary, unreadable_date = _literal_date(candidate.date_boundary)
    if unreadable_date:
        # Keep the cited condition. Staff confirm the date; the other rules continue.
        return None, DATE_CONFIRMATION
    if candidate.predicate_kind == "unsupported":
        return None, "The policy condition has unsupported semantics and requires interpretation."
    if candidate.predicate_kind == "narrative":
        hidden = [
            name
            for name, value in (
                ("operator", candidate.operator),
                ("threshold", candidate.threshold),
                ("unit", candidate.unit),
                ("date_boundary", candidate.date_boundary),
                ("date_role", candidate.date_role),
            )
            if value is not None
        ]
        # Structured output often fills every slot. Do not apply those values,
        # and do not discard the cited requirement.
        note = None
        if hidden:
            note = (
                f"Criterion {candidate.criterion_id} was labeled narrative but also set "
                f"{', '.join(hidden)}. Those fields were not applied. Review the cited "
                "wording before treating this as a numeric or date rule."
            )
        return NarrativePredicate(question=candidate.interpretation), note
    if not candidate.context:
        return None, "The comparison has no explicit source-bound context."
    if candidate.predicate_kind == "numeric":
        if candidate.operator not in {"gt", "gte", "lt", "lte", "eq"}:
            return None, "The numeric comparison operator is unsupported."
        if candidate.threshold is None or candidate.unit is None:
            return None, "The numeric comparison lacks an explicit threshold or unit."
        stray_dates = [
            name
            for name, value in (
                ("date_boundary", candidate.date_boundary),
                ("date_role", candidate.date_role),
            )
            if value is not None
        ]
        note = None
        if stray_dates:
            note = (
                f"Criterion {candidate.criterion_id} is numeric but also set "
                f"{', '.join(stray_dates)}. Those date fields were not applied."
            )
        return NumericPredicate.model_validate(
            {
                "operator": candidate.operator,
                "threshold": candidate.threshold,
                "unit": candidate.unit,
                "context": candidate.context[0],
            }
        ), note
    stray_numbers = [
        name
        for name, value in (("threshold", candidate.threshold), ("unit", candidate.unit))
        if value is not None
    ]
    if candidate.operator not in {"before", "on_or_before", "after", "on_or_after", "on"}:
        return None, "The date comparison operator is unsupported."
    if boundary is None or candidate.date_role is None:
        return None, "The date comparison lacks an explicit boundary or role."
    note = None
    if stray_numbers:
        note = (
            f"Criterion {candidate.criterion_id} is a date comparison but also set "
            f"{', '.join(stray_numbers)}. Those numeric fields were not applied."
        )
    return DatePredicate.model_validate(
        {
            "operator": candidate.operator,
            "boundary": boundary,
            "date_role": candidate.date_role,
            "context": candidate.context[0],
        }
    ), note


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
                            DATE_CONFIRMATION_ACTION
                            if unsupported == DATE_CONFIRMATION
                            else (
                                "Review the cited governing condition before using a "
                                "favorable result."
                            )
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
            elif not node.children and node.criterion_id is not None:
                # The kind says group, but the only link is a criterion.
                nodes.append(
                    CriterionNode(
                        node_id=node.node_id, criterion_id=node.criterion_id, sources=sources
                    )
                )
            else:
                if not node.children:
                    raise ValueError("A logical group needs at least one child")
                # Models often fill criterion_id on an AND/OR node. The kind is the group.
                node_class = AllNode if node.kind == "all" else AnyNode
                nodes.append(
                    node_class(node_id=node.node_id, children=node.children, sources=sources)
                )
        built_sections: list[PolicySection] = []
        for index, section in enumerate(candidate.sections):
            heading, heading_missing = _filled(section.heading, "Untitled section")
            explanation, explanation_missing = _filled(
                section.explanation, "The section explanation was not extracted."
            )
            if heading_missing or explanation_missing:
                issues.append(
                    ReviewIssue(
                        issue_id=f"conversion-section-label-{index:04d}",
                        category=IssueCategory.INTERPRETATION,
                        message=(
                            f"Section {section.section_id} did not include a heading or "
                            "explanation. A placeholder was kept with its citations."
                        ),
                        action=(
                            "Confirm the section heading from the guideline before using "
                            "a favorable result."
                        ),
                        blocks_readiness=True,
                        sources=_citations(section.citations, resolver, document_id),
                    )
                )
            built_sections.append(
                PolicySection(
                    section_id=section.section_id,
                    heading=heading,
                    sources=_citations(section.citations, resolver, document_id),
                    disposition=section.disposition,
                    criterion_ids=section.criterion_ids,
                    explanation=explanation,
                )
            )
        sections = tuple(built_sections)
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
        heading = next(
            (item.heading.strip() for item in candidate.sections if item.heading.strip()),
            "",
        )
        title, title_missing = _filled(candidate.title, heading or "Untitled extracted section")
        scope_summary, scope_missing = _filled(
            candidate.scope_summary, "The section scope was not extracted."
        )
        if title_missing or scope_missing:
            missing = [
                name
                for name, absent in (("title", title_missing), ("scope", scope_missing))
                if absent
            ]
            issues.append(
                ReviewIssue(
                    issue_id="conversion-policy-label",
                    category=IssueCategory.INTERPRETATION,
                    message=(
                        "The extracted section did not include a "
                        + " and ".join(missing)
                        + ". A placeholder was kept so the cited rules remain reviewable."
                    ),
                    action=(
                        "Confirm the section label from the guideline before using "
                        "a favorable result."
                    ),
                    blocks_readiness=True,
                )
            )
        revision_date, revision_unreadable = _literal_date(candidate.revision_date)
        effective_from, effective_from_unreadable = _literal_date(candidate.effective_from)
        effective_to, effective_to_unreadable = _literal_date(candidate.effective_to)
        if revision_unreadable or effective_from_unreadable or effective_to_unreadable:
            issues.append(
                ReviewIssue(
                    issue_id="conversion-policy-date",
                    category=IssueCategory.INTERPRETATION,
                    message=POLICY_DATE_CONFIRMATION,
                    action=POLICY_DATE_ACTION,
                    blocks_readiness=True,
                    # The candidate carries no citation for the metadata field, so
                    # do not attach an unrelated criterion passage to this issue.
                    sources=(),
                )
            )
        paths: list[PolicyPath] = []
        for index, path in enumerate(candidate.paths):
            path_title, path_title_missing = _filled(
                path.title, path.path_id.strip() or f"Untitled path {index + 1}"
            )
            path_scope, path_scope_missing = _filled(
                path.scope, "The path scope was not extracted."
            )
            if path_title_missing or path_scope_missing:
                issues.append(
                    ReviewIssue(
                        issue_id=f"conversion-path-label-{index:04d}",
                        category=IssueCategory.INTERPRETATION,
                        message=(
                            f"Policy path {path.path_id or index + 1} did not include a "
                            "title or scope. A placeholder was kept with its citations."
                        ),
                        action=(
                            "Confirm the path label from the guideline before using "
                            "a favorable result."
                        ),
                        blocks_readiness=True,
                        sources=_citations(path.citations, resolver, document_id),
                    )
                )
            paths.append(
                PolicyPath(
                    path_id=path.path_id,
                    title=path_title,
                    scope=path_scope,
                    root_id=path.root_id,
                    sources=_citations(path.citations, resolver, document_id),
                )
            )
        policy = Policy(
            policy_id=policy_id,
            document_id=document_id,
            document_sha256=criteria[0].sources[0].document_sha256,
            title=title,
            scope_summary=scope_summary,
            # The prompt forbids empty strings where null belongs. A blank policy
            # number is not an identifier; it must not fail an otherwise valid section.
            identifier=(
                candidate.identifier
                if candidate.identifier and candidate.identifier.strip()
                else None
            ),
            revision_date=revision_date,
            effective_from=effective_from,
            effective_to=effective_to,
            criteria=tuple(criteria),
            nodes=tuple(nodes),
            root_id=candidate.root_id,
            sections=sections,
            issues=tuple(issues),
            paths=tuple(paths),
        )
        resolver.validate_policy(policy)
        return policy


def _facts(
    candidates: Sequence[CandidateFact],
    resolver: CitationResolver,
) -> tuple[tuple[ChartFact, ...], tuple[str, ...]]:
    chart_id = resolver.document_id_for_role(DocumentRole.CHART)
    notes: list[str] = []
    kept: list[
        tuple[CandidateFact, tuple[SourceSpan, ...], str, date | None, date | None, bool]
    ] = []
    for item in candidates:
        if not item.citations:
            raise ValueError("This domain record requires its own source citations")
        sources = _scope_spans(item.citations, resolver, chart_id)
        omitted = len(item.citations) - len(sources)
        if not sources:
            notes.append(
                f"Chart fact {item.fact_id} was not kept because its citation did not "
                "match one block on the cited page."
            )
            continue
        if omitted:
            notes.append(
                f"Chart fact {item.fact_id} was not kept in full because a citation did not "
                "match one block on the cited page."
            )
        proposition = item.proposition.strip()
        if not proposition:
            notes.append(f"Chart fact {item.fact_id} was not kept because it had no statement.")
            continue
        event_date, event_unreadable = _literal_date(item.event_date)
        documentation_date, documentation_unreadable = _literal_date(item.documentation_date)
        if event_unreadable or documentation_unreadable:
            notes.append(CHART_DATE_CONFIRMATION.format(fact_id=item.fact_id))
        kept.append((item, sources, proposition, event_date, documentation_date, omitted > 0))
    candidate_fact_ids = {item.fact_id for item in candidates}
    for item in candidates:
        if not set(item.conflicting_fact_ids) <= candidate_fact_ids:
            raise ValueError("Conflict fact references an unknown candidate fact")
    kept_ids = {item.fact_id for item, *_ in kept}
    facts = []
    for item, sources, proposition, event_date, documentation_date, omitted_citation in kept:
        uncertainty = list(_present_text(item.uncertainty))
        conflicts = tuple(fact_id for fact_id in item.conflicting_fact_ids if fact_id in kept_ids)
        if omitted_citation or len(conflicts) != len(item.conflicting_fact_ids):
            uncertainty.append(_OMITTED_CITATION)
        facts.append(
            ChartFact(
                fact_id=item.fact_id,
                proposition=proposition,
                sources=sources,
                polarity=FactPolarity(item.polarity),
                provenance=FactProvenance(item.provenance),
                value=item.value,
                unit=_optional_text(item.unit),
                event_date=event_date,
                documentation_date=documentation_date,
                anatomical_target=_optional_text(item.anatomical_target),
                laterality=_optional_text(item.laterality),
                context=_present_text(item.context),
                uncertainty=tuple(dict.fromkeys(uncertainty)),
                conflicting_fact_ids=conflicts,
            )
        )
    return tuple(facts), tuple(dict.fromkeys(notes))


def convert_chart(
    candidate: ChartCandidate, resolver: CitationResolver, *, document_sha256: str
) -> ChartData:
    with _guard(RunPhase.EXTRACTING_CHART):
        facts, date_notes = _facts(candidate.facts, resolver)
        document = resolver.document_id_for_role(DocumentRole.CHART)
        # Resolve the original hash even when the chart contains no facts.
        return ChartData(
            document_id=document,
            document_sha256=document_sha256,
            facts=facts,
            interpretation_issues=(*candidate.interpretation_issues, *date_notes),
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
