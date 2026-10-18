"""Mechanical source checks and deliberately bounded comparisons.

Existence of a citation, a value, or a context label does not prove entailment.
Narrative support and interpretation of policy language remain reviewed judgments.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.schemas import (
    CandidateCitation,
    ChartFact,
    Criterion,
    DatePredicate,
    DocumentRecord,
    DocumentRole,
    EvidenceReference,
    EvidenceRelation,
    EvidenceStatus,
    ExtractionRecord,
    FactPolarity,
    Finding,
    LogicalValue,
    NarrativePredicate,
    NumericPredicate,
    PageQuality,
    Policy,
    RequestContext,
    SourceSpan,
    TextBlock,
)


class CitationError(ValueError):
    """A citation cannot be resolved against the selected source revision."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class EvidenceValidationError(ValueError):
    """Evidence records have invalid cross-record references."""


def normalize_whitespace(text: str) -> str:
    """Collapse Unicode whitespace runs to one ASCII space; trim either edge.

    No case, punctuation, Unicode composition, hyphenation, or spelling repair.
    """
    return " ".join(text.split())


def _normalized_offsets(text: str) -> tuple[str, tuple[int, ...], tuple[int, ...]]:
    characters: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    for match in re.finditer(r"\S+|\s+", text):
        if match.group().isspace():
            if characters:
                characters.append(" ")
                starts.append(match.start())
                ends.append(match.end())
        else:
            for offset in range(match.start(), match.end()):
                characters.append(text[offset])
                starts.append(offset)
                ends.append(offset + 1)
    if characters and characters[-1] == " ":
        characters.pop()
        starts.pop()
        ends.pop()
    return "".join(characters), tuple(starts), tuple(ends)


