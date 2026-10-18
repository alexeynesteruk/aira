"""Source validity is tested independently of clinical/model interpretation."""

from datetime import UTC, date, datetime

import pytest
from pydantic import BaseModel

from app.evidence import CitationError, CitationResolver, check_predicate, normalize_whitespace
from app.schemas import (
    BoundingBox,
    CandidateCitation,
    ChartFact,
    Criterion,
    DatePredicate,
    DocumentRecord,
    DocumentRole,
    ExtractedPage,
    ExtractionMethod,
    ExtractionRecord,
    FactPolarity,
    LogicalValue,
    NarrativePredicate,
    NumericPredicate,
    PageInventory,
    PageQuality,
    RequestContext,
    TextBlock,
)


def changed[T: BaseModel](model: T, **updates: object) -> T:
    return type(model).model_validate({**model.model_dump(), **updates})


def source(
    document_id: str,
    role: DocumentRole,
    pages: tuple[tuple[str, ...], ...],
) -> tuple[DocumentRecord, ExtractionRecord]:
    digest = "a" * 64 if role == DocumentRole.POLICY else "b" * 64
    document = DocumentRecord(
        document_id=document_id,
        role=role,
        filename=document_id + ".pdf",
        sha256=digest,
        byte_count=100,
        page_count=len(pages),
        pages=tuple(PageInventory(page=n) for n in range(1, len(pages) + 1)),
        created_at=datetime(2026, 10, 18, tzinfo=UTC),
    )
    extraction = ExtractionRecord(
        extraction_id=document_id + "-v1",
        document_id=document_id,
        document_sha256=digest,
        parser_name="artificial-test-blocks",
        parser_version="1",
        configuration_sha256="c" * 64,
        created_at=document.created_at,
        pages=tuple(
            ExtractedPage(
                page=n,
                quality=PageQuality.USABLE,
                method=ExtractionMethod.NATIVE_TEXT,
                blocks=tuple(
                    TextBlock(block_id=f"p{n}b{i}", reading_order=i, text=text)
                    for i, text in enumerate(blocks)
                ),
            )
            for n, blocks in enumerate(pages, 1)
        ),
    )
    return document, extraction


def resolver_for(
    chart: str,
    policy: str = "The right vein diameter must be at least 3.0 mm.",
) -> CitationResolver:
    p, pe = source("policy", DocumentRole.POLICY, ((policy,),))
    c, ce = source("chart", DocumentRole.CHART, ((chart,),))
    return CitationResolver((p, c), (pe, ce))


def citation(document: str, quote: str, page: int = 1) -> CandidateCitation:
    return CandidateCitation(document_id=document, page=page, quote=quote)


def numeric_case(
    text: str = "Right vein diameter is 3.0 mm.",
    value: float = 3.0,
    unit: str = "mm",
    policy_text: str = "The right vein diameter must be at least 3.0 mm.",
) -> tuple[CitationResolver, Criterion, ChartFact]:
    resolver = resolver_for(text, policy_text)
    criterion = Criterion(
        criterion_id="diameter",
        wording=policy_text,
        interpretation="At least the stated diameter for the selected context.",
        sources=(resolver.resolve(citation("policy", policy_text)),),
        predicate=NumericPredicate(operator="gte", threshold=3.0, unit="mm", context="right vein"),
    )
    fact = ChartFact(
        fact_id="measurement",
        proposition="The cited diameter measurement.",
        sources=(resolver.resolve(citation("chart", text)),),
        polarity=FactPolarity.AFFIRMED,
        value=value,
        unit=unit,
        context=("right vein",),
        anatomical_target="vein",
        laterality="right",
    )
    return resolver, criterion, fact


def test_whitespace_resolution_preserves_original_unicode_offsets() -> None:
    text = "α intro\n  Right\u00a0vein\t diameter is 3.0 mm.\n"
    resolver = resolver_for(text)
    span = resolver.resolve(citation("chart", "  Right vein diameter\nis 3.0 mm. "))
    assert span.excerpt == "Right\u00a0vein\t diameter is 3.0 mm."
    assert text[span.start : span.end] == span.excerpt
    assert resolver.validate(span) == span
    normalized = changed(span, excerpt="Right vein diameter is 3.0 mm.")
    assert resolver.validate(normalized).excerpt == span.excerpt
    assert normalize_whitespace("  x\r\n\t y  ") == "x y"