class CitationResolver:
    """Pin one extraction per document and resolve only within its actual blocks.

    Original byte hashes are supplied by ingestion; this pure class checks their
    agreement, not the bytes themselves. A citation never spans multiple blocks.
    """

    def __init__(
        self,
        documents: Sequence[DocumentRecord],
        extractions: Sequence[ExtractionRecord],
    ) -> None:
        self._documents = {document.document_id: document for document in documents}
        self._extractions = {item.document_id: item for item in extractions}
        if len(self._documents) != len(documents):
            raise CitationError("duplicate_document", "Document identifiers must be unique")
        if len(self._extractions) != len(extractions):
            raise CitationError("ambiguous_revision", "Select one extraction per document")
        if len({item.extraction_id for item in extractions}) != len(extractions):
            raise CitationError("duplicate_extraction", "Extraction identifiers must be unique")
        if self._documents.keys() != self._extractions.keys():
            raise CitationError("missing_extraction", "Each selected document needs its extraction")
        for document_id, extraction in self._extractions.items():
            document = self._documents[document_id]
            if extraction.document_sha256 != document.sha256:
                raise CitationError("wrong_hash", "Extraction does not match original identity")
            if len(extraction.pages) != document.page_count:
                raise CitationError("page_inventory", "Extraction must account for every page")

    def document_id_for_role(self, role: DocumentRole) -> str:
        ids = [key for key, document in self._documents.items() if document.role == role]
        if len(ids) != 1:
            raise CitationError("ambiguous_role", "Select exactly one document for this role")
        return ids[0]

    def _document(
        self, document_id: str, expected_document_id: str | None
    ) -> tuple[DocumentRecord, ExtractionRecord]:
        if expected_document_id is not None and document_id != expected_document_id:
            raise CitationError("wrong_document", "Citation belongs to a different selected input")
        if document_id not in self._documents:
            raise CitationError("unknown_document", "Citation document is not a selected input")
        return self._documents[document_id], self._extractions[document_id]

    @staticmethod
    def _blocks(extraction: ExtractionRecord, page: int) -> tuple[TextBlock, ...]:
        if page < 1 or page > len(extraction.pages):
            raise CitationError("invalid_page", "Citation page is outside the original document")
        selected = extraction.pages[page - 1]
        if selected.quality != PageQuality.USABLE:
            raise CitationError("unusable_page", "Citation page has no accepted usable extraction")
        return selected.blocks

    def resolve(
        self, citation: CandidateCitation, *, expected_document_id: str | None = None
    ) -> SourceSpan:
        """Resolve one unique occurrence on the named page, with original offsets.

        Multiple occurrences, including repeated text within a block, are an
        ambiguity. Ask for a longer quote; never select the first occurrence.
        """
        document, extraction = self._document(citation.document_id, expected_document_id)
        quote = normalize_whitespace(citation.quote)
        if not quote:
            raise CitationError("empty_quote", "Citation quote must contain non-whitespace text")
        matches: list[SourceSpan] = []
        for block in self._blocks(extraction, citation.page):
            normalized, starts, ends = _normalized_offsets(block.text)
            search_from = 0
            while (position := normalized.find(quote, search_from)) != -1:
                start, end = starts[position], ends[position + len(quote) - 1]
                matches.append(
                    SourceSpan(
                        document_id=document.document_id,
                        document_sha256=document.sha256,
                        extraction_id=extraction.extraction_id,
                        page=citation.page,
                        block_id=block.block_id,
                        start=start,
                        end=end,
                        excerpt=block.text[start:end],
                        bbox=block.bbox,
                    )
                )
                if len(matches) > 1:
                    raise CitationError(
                        "ambiguous_quote", "Quote occurs more than once on its page"
                    )
                search_from = position + 1
        if not matches:
            raise CitationError("quote_not_found", "Exact quote was not found on the cited page")
        return matches[0]

    def validate(self, span: SourceSpan, *, expected_document_id: str | None = None) -> SourceSpan:
        """Validate an existing address and return its canonical original excerpt."""
        document, extraction = self._document(span.document_id, expected_document_id)
        if span.document_sha256 != document.sha256:
            raise CitationError("wrong_hash", "Citation hash does not match the selected document")
        if span.extraction_id != extraction.extraction_id:
            raise CitationError("wrong_extraction", "Citation uses a different extraction revision")
        blocks = self._blocks(extraction, span.page)
        block = next((item for item in blocks if item.block_id == span.block_id), None)
        if block is None:
            raise CitationError("unknown_block", "Citation block does not belong to this page")
        if span.start < 0 or span.end <= span.start or span.end > len(block.text):
            raise CitationError(
                "invalid_offsets", "Citation offsets are outside their source block"
            )
        original = block.text[span.start : span.end]
        if normalize_whitespace(original) != normalize_whitespace(span.excerpt):
            raise CitationError("wrong_excerpt", "Excerpt does not match the addressed source span")
        if not normalize_whitespace(original):
            raise CitationError("empty_quote", "Citation must identify non-whitespace source text")
        if span.bbox is not None and span.bbox != block.bbox:
            raise CitationError("wrong_bbox", "Citation geometry must be its source block geometry")
        return SourceSpan(
            document_id=span.document_id,
            document_sha256=span.document_sha256,
            extraction_id=span.extraction_id,
            page=span.page,
            block_id=span.block_id,
            start=span.start,
            end=span.end,
            excerpt=original,
            bbox=block.bbox,
        )

    def validate_policy(self, policy: Policy) -> None:
        expected_id = self.document_id_for_role(DocumentRole.POLICY)
        document, _ = self._document(policy.document_id, expected_id)
        if policy.document_sha256 != document.sha256:
            raise CitationError("wrong_hash", "Policy identity does not match its document")
        for record in (*policy.criteria, *policy.nodes, *policy.sections, *policy.issues):
            for source in record.sources:
                self.validate(source, expected_document_id=expected_id)

    def validate_facts(self, facts: Sequence[ChartFact]) -> None:
        expected_id = self.document_id_for_role(DocumentRole.CHART)
        ids = {fact.fact_id for fact in facts}
        if len(ids) != len(facts):
            raise EvidenceValidationError("Fact identifiers must be unique")
        for fact in facts:
            if not set(fact.conflicting_fact_ids) <= ids:
                raise EvidenceValidationError("A fact references an unknown conflicting fact")
            for source in fact.sources:
                self.validate(source, expected_document_id=expected_id)


@dataclass(frozen=True)
class PredicateCheck:
    logical_value: LogicalValue
    reasons: tuple[str, ...] = ()


# Exact units only. Aliases below are spelling variants, never scale conversions.
_UNITS = {
    "mm": ("mm",),
    "cm": ("cm",),
    "m": ("m",),
    "ms": ("ms",),
    "s": ("s", "second", "seconds"),
    "min": ("min", "minute", "minutes"),
    "h": ("h", "hour", "hours"),
    "days": ("day", "days"),
    "consecutive_days": ("consecutive days",),
    "bpm": ("bpm",),
    "%": ("%",),
}
_NUMBER = r"[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)"
_NON_EXACT = re.compile(
    rf"(?:{_NUMBER}\s*(?:[-–—]|to|through)\s*{_NUMBER})"
    r"|\b(?:approximately|about|roughly|less than|greater than|at least|at most|"
    r"more than|up to|under|over|between|not|no|without|denies|denied)\b|[<>≤≥≈~]",
    re.IGNORECASE,
)
_DATE_LABELS = {
    "event_date": r"(?:event date|observation date)",
    "documentation_date": r"(?:documentation date|report signed|documented)",
}


def _unit(unit: str) -> str | None:
    normalized = normalize_whitespace(unit).casefold()
    for canonical, aliases in _UNITS.items():
        if normalized == canonical or normalized in aliases:
            return canonical
    return None


def _contains(text: str, phrase: str) -> bool:
    return (
        re.search(r"(?<!\w)" + re.escape(phrase.casefold()) + r"(?!\w)", text.casefold())
        is not None
    )


def _quantities(text: str, unit: str) -> tuple[Decimal, ...]:
    units = "|".join(re.escape(alias) for alias in _UNITS[unit])
    pattern = rf"(?<![\w.,+\-])({_NUMBER})\s*(?:{units})(?!\w)"
    return tuple(
        Decimal(match.group(1))
        for match in re.finditer(pattern, text, re.IGNORECASE)
        if not re.match(r"\s*(?:[/^²³]|(?:Hg|H2O|per)\b)", text[match.end() :], re.IGNORECASE)
    )


def _source_texts(sources: Sequence[SourceSpan], resolver: CitationResolver) -> tuple[str, ...]:
    return tuple(normalize_whitespace(resolver.validate(source).excerpt) for source in sources)


def predicate_support_reasons(criterion: Criterion) -> tuple[str, ...]:
    """Known policy-interpretation blockers, separate from missing chart evidence.

    Source spans must already have been resolved. Matching a threshold/date here
    does not prove the model interpreted its operator or governing prose correctly.
    """
    predicate = criterion.predicate
    texts = tuple(normalize_whitespace(source.excerpt) for source in criterion.sources)
    if isinstance(predicate, NumericPredicate):
        unit = _unit(predicate.unit)
        if unit is None:
            return ("unsupported_policy_unit",)
        values = {value for text in texts for value in _quantities(text, unit)}
        if Decimal(str(predicate.threshold)) not in values:
            return ("unverified_policy_threshold",)
    elif isinstance(predicate, DatePredicate):
        if predicate.date_role not in _DATE_LABELS:
            return ("unsupported_date_role",)
        if not any(_contains(text, predicate.boundary.isoformat()) for text in texts):
            return ("unverified_policy_date_boundary",)
    elif predicate is None:
        return ("unsupported_predicate",)
    return ()