@pytest.mark.parametrize(
    ("quote", "code"),
    [
        ("right vein diameter is 3.0 mm.", "quote_not_found"),
        ("Right vein diameter is 3.1 mm.", "quote_not_found"),
        ("Right vein diameter is 3.0mm.", "quote_not_found"),
        (" \n\t ", "empty_quote"),
    ],
)
def test_resolver_does_not_fuzzy_repair(quote: str, code: str) -> None:
    resolver = resolver_for("Right vein diameter is 3.0 mm.")
    with pytest.raises(CitationError) as error:
        resolver.resolve(citation("chart", quote))
    assert error.value.code == code


@pytest.mark.parametrize("blocks", [("echo echo",), ("echo", "echo"), ("aaaa",)])
def test_repeated_or_overlapping_quote_is_ambiguous(blocks: tuple[str, ...]) -> None:
    document, extraction = source("chart", DocumentRole.CHART, (blocks,))
    resolver = CitationResolver((document,), (extraction,))
    with pytest.raises(CitationError) as error:
        resolver.resolve(citation("chart", "aa" if blocks == ("aaaa",) else "echo"))
    assert error.value.code == "ambiguous_quote"


def test_quote_cannot_cross_blocks_or_search_another_page() -> None:
    document, extraction = source(
        "chart", DocumentRole.CHART, (("first", "second"), ("elsewhere",))
    )
    resolver = CitationResolver((document,), (extraction,))
    for candidate in (citation("chart", "first second"), citation("chart", "elsewhere")):
        with pytest.raises(CitationError, match="not found"):
            resolver.resolve(candidate)
    assert resolver.resolve(citation("chart", "elsewhere", 2)).page == 2


@pytest.mark.parametrize(
    ("update", "code"),
    [
        ({"document_id": "unknown"}, "unknown_document"),
        ({"document_sha256": "d" * 64}, "wrong_hash"),
        ({"extraction_id": "chart-v2"}, "wrong_extraction"),
        ({"page": 2}, "invalid_page"),
        ({"block_id": "invented"}, "unknown_block"),
        ({"start": 1}, "wrong_excerpt"),
        ({"end": 1000}, "invalid_offsets"),
        ({"excerpt": "Invented measurement"}, "wrong_excerpt"),
        ({"bbox": BoundingBox(x0=0.0, y0=0.0, x1=1.0, y1=1.0)}, "wrong_bbox"),
    ],
)
def test_span_identity_and_address_are_enforced(update: dict[str, object], code: str) -> None:
    resolver = resolver_for("Right vein diameter is 3.0 mm.")
    span = resolver.resolve(citation("chart", "Right vein diameter is 3.0 mm."))
    with pytest.raises(CitationError) as error:
        resolver.validate(changed(span, **update))
    assert error.value.code == code


def test_selected_document_prevents_known_other_input_citations() -> None:
    resolver = resolver_for("Right vein diameter is 3.0 mm.")
    with pytest.raises(CitationError, match="different selected input"):
        resolver.resolve(citation("chart", "Right vein"), expected_document_id="policy")
    span = resolver.resolve(citation("chart", "Right vein"))
    with pytest.raises(CitationError, match="different selected input"):
        resolver.validate(span, expected_document_id="policy")


def test_resolver_rejects_wrong_inventory_hash_and_revision_selection() -> None:
    document, extraction = source("chart", DocumentRole.CHART, (("text",),))
    with pytest.raises(CitationError, match="original identity"):
        CitationResolver((document,), (changed(extraction, document_sha256="e" * 64),))
    with pytest.raises(CitationError, match="one extraction"):
        CitationResolver((document,), (extraction, changed(extraction, extraction_id="v2")))
    document2 = changed(
        document, page_count=2, pages=(PageInventory(page=1), PageInventory(page=2))
    )
    with pytest.raises(CitationError, match="every page"):
        CitationResolver((document2,), (extraction,))


def test_unusable_page_is_never_accepted_as_a_citation_source() -> None:
    document, extraction = source("chart", DocumentRole.CHART, (("suspect",),))
    page = changed(extraction.pages[0], quality=PageQuality.NEEDS_OCR)
    resolver = CitationResolver((document,), (changed(extraction, pages=(page,)),))
    with pytest.raises(CitationError) as error:
        resolver.resolve(citation("chart", "suspect"))
    assert error.value.code == "unusable_page"


@pytest.mark.parametrize(
    ("value", "expected"),
    [(2.9, LogicalValue.FALSE), (3.0, LogicalValue.TRUE), (3.1, LogicalValue.TRUE)],
)
def test_numeric_inclusive_boundary(value: float, expected: LogicalValue) -> None:
    resolver, criterion, fact = numeric_case(f"Right vein diameter is {value} mm.", value)
    check = check_predicate(criterion, fact, resolver)
    assert check.logical_value == expected
    assert check.reasons == ()


@pytest.mark.parametrize(
    ("operator", "expected"),
    [("gt", False), ("gte", True), ("lt", False), ("lte", True), ("eq", True)],
)
def test_numeric_operators_have_distinct_boundary_semantics(operator: str, expected: bool) -> None:
    resolver, criterion, fact = numeric_case()
    predicate = NumericPredicate.model_validate(
        {"operator": operator, "threshold": 3.0, "unit": "mm", "context": "right vein"}
    )
    criterion = changed(criterion, predicate=predicate)
    assert check_predicate(criterion, fact, resolver).logical_value == (
        LogicalValue.TRUE if expected else LogicalValue.FALSE
    )


@pytest.mark.parametrize(
    ("text", "claimed", "reason"),
    [
        ("Right vein diameter is 2.7 mm.", 3.4, "unverified_or_ambiguous_numeric_value"),
        ("Right vein diameter is 3.4.", 3.4, "unverified_or_ambiguous_numeric_value"),
        ("Right vein diameter is 3.4 mm and 2.7 mm.", 3.4, "unverified_or_ambiguous_numeric_value"),
        ("Right vein diameter is about 3.4 mm.", 3.4, "non_exact_numeric_statement"),
        ("Right vein diameter is 2.7–3.4 mm.", 3.4, "non_exact_numeric_statement"),
        ("Right vein diameter is less than 3.4 mm.", 3.4, "non_exact_numeric_statement"),
        ("Right vein diameter is not 3.4 mm.", 3.4, "non_exact_numeric_statement"),
        ("Right vein diameter is 1e3 mm.", 3.0, "unverified_or_ambiguous_numeric_value"),
        ("Right vein diameter is 1e-3 mm.", 3.0, "unverified_or_ambiguous_numeric_value"),
        ("Right vein diameter is 3.4 mm Hg.", 3.4, "unverified_or_ambiguous_numeric_value"),
        ("Right vein diameter is 3.4 mm/s.", 3.4, "unverified_or_ambiguous_numeric_value"),
    ],
)
def test_source_must_support_an_exact_unambiguous_number(
    text: str, claimed: float, reason: str
) -> None:
    resolver, criterion, fact = numeric_case(text, claimed)
    check = check_predicate(criterion, fact, resolver)
    assert check.logical_value == LogicalValue.UNKNOWN
    assert reason in check.reasons


def test_units_context_and_policy_threshold_cannot_come_only_from_model_fields() -> None:
    resolver, criterion, fact = numeric_case()
    assert (
        "missing_or_incompatible_fact_unit"
        in check_predicate(criterion, changed(fact, unit="cm"), resolver).reasons
    )
    assert (
        "missing_or_incompatible_fact_unit"
        in check_predicate(criterion, changed(fact, unit=None), resolver).reasons
    )
    assert (
        "unverified_required_context"
        in check_predicate(criterion, changed(fact, context=("left vein",)), resolver).reasons
    )
    wrong_threshold = NumericPredicate(
        operator="gte", threshold=4.0, unit="mm", context="right vein"
    )
    assert (
        "unverified_policy_threshold"
        in check_predicate(changed(criterion, predicate=wrong_threshold), fact, resolver).reasons
    )
    unsupported = NumericPredicate(
        operator="gte", threshold=3.0, unit="months", context="right vein"
    )
    assert (
        "unsupported_policy_unit"
        in check_predicate(changed(criterion, predicate=unsupported), fact, resolver).reasons
    )