def _date_reasons(
    fact: ChartFact, texts: tuple[str, ...], request: RequestContext | None
) -> tuple[str, ...]:
    reasons: list[str] = []
    for role, value in (
        ("event_date", fact.event_date),
        ("documentation_date", fact.documentation_date),
    ):
        if value is None:
            continue
        pattern = rf"\b{_DATE_LABELS[role]}\s*:\s*(\d{{4}}-\d{{2}}-\d{{2}})(?!\d)"
        dates = {
            match.group(1) for text in texts for match in re.finditer(pattern, text, re.IGNORECASE)
        }
        if dates != {value.isoformat()}:
            reasons.append(f"unverified_or_ambiguous_{role}")
    if fact.event_date and fact.documentation_date and fact.event_date > fact.documentation_date:
        reasons.append("event_after_documentation")
    if request and request.assessment_cutoff:
        if fact.documentation_date is None:
            reasons.append("missing_availability_date")
        for role, value in (
            ("event_date", fact.event_date),
            ("documentation_date", fact.documentation_date),
        ):
            if value and value > request.assessment_cutoff:
                reasons.append(f"{role}_after_cutoff")
    return tuple(reasons)


def _context_reasons(
    criterion: Criterion,
    fact: ChartFact,
    texts: tuple[str, ...],
    request: RequestContext | None,
) -> tuple[str, ...]:
    reasons: list[str] = []
    context = {normalize_whitespace(item).casefold() for item in fact.context}
    required = list(criterion.context)
    if isinstance(criterion.predicate, NumericPredicate | DatePredicate):
        required.append(criterion.predicate.context)
    for item in required:
        normalized = normalize_whitespace(item)
        if normalized.casefold() not in context or not any(
            _contains(text, normalized) for text in texts
        ):
            reasons.append("unverified_required_context")
    if request:
        for name in ("anatomical_target", "laterality"):
            selected, observed = getattr(request, name), getattr(fact, name)
            if selected is not None and (
                observed is None
                or normalize_whitespace(selected).casefold()
                != normalize_whitespace(observed).casefold()
                or not any(_contains(text, normalize_whitespace(observed)) for text in texts)
            ):
                reasons.append(f"unverified_selected_{name}")
    return tuple(dict.fromkeys(reasons))


def _known_fact_reasons(fact: ChartFact) -> tuple[str, ...]:
    reasons: list[str] = []
    if fact.uncertainty or fact.polarity == FactPolarity.UNCERTAIN:
        reasons.append("fact_uncertain")
    if fact.conflicting_fact_ids:
        reasons.append("fact_conflict_unresolved")
    return tuple(reasons)


def _compare_numeric(value: Decimal, predicate: NumericPredicate) -> bool:
    boundary = Decimal(str(predicate.threshold))
    match predicate.operator:
        case "gt":
            return value > boundary
        case "gte":
            return value >= boundary
        case "lt":
            return value < boundary
        case "lte":
            return value <= boundary
        case "eq":
            return value == boundary


def _compare_date(value: date, predicate: DatePredicate) -> bool:
    match predicate.operator:
        case "before":
            return value < predicate.boundary
        case "on_or_before":
            return value <= predicate.boundary
        case "after":
            return value > predicate.boundary
        case "on_or_after":
            return value >= predicate.boundary
        case "on":
            return value == predicate.boundary