def test_awake_context_and_selected_side_are_checked() -> None:
    resolver, criterion, fact = numeric_case("Sleeping right vein diameter is 3.0 mm.")
    awake = NumericPredicate(operator="gte", threshold=3.0, unit="mm", context="awake")
    check = check_predicate(
        changed(criterion, predicate=awake), changed(fact, context=("awake",)), resolver
    )
    assert "unverified_required_context" in check.reasons
    request = RequestContext(laterality="left", anatomical_target="vein")
    assert (
        "unverified_selected_laterality"
        in check_predicate(criterion, fact, resolver, request).reasons
    )


def test_negated_uncertain_or_conflicting_measurements_do_not_become_true() -> None:
    resolver, criterion, fact = numeric_case()
    for altered in (
        changed(fact, polarity=FactPolarity.NEGATED),
        changed(fact, uncertainty=("units disputed",)),
        changed(fact, conflicting_fact_ids=("other",)),
    ):
        assert check_predicate(criterion, altered, resolver).logical_value == LogicalValue.UNKNOWN


def date_case(
    event_day: int = 12, documentation_day: int = 13
) -> tuple[CitationResolver, Criterion, ChartFact]:
    policy = "Right vein observation must occur on or before 2026-10-18."
    event = date(2026, 10, event_day)
    documented = date(2026, 10, documentation_day)
    text = f"Right vein observation date: {event}. Report signed: {documented}."
    resolver = resolver_for(text, policy)
    criterion = Criterion(
        criterion_id="date",
        wording=policy,
        interpretation="Bounded comparison of the stated observation date.",
        sources=(resolver.resolve(citation("policy", policy)),),
        predicate=DatePredicate(
            operator="on_or_before",
            boundary=date(2026, 10, 18),
            date_role="event_date",
            context="right vein",
        ),
    )
    fact = ChartFact(
        fact_id="dated",
        proposition="Dated observation.",
        sources=(resolver.resolve(citation("chart", text)),),
        polarity=FactPolarity.AFFIRMED,
        event_date=event,
        documentation_date=documented,
        context=("right vein",),
    )
    return resolver, criterion, fact


@pytest.mark.parametrize(
    ("operator", "expected"),
    [
        ("before", True),
        ("on_or_before", True),
        ("after", False),
        ("on_or_after", False),
        ("on", False),
    ],
)
def test_supported_date_role_and_operators(operator: str, expected: bool) -> None:
    resolver, criterion, fact = date_case()
    assert isinstance(criterion.predicate, DatePredicate)
    criterion = changed(criterion, predicate=changed(criterion.predicate, operator=operator))
    check = check_predicate(
        criterion, fact, resolver, RequestContext(assessment_cutoff=date(2026, 10, 18))
    )
    assert check.logical_value == (LogicalValue.TRUE if expected else LogicalValue.FALSE)


@pytest.mark.parametrize(
    ("operator", "expected"),
    [
        ("before", False),
        ("on_or_before", True),
        ("after", False),
        ("on_or_after", True),
        ("on", True),
    ],
)
def test_date_operators_at_the_exact_boundary(operator: str, expected: bool) -> None:
    resolver, criterion, fact = date_case(18, 18)
    assert isinstance(criterion.predicate, DatePredicate)
    criterion = changed(criterion, predicate=changed(criterion.predicate, operator=operator))
    check = check_predicate(criterion, fact, resolver)
    assert check.logical_value == (LogicalValue.TRUE if expected else LogicalValue.FALSE)


def test_a_source_verified_date_after_boundary_is_false_without_a_cutoff_conflict() -> None:
    resolver, criterion, fact = date_case(19, 19)
    check = check_predicate(criterion, fact, resolver)
    assert check.logical_value == LogicalValue.FALSE
    assert check.reasons == ()


def test_date_role_source_labels_and_cutoff_are_not_inferred() -> None:
    resolver, criterion, fact = date_case()
    assert isinstance(criterion.predicate, DatePredicate)
    unsupported = changed(criterion.predicate, date_role="last_three_calendar_months")
    assert (
        "unsupported_date_role"
        in check_predicate(changed(criterion, predicate=unsupported), fact, resolver).reasons
    )
    fabricated = changed(fact, event_date=date(2026, 10, 11))
    assert (
        "unverified_or_ambiguous_event_date"
        in check_predicate(criterion, fabricated, resolver).reasons
    )
    request = RequestContext(assessment_cutoff=date(2026, 10, 12))
    assert (
        "documentation_date_after_cutoff"
        in check_predicate(criterion, fact, resolver, request).reasons
    )
    no_date = changed(fact, documentation_date=None)
    assert (
        "missing_availability_date"
        in check_predicate(criterion, no_date, resolver, request).reasons
    )


def test_observation_after_signature_and_cutoff_stays_unresolved() -> None:
    text = "Right vein diameter is 3.0 mm. Observation date: 2026-10-19. Report signed: 2026-10-12."
    resolver, criterion, fact = numeric_case(text)
    fact = changed(fact, event_date=date(2026, 10, 19), documentation_date=date(2026, 10, 12))
    check = check_predicate(
        criterion, fact, resolver, RequestContext(assessment_cutoff=date(2026, 10, 18))
    )
    assert check.logical_value == LogicalValue.UNKNOWN
    assert set(check.reasons) == {"event_after_documentation", "event_date_after_cutoff"}


def test_dated_numeric_observation_at_cutoff_is_supported_without_range_false_positive() -> None:
    text = "Right vein diameter is 3.0 mm. Observation date: 2026-10-18. Report signed: 2026-10-18."
    resolver, criterion, fact = numeric_case(text)
    fact = changed(fact, event_date=date(2026, 10, 18), documentation_date=date(2026, 10, 18))
    check = check_predicate(
        criterion, fact, resolver, RequestContext(assessment_cutoff=date(2026, 10, 18))
    )
    assert check.logical_value == LogicalValue.TRUE
    assert check.reasons == ()


def test_an_unrelated_right_side_quote_cannot_authorize_a_left_side_quantity() -> None:
    text = "Left vein diameter is 3.0 mm. Requested target is right vein."
    resolver, criterion, fact = numeric_case(text)
    predicate = NumericPredicate(operator="gte", threshold=3.0, unit="mm", context="vein")
    fact = changed(
        fact,
        context=("vein",),
        sources=(
            resolver.resolve(citation("chart", "Left vein diameter is 3.0 mm.")),
            resolver.resolve(citation("chart", "Requested target is right vein.")),
        ),
    )
    check = check_predicate(
        changed(criterion, predicate=predicate),
        fact,
        resolver,
        RequestContext(laterality="right", anatomical_target="vein"),
    )
    assert check.logical_value == LogicalValue.UNKNOWN
    assert "quantity_context_not_in_same_passage" in check.reasons


def test_explicit_consecutive_day_duration_uses_its_own_unit_without_calendar_conversion() -> None:
    text = "Compression was completed for 90 consecutive days."
    policy_text = "Compression requires at least 90 consecutive days."
    resolver, criterion, fact = numeric_case(text, 90.0, "consecutive_days", policy_text)
    predicate = NumericPredicate(
        operator="gte", threshold=90.0, unit="consecutive_days", context="compression"
    )
    fact = changed(fact, context=("compression",))
    assert (
        check_predicate(changed(criterion, predicate=predicate), fact, resolver).logical_value
        == LogicalValue.TRUE
    )


def test_unknown_and_narrative_predicates_are_not_deterministic_truth_proofs() -> None:
    resolver, criterion, fact = numeric_case()
    assert (
        "unsupported_predicate"
        in check_predicate(changed(criterion, predicate=None), fact, resolver).reasons
    )
    narrative = NarrativePredicate(question="Does the evidence support the requirement?")
    check = check_predicate(changed(criterion, predicate=narrative), fact, resolver)
    assert check.logical_value == LogicalValue.UNKNOWN
    assert "narrative_requires_judgment" in check.reasons