def check_predicate(
    criterion: Criterion,
    fact: ChartFact,
    resolver: CitationResolver,
    request: RequestContext | None = None,
) -> PredicateCheck:
    """Check one bounded comparison; unsupported or uncertain facts stay unknown.

    Numeric inputs need one explicit, exact quantity in a cited context. Dates
    need an ISO date with a supported role label. No date arithmetic or unit
    conversion is attempted. A valid real passage may still be irrelevant: the
    source-to-requirement association is a separately evaluated judgment.
    """
    policy_id = resolver.document_id_for_role(DocumentRole.POLICY)
    chart_id = resolver.document_id_for_role(DocumentRole.CHART)
    for source in criterion.sources:
        resolver.validate(source, expected_document_id=policy_id)
    for source in fact.sources:
        resolver.validate(source, expected_document_id=chart_id)
    texts = _source_texts(fact.sources, resolver)
    policy_texts = _source_texts(criterion.sources, resolver)
    predicate = criterion.predicate
    reasons = [
        *predicate_support_reasons(criterion),
        *_known_fact_reasons(fact),
        *_context_reasons(criterion, fact, texts, request),
    ]
    reasons.extend(_date_reasons(fact, texts, request))
    if fact.polarity != FactPolarity.AFFIRMED:
        reasons.append("non_affirmed_comparison_value")
    if isinstance(predicate, NumericPredicate):
        unit = _unit(predicate.unit)
        if unit is None:
            reasons.append("unsupported_policy_unit")
        elif fact.unit is None or _unit(fact.unit) != unit:
            reasons.append("missing_or_incompatible_fact_unit")
        elif fact.value is None:
            reasons.append("missing_numeric_value")
        else:
            quantity_texts = tuple(text for text in texts if _quantities(text, unit))
            values = {value for text in quantity_texts for value in _quantities(text, unit)}
            if values != {Decimal(str(fact.value))}:
                reasons.append("unverified_or_ambiguous_numeric_value")
            # ISO date separators are not numeric ranges. Dates are checked by role above.
            if any(
                _NON_EXACT.search(re.sub(r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)", "[date]", text))
                for text in quantity_texts
            ):
                reasons.append("non_exact_numeric_statement")
            same_passage_context = [predicate.context, *criterion.context]
            if request:
                same_passage_context.extend(
                    selected
                    for selected in (request.anatomical_target, request.laterality)
                    if selected is not None
                )
            if not any(
                all(_contains(text, normalize_whitespace(item)) for item in same_passage_context)
                for text in quantity_texts
            ):
                reasons.append("quantity_context_not_in_same_passage")
            policy_values = {value for text in policy_texts for value in _quantities(text, unit)}
            if Decimal(str(predicate.threshold)) not in policy_values:
                reasons.append("unverified_policy_threshold")
        if not reasons and fact.value is not None:
            passed = _compare_numeric(Decimal(str(fact.value)), predicate)
            return PredicateCheck(LogicalValue.TRUE if passed else LogicalValue.FALSE)
    elif isinstance(predicate, DatePredicate):
        if predicate.date_role not in _DATE_LABELS:
            reasons.append("unsupported_date_role")
        else:
            value = (
                fact.event_date if predicate.date_role == "event_date" else fact.documentation_date
            )
            if value is None:
                reasons.append("missing_date_value")
            if not any(_contains(text, predicate.boundary.isoformat()) for text in policy_texts):
                reasons.append("unverified_policy_date_boundary")
            if not reasons and value is not None:
                passed = _compare_date(value, predicate)
                return PredicateCheck(LogicalValue.TRUE if passed else LogicalValue.FALSE)
    elif isinstance(predicate, NarrativePredicate):
        reasons.append("narrative_requires_judgment")
    else:
        reasons.append("unsupported_predicate")
    return PredicateCheck(LogicalValue.UNKNOWN, tuple(dict.fromkeys(reasons)))


def require_saved_fact_mapping(
    saved: Sequence[ChartFact],
    findings: Sequence[Finding],
    proposed: Sequence[ChartFact] | None = None,
) -> tuple[ChartFact, ...]:
    """Return the saved facts unchanged.

    Assessment may cite those fact IDs. It cannot add, drop, or rewrite a fact.
    The returned tuple is the saved facts, so a rejected proposal cannot replace them.
    """
    saved_facts = tuple(saved)
    by_id = {fact.fact_id: fact for fact in saved_facts}
    if len(by_id) != len(saved_facts):
        raise EvidenceValidationError("Saved chart facts must have unique identifiers")
    for finding in findings:
        for reference in finding.evidence:
            if reference.fact_id not in by_id:
                raise EvidenceValidationError("Finding references an unknown fact")
    if proposed is not None:
        proposed_facts = tuple(proposed)
        if {fact.fact_id for fact in proposed_facts} != set(by_id) or len(proposed_facts) != len(
            saved_facts
        ):
            raise EvidenceValidationError("Assessment cannot add, remove, or rename chart facts")
        for fact in proposed_facts:
            original = by_id[fact.fact_id]
            if fact.model_dump(mode="json") != original.model_dump(mode="json"):
                raise EvidenceValidationError("Assessment cannot rewrite a saved chart fact")
    return saved_facts


def validate_findings(
    policy: Policy,
    facts: Sequence[ChartFact],
    findings: Sequence[Finding],
    resolver: CitationResolver,
    request: RequestContext | None = None,
) -> tuple[Finding, ...]:
    """Validate domain references and guard resolved candidate judgments.

    This is not provider-candidate conversion. Existing missing/conflicting/review
    findings remain unresolved. For resolved numeric/date findings, recompute the
    comparison and evidence relation; never silently trust the model's number.
    """
    resolver.validate_policy(policy)
    resolver.validate_facts(facts)
    criteria = {item.criterion_id: item for item in policy.criteria}
    by_fact = {fact.fact_id: fact for fact in facts}
    by_finding = {finding.criterion_id: finding for finding in findings}
    if len(by_finding) != len(findings) or by_finding.keys() != criteria.keys():
        raise EvidenceValidationError("Exactly one finding is required for every policy criterion")
    validated: list[Finding] = []
    for finding in findings:
        if any(reference.fact_id not in by_fact for reference in finding.evidence):
            raise EvidenceValidationError("Finding references an unknown fact")
        criterion = criteria[finding.criterion_id]
        if finding.status not in (EvidenceStatus.MET, EvidenceStatus.NOT_MET):
            validated.append(finding)
            continue
        reasons: list[str] = []
        checks: list[PredicateCheck] = []
        references: list[EvidenceReference] = []
        for reference in finding.evidence:
            fact = by_fact[reference.fact_id]
            if reference.relation == EvidenceRelation.CONTEXT:
                references.append(reference)
                continue
            if isinstance(criterion.predicate, NarrativePredicate):
                texts = _source_texts(fact.sources, resolver)
                reasons.extend(_known_fact_reasons(fact))
                reasons.extend(_context_reasons(criterion, fact, texts, request))
                reasons.extend(_date_reasons(fact, texts, request))
                references.append(reference)
            else:
                check = check_predicate(criterion, fact, resolver, request)
                checks.append(check)
                reasons.extend(check.reasons)
                relation = {
                    LogicalValue.TRUE: EvidenceRelation.SUPPORTING,
                    LogicalValue.FALSE: EvidenceRelation.CONTRADICTING,
                    LogicalValue.UNKNOWN: EvidenceRelation.CONTEXT,
                }[check.logical_value]
                references.append(EvidenceReference(fact_id=fact.fact_id, relation=relation))
        values = {check.logical_value for check in checks}
        if reasons:
            status = EvidenceStatus.NEEDS_REVIEW
        elif values == {LogicalValue.TRUE, LogicalValue.FALSE}:
            status = EvidenceStatus.CONFLICTING
            reasons.append("incompatible_comparison_results")
        elif checks:
            status = EvidenceStatus.MET if values == {LogicalValue.TRUE} else EvidenceStatus.NOT_MET
        else:
            validated.append(finding)
            continue
        rationale = (
            "Mechanical validation requires review: " + ", ".join(dict.fromkeys(reasons))
            if reasons
            else "The source-verified bounded comparison is " + status.value + "."
        )
        validated.append(
            Finding(
                criterion_id=finding.criterion_id,
                status=status,
                rationale=rationale,
                evidence=tuple(references),
                unresolved_reasons=tuple(dict.fromkeys(reasons)),
            )
        )
    return tuple(validated)
