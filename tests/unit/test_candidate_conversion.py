"""Provider-shaped candidates exercise domain conversion without provider calls."""

from datetime import UTC, date, datetime

import pytest
from pydantic import BaseModel, ValidationError

from app.assessment import evaluate_policy
from app.evidence import CitationResolver
from app.policies import (
    CandidateConversionError,
    EvidenceConversion,
    convert_chart,
    convert_findings,
    convert_policy,
    convert_scope,
)
from app.policies.conversion import chart_omission_issue
from app.schemas import (
    ApplicabilityStatus,
    AssessmentOutcome,
    CandidateCitation,
    CandidateCriterion,
    CandidateEvidenceReference,
    CandidateFact,
    CandidateFieldSources,
    CandidateFinding,
    CandidatePolicyNode,
    CandidatePolicySection,
    CandidateRequest,
    ChartCandidate,
    DateAnnotation,
    DocumentRecord,
    DocumentRole,
    ErrorCode,
    EvidenceCandidate,
    EvidenceRelation,
    EvidenceStatus,
    ExtractedPage,
    ExtractionMethod,
    ExtractionRecord,
    FactProvenance,
    FindingsCandidate,
    NarrativePredicate,
    NumericPredicate,
    PageInventory,
    PageQuality,
    Policy,
    PolicyCandidate,
    RequestContext,
    RequestField,
    RunPhase,
    ScopeCandidate,
    TextAnnotation,
    TextBlock,
)
from app.schemas.provider import CandidatePolicyPath

NOW = datetime(2026, 10, 18, tzinfo=UTC)
POLICY = (
    "Payer: Fixture Health. Plan: Vascular. Policy applies to endovenous ablation. "
    "Revised: 2026-10-01. Right vein diameter must be at least 3.0 mm. "
    "Observation must be on or before 2026-10-18. Both requirements apply."
)
CHART = (
    "Payer: Fixture Health. Plan: Vascular. Requested procedure: endovenous ablation. "
    "Right vein diameter is 2.7 mm. Observation date: 2026-10-12. "
    "Report signed: 2026-10-13. Service date: 2026-10-28."
)


def changed[T: BaseModel](model: T, **updates: object) -> T:
    return type(model).model_validate({**model.model_dump(), **updates})


def citation(quote: str, document: str = "policy") -> CandidateCitation:
    return CandidateCitation(document_id=document, page=1, quote=quote)


@pytest.fixture
def resolver() -> CitationResolver:
    documents = []
    extractions = []
    for document_id, role, text, digest in (
        ("policy", DocumentRole.POLICY, POLICY, "a" * 64),
        ("chart", DocumentRole.CHART, CHART, "b" * 64),
    ):
        documents.append(
            DocumentRecord(
                document_id=document_id,
                role=role,
                filename=document_id + ".pdf",
                sha256=digest,
                byte_count=100,
                page_count=1,
                pages=(PageInventory(page=1),),
                created_at=NOW,
            )
        )
        extractions.append(
            ExtractionRecord(
                extraction_id=document_id + "-v1",
                document_id=document_id,
                document_sha256=digest,
                parser_name="artificial-contract-blocks",
                parser_version="1",
                configuration_sha256="c" * 64,
                created_at=NOW,
                pages=(
                    ExtractedPage(
                        page=1,
                        quality=PageQuality.USABLE,
                        method=ExtractionMethod.NATIVE_TEXT,
                        blocks=(TextBlock(block_id="p1", text=text, reading_order=0),),
                    ),
                ),
            )
        )
    return CitationResolver(documents, extractions)


def scope_candidate() -> ScopeCandidate:
    request = CandidateRequest(
        procedure="endovenous ablation",
        procedure_code=None,
        anatomical_target=None,
        laterality=None,
        payer="Fixture Health",
        plan="Vascular",
        service_date="2026-10-28",
        assessment_cutoff=None,
    )
    return ScopeCandidate(
        request=request,
        status="applicable",
        rationale="The cited payer, plan, and procedure match.",
        citations=(
            citation(
                "Payer: Fixture Health. Plan: Vascular. Policy applies to endovenous ablation."
            ),
            citation(
                "Payer: Fixture Health. Plan: Vascular. Requested procedure: endovenous ablation.",
                "chart",
            ),
        ),
        unresolved_fields=(),
        field_sources=(
            CandidateFieldSources(
                field="procedure",
                citations=(citation("Requested procedure: endovenous ablation.", "chart"),),
            ),
            CandidateFieldSources(
                field="payer", citations=(citation("Payer: Fixture Health.", "chart"),)
            ),
            CandidateFieldSources(field="plan", citations=(citation("Plan: Vascular.", "chart"),)),
            CandidateFieldSources(
                field="service_date", citations=(citation("Service date: 2026-10-28.", "chart"),)
            ),
        ),
    )


def policy_candidate() -> PolicyCandidate:
    criterion = CandidateCriterion(
        criterion_id="diameter",
        wording="Right vein diameter must be at least 3.0 mm.",
        interpretation="The selected right vein diameter is at least 3.0 mm.",
        citations=(citation("Right vein diameter must be at least 3.0 mm."),),
        context=("right vein",),
        predicate_kind="numeric",
        operator="gte",
        threshold=3.0,
        unit="mm",
        date_boundary=None,
        date_role=None,
    )
    return PolicyCandidate(
        title="Fixture policy",
        scope_summary="Fixture Health Vascular endovenous ablation.",
        identifier="fixture-policy",
        revision_date="2026-10-01",
        effective_from=None,
        effective_to=None,
        criteria=(criterion,),
        nodes=(
            CandidatePolicyNode(
                node_id="root",
                kind="criterion",
                children=(),
                criterion_id="diameter",
                citations=criterion.citations,
            ),
        ),
        root_id="root",
        sections=(
            CandidatePolicySection(
                section_id="requirements",
                heading="Diameter",
                citations=criterion.citations,
                disposition="requirements",
                criterion_ids=("diameter",),
                explanation="The stated requirement.",
            ),
        ),
        interpretation_issues=(),
    )


def evidence_candidate() -> EvidenceCandidate:
    fact = CandidateFact(
        fact_id="measurement",
        proposition="The chart reports the right vein diameter.",
        citations=(citation("Right vein diameter is 2.7 mm.", "chart"),),
        polarity="affirmed",
        provenance="direct",
        value=2.7,
        unit="mm",
        event_date=None,
        documentation_date=None,
        anatomical_target="vein",
        laterality="right",
        context=("right vein",),
        uncertainty=(),
        conflicting_fact_ids=(),
    )
    finding = CandidateFinding(
        criterion_id="diameter",
        status="met",
        rationale="The candidate mistakenly calls the measurement sufficient.",
        evidence=(CandidateEvidenceReference(fact_id="measurement", relation="supporting"),),
        unresolved_reasons=(),
    )
    return EvidenceCandidate(facts=(fact,), findings=(finding,))


def convert_chart_and_findings(
    candidate: EvidenceCandidate,
    policy: Policy,
    resolver: CitationResolver,
    request: RequestContext | None = None,
) -> EvidenceConversion:
    """Run the production chart-build then findings-mapping stages in sequence.

    Facts are prepared from the chart document alone, then findings are mapped
    onto those saved facts. This mirrors the independent WP-19 assessment path
    instead of re-deriving facts during evidence mapping.
    """
    chart = convert_chart(
        ChartCandidate(facts=candidate.facts),
        resolver,
        document_sha256="b" * 64,
    )
    return convert_findings(
        FindingsCandidate(findings=candidate.findings),
        policy,
        chart.facts,
        resolver,
        request,
    )


def assert_invalid(error: pytest.ExceptionInfo[CandidateConversionError], phase: RunPhase) -> None:
    assert error.value.error.code == ErrorCode.INVALID_OUTPUT
    assert error.value.error.stage == phase
    assert error.value.error.retryable is False
    assert error.value.error.action


def test_scope_has_field_sources_and_does_not_invent_missing_context(
    resolver: CitationResolver,
) -> None:
    candidate = scope_candidate()
    before = candidate.model_dump_json()
    converted = convert_scope(candidate, resolver)
    assert converted.request == converted.extracted_request
    assert converted.request.service_date == date(2026, 10, 28)
    assert converted.request.assessment_cutoff is None
    assert converted.request.procedure_code is None
    assert {item.field for item in converted.request.field_sources} == {
        RequestField.PROCEDURE,
        RequestField.PAYER,
        RequestField.PLAN,
        RequestField.SERVICE_DATE,
    }
    assert converted.applicability.status == ApplicabilityStatus.APPLICABLE
    assert candidate.model_dump_json() == before


def test_missing_field_citations_cannot_borrow_aggregate_scope_quotes(
    resolver: CitationResolver,
) -> None:
    candidate = scope_candidate()
    converted = convert_scope(changed(candidate, field_sources=()), resolver)
    assert converted.request.field_sources == ()
    assert converted.request.procedure is None
    assert converted.request.payer is None
    assert converted.request.plan is None
    assert converted.request.service_date is None
    assert converted.extracted_request.procedure is None
    assert converted.applicability.status == ApplicabilityStatus.UNRESOLVED
    assert RequestField.PROCEDURE in converted.applicability.unresolved_fields
    assert "chart citation" in converted.applicability.rationale
    assert converted.applicability.sources
    assert "endovenous ablation" not in converted.applicability.rationale


def blocks_resolver(
    *,
    policy_blocks: tuple[tuple[str, str], ...],
    chart_blocks: tuple[tuple[str, str], ...],
) -> CitationResolver:
    documents = []
    extractions = []
    for document_id, role, blocks, digest in (
        ("policy", DocumentRole.POLICY, policy_blocks, "a" * 64),
        ("chart", DocumentRole.CHART, chart_blocks, "b" * 64),
    ):
        documents.append(
            DocumentRecord(
                document_id=document_id,
                role=role,
                filename=document_id + ".pdf",
                sha256=digest,
                byte_count=100,
                page_count=1,
                pages=(PageInventory(page=1),),
                created_at=NOW,
            )
        )
        extractions.append(
            ExtractionRecord(
                extraction_id=document_id + "-v1",
                document_id=document_id,
                document_sha256=digest,
                parser_name="artificial-contract-blocks",
                parser_version="1",
                configuration_sha256="c" * 64,
                created_at=NOW,
                pages=(
                    ExtractedPage(
                        page=1,
                        quality=PageQuality.USABLE,
                        method=ExtractionMethod.NATIVE_TEXT,
                        blocks=tuple(
                            TextBlock(block_id=block_id, text=text, reading_order=index)
                            for index, (block_id, text) in enumerate(blocks)
                        ),
                    ),
                ),
            )
        )
    return CitationResolver(documents, extractions)


def test_an_unknown_scope_block_keeps_the_unique_quote_on_that_page(
    resolver: CitationResolver,
) -> None:
    candidate = scope_candidate()
    invented = "p0001.b00030"

    def with_block(item: CandidateCitation) -> CandidateCitation:
        return changed(item, block_id=invented)

    converted = convert_scope(
        changed(
            candidate,
            citations=tuple(with_block(item) for item in candidate.citations),
            field_sources=tuple(
                changed(record, citations=tuple(with_block(item) for item in record.citations))
                for record in candidate.field_sources
            ),
        ),
        resolver,
    )
    assert converted.applicability.status == ApplicabilityStatus.APPLICABLE
    assert converted.request.procedure == "endovenous ablation"
    spans = [
        *converted.applicability.sources,
        *(source for record in converted.request.field_sources for source in record.sources),
    ]
    assert {span.block_id for span in spans} == {"p1"}


def test_an_unknown_scope_block_drops_a_missing_or_repeated_quote() -> None:
    resolver = blocks_resolver(
        policy_blocks=(("policy-b0", "Policy applies to endovenous ablation."),),
        chart_blocks=(
            ("b0", "Requested procedure: endovenous ablation."),
            ("b1", "Requested procedure: endovenous ablation."),
            ("payer", "Payer: Fixture Health."),
        ),
    )
    repeated = CandidateCitation(
        document_id="chart",
        page=1,
        quote="Requested procedure: endovenous ablation.",
        block_id="invented",
    )
    request = CandidateRequest(
        procedure="endovenous ablation",
        procedure_code=None,
        anatomical_target=None,
        laterality=None,
        payer="Fixture Health",
        plan=None,
        service_date=None,
        assessment_cutoff=None,
    )
    converted = convert_scope(
        ScopeCandidate(
            request=request,
            status="mismatch",
            rationale="The cited procedure is outside this policy.",
            citations=(
                CandidateCitation(
                    document_id="policy",
                    page=1,
                    quote="Policy applies to endovenous ablation.",
                    block_id="not-a-block",
                ),
                repeated,
                CandidateCitation(
                    document_id="chart",
                    page=1,
                    quote="this sentence is not on the page",
                    block_id="invented",
                ),
                CandidateCitation(
                    document_id="chart",
                    page=1,
                    quote="Requested procedure: endovenous ablation. Payer: Fixture Health.",
                    block_id="invented",
                ),
                CandidateCitation(
                    document_id="chart",
                    page=1,
                    quote="Payer: Fixture Health.",
                    block_id="invented",
                ),
            ),
            unresolved_fields=(),
            field_sources=(
                CandidateFieldSources(field="procedure", citations=(repeated,)),
                CandidateFieldSources(
                    field="payer",
                    citations=(
                        CandidateCitation(
                            document_id="chart",
                            page=1,
                            quote="Payer: Fixture Health.",
                            block_id="invented",
                        ),
                    ),
                ),
            ),
        ),
        resolver,
    )
    assert converted.applicability.status == ApplicabilityStatus.MISMATCH
    assert converted.request.procedure is None
    assert converted.request.payer == "Fixture Health"
    assert RequestField.PROCEDURE in converted.request.unresolved_fields
    assert converted.applicability.unresolved_fields == ()
    payer = next(
        item for item in converted.request.field_sources if item.field == RequestField.PAYER
    )
    assert [source.block_id for source in payer.sources] == ["payer"]
    assert {source.block_id for source in converted.applicability.sources} == {"policy-b0", "payer"}
    assert all(
        "not on the page" not in source.excerpt for source in converted.applicability.sources
    )


def test_a_real_scope_block_id_still_selects_that_copy() -> None:
    resolver = blocks_resolver(
        policy_blocks=(("policy-b0", "Policy applies to endovenous ablation."),),
        chart_blocks=(
            ("b0", "Requested procedure: endovenous ablation."),
            ("b1", "Requested procedure: endovenous ablation."),
        ),
    )
    selected = CandidateCitation(
        document_id="chart",
        page=1,
        quote="Requested procedure: endovenous ablation.",
        block_id="b1",
    )
    converted = convert_scope(
        ScopeCandidate(
            request=CandidateRequest(
                procedure="endovenous ablation",
                procedure_code=None,
                anatomical_target=None,
                laterality=None,
                payer=None,
                plan=None,
                service_date=None,
                assessment_cutoff=None,
            ),
            status="mismatch",
            rationale="The repeated passage is pinned to one block.",
            citations=(
                CandidateCitation(
                    document_id="policy",
                    page=1,
                    quote="Policy applies to endovenous ablation.",
                ),
                selected,
            ),
            unresolved_fields=(),
            field_sources=(CandidateFieldSources(field="procedure", citations=(selected,)),),
        ),
        resolver,
    )
    assert converted.request.field_sources[0].sources[0].block_id == "b1"
    with pytest.raises(CandidateConversionError) as error:
        convert_scope(
            ScopeCandidate(
                request=CandidateRequest(
                    procedure=None,
                    procedure_code=None,
                    anatomical_target=None,
                    laterality=None,
                    payer=None,
                    plan=None,
                    service_date=None,
                    assessment_cutoff=None,
                ),
                status="unresolved",
                rationale="The repeated passage has no block id.",
                citations=(changed(selected, block_id=None),),
                unresolved_fields=("policy_scope",),
                field_sources=(),
            ),
            resolver,
        )
    assert error.value.error.code == ErrorCode.CITATION_INVALID
    assert "ambiguous_quote" in error.value.error.message


def test_a_scope_quote_without_a_block_id_must_still_be_on_that_page(
    resolver: CitationResolver,
) -> None:
    candidate = scope_candidate()
    with pytest.raises(CandidateConversionError) as error:
        convert_scope(
            changed(
                candidate,
                citations=(
                    *candidate.citations,
                    CandidateCitation(
                        document_id="chart", page=1, quote="this sentence is not on the page"
                    ),
                ),
            ),
            resolver,
        )
    assert error.value.error.code == ErrorCode.CITATION_INVALID
    assert "quote_not_found" in error.value.error.message


def test_an_unknown_block_does_not_accept_another_document_or_page(
    resolver: CitationResolver,
) -> None:
    candidate = scope_candidate()
    policy_quote = changed(citation("Policy applies to endovenous ablation."), block_id="invented")
    with pytest.raises(CandidateConversionError) as wrong_document:
        convert_scope(
            changed(
                candidate,
                field_sources=(
                    changed(candidate.field_sources[0], citations=(policy_quote,)),
                    *candidate.field_sources[1:],
                ),
            ),
            resolver,
        )
    assert wrong_document.value.error.code == ErrorCode.CITATION_INVALID
    chart_only = CandidateCitation(
        document_id="chart",
        page=1,
        quote="Policy applies to endovenous ablation.",
        block_id="invented",
    )
    dropped = convert_scope(
        changed(
            candidate,
            field_sources=(
                changed(candidate.field_sources[0], citations=(chart_only,)),
                *candidate.field_sources[1:],
            ),
        ),
        resolver,
    )
    assert dropped.request.procedure is None
    assert dropped.applicability.status == ApplicabilityStatus.UNRESOLVED
    with pytest.raises(CandidateConversionError) as other_page:
        convert_scope(
            changed(
                candidate,
                citations=(
                    *candidate.citations,
                    CandidateCitation(
                        document_id="chart",
                        page=2,
                        quote="Requested procedure: endovenous ablation.",
                        block_id="invented",
                    ),
                ),
            ),
            resolver,
        )
    assert "invalid_page" in other_page.value.error.message


def test_dropped_scope_citations_still_reject_a_resolved_judgment() -> None:
    resolver = blocks_resolver(
        policy_blocks=(("policy-b0", "Policy applies to endovenous ablation."),),
        chart_blocks=(("chart-b0", "Requested procedure: endovenous ablation."),),
    )
    with pytest.raises(CandidateConversionError) as error:
        convert_scope(
            ScopeCandidate(
                request=CandidateRequest(
                    procedure="endovenous ablation",
                    procedure_code=None,
                    anatomical_target=None,
                    laterality=None,
                    payer=None,
                    plan=None,
                    service_date=None,
                    assessment_cutoff=None,
                ),
                status="applicable",
                rationale="The quotes were not on the cited pages.",
                citations=(
                    CandidateCitation(
                        document_id="policy",
                        page=1,
                        quote="not in the policy",
                        block_id="invented",
                    ),
                    CandidateCitation(
                        document_id="chart",
                        page=1,
                        quote="not in the chart",
                        block_id="invented",
                    ),
                ),
                unresolved_fields=(),
                field_sources=(
                    CandidateFieldSources(
                        field="procedure",
                        citations=(
                            CandidateCitation(
                                document_id="chart",
                                page=1,
                                quote="Requested procedure: endovenous ablation.",
                                block_id="invented",
                            ),
                        ),
                    ),
                ),
            ),
            resolver,
        )
    assert_invalid(error, RunPhase.CHECKING_APPLICABILITY)


def test_policy_conversion_still_rejects_an_unknown_block(resolver: CitationResolver) -> None:
    candidate = policy_candidate()
    criterion = changed(
        candidate.criteria[0],
        citations=(changed(candidate.criteria[0].citations[0], block_id="invented"),),
    )
    with pytest.raises(CandidateConversionError) as error:
        convert_policy(
            changed(candidate, criteria=(criterion,)),
            resolver,
            policy_id="policy-interpretation-1",
        )
    assert error.value.error.code == ErrorCode.CITATION_INVALID
    assert "unknown_block" in error.value.error.message


def test_mismatch_drops_an_unsourced_request_value(resolver: CitationResolver) -> None:
    candidate = scope_candidate()
    records = tuple(item for item in candidate.field_sources if item.field != "plan")
    converted = convert_scope(
        changed(candidate, status="mismatch", field_sources=records), resolver
    )
    assert converted.applicability.status == ApplicabilityStatus.MISMATCH
    assert converted.request.plan is None
    assert converted.request.procedure == "endovenous ablation"
    assert RequestField.PLAN in converted.request.unresolved_fields
    assert converted.applicability.unresolved_fields == ()


def test_scope_does_not_substitute_policy_text_for_chart_field_evidence(
    resolver: CitationResolver,
) -> None:
    candidate = scope_candidate()
    records = (
        changed(
            candidate.field_sources[0],
            citations=(citation("Policy applies to endovenous ablation."),),
        ),
        *candidate.field_sources[1:],
    )
    with pytest.raises(CandidateConversionError) as error:
        convert_scope(changed(candidate, field_sources=records), resolver)
    assert error.value.error.code == ErrorCode.CITATION_INVALID


@pytest.mark.parametrize(
    "invalid_date",
    ["20261028", "2026-W43-3", "2026-02-30", "today", "2026-10-28T00:00:00Z", " 2026-10-28 "],
)
def test_unreadable_request_dates_ask_staff_instead_of_failing(
    resolver: CitationResolver, invalid_date: str
) -> None:
    candidate = scope_candidate()
    converted = convert_scope(
        changed(candidate, request=changed(candidate.request, service_date=invalid_date)),
        resolver,
    )
    assert converted.request.service_date is None
    assert converted.applicability.status == ApplicabilityStatus.UNRESOLVED
    assert RequestField.SERVICE_DATE in converted.applicability.unresolved_fields
    assert "YYYY-MM-DD" in converted.applicability.rationale
    assert "service date" in converted.applicability.rationale
    assert invalid_date not in converted.applicability.rationale


def test_unreadable_dates_do_not_hide_a_cited_mismatch(resolver: CitationResolver) -> None:
    candidate = scope_candidate()
    converted = convert_scope(
        changed(
            candidate,
            status="mismatch",
            rationale="The chart procedure is outside the cited policy.",
            request=changed(candidate.request, service_date="October 28, 2026"),
        ),
        resolver,
    )
    assert converted.applicability.status == ApplicabilityStatus.MISMATCH
    assert converted.applicability.unresolved_fields == ()
    assert "outside the cited policy" in converted.applicability.rationale
    assert converted.request.service_date is None
    assert RequestField.SERVICE_DATE in converted.request.unresolved_fields
    assert "October 28, 2026" not in converted.applicability.rationale


def test_staff_date_replaces_an_unreadable_model_date(resolver: CitationResolver) -> None:
    candidate = scope_candidate()
    original = resolver.resolve(citation("Service date: 2026-10-28.", "chart"))
    annotation = DateAnnotation(
        annotation_id="service-date",
        field="service_date",
        value=date(2026, 10, 28),
        created_at=NOW,
        resolves_conflict=True,
        resolution_reason="The chart date was not returned as YYYY-MM-DD.",
        original_sources=(original,),
    )
    converted = convert_scope(
        changed(candidate, request=changed(candidate.request, service_date="October 28, 2026")),
        resolver,
        (annotation,),
    )
    assert converted.request.service_date == date(2026, 10, 28)
    assert converted.extracted_request.service_date is None
    assert converted.applicability.status == ApplicabilityStatus.APPLICABLE
    assert RequestField.SERVICE_DATE not in converted.applicability.unresolved_fields


def test_unresolved_and_mismatch_scope_are_distinct(resolver: CitationResolver) -> None:
    candidate = scope_candidate()
    unresolved = changed(candidate, status="unresolved", unresolved_fields=("plan",))
    converted = convert_scope(unresolved, resolver)
    assert converted.applicability.status == ApplicabilityStatus.UNRESOLVED
    assert converted.request.unresolved_fields == (RequestField.PLAN,)
    mismatch = convert_scope(changed(candidate, status="mismatch"), resolver)
    assert mismatch.applicability.status == ApplicabilityStatus.MISMATCH


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown_field",
        "duplicate_field",
        "empty_unresolved",
        "resolved_with_unknown",
        "missing_procedure",
        "missing_policy_citation",
    ],
)
def test_scope_inconsistencies_are_operational_failures(
    resolver: CitationResolver, mutation: str
) -> None:
    candidate = scope_candidate()
    if mutation == "unknown_field":
        candidate = changed(candidate, status="unresolved", unresolved_fields=("clinical_met",))
    elif mutation == "duplicate_field":
        candidate = changed(
            candidate, field_sources=(*candidate.field_sources, candidate.field_sources[0])
        )
    elif mutation == "empty_unresolved":
        candidate = changed(candidate, status="unresolved")
    elif mutation == "resolved_with_unknown":
        candidate = changed(candidate, unresolved_fields=("plan",))
    elif mutation == "missing_policy_citation":
        candidate = changed(candidate, citations=(candidate.citations[1],))
    else:
        candidate = changed(
            candidate,
            request=changed(candidate.request, procedure=None),
            field_sources=candidate.field_sources[1:],
        )
    with pytest.raises(CandidateConversionError) as error:
        convert_scope(candidate, resolver)
    assert_invalid(error, RunPhase.CHECKING_APPLICABILITY)


def test_staff_only_context_remains_annotation_not_extracted_fact(
    resolver: CitationResolver,
) -> None:
    candidate = scope_candidate()
    annotation = DateAnnotation(
        annotation_id="cutoff", field="assessment_cutoff", value=date(2026, 10, 18), created_at=NOW
    )
    candidate = changed(
        candidate, request=changed(candidate.request, assessment_cutoff="2026-10-18")
    )
    converted = convert_scope(candidate, resolver, (annotation,))
    assert converted.request.assessment_cutoff == annotation.value
    assert converted.extracted_request.assessment_cutoff is None
    assert converted.annotations == (annotation,)
    assert all(
        item.field != RequestField.ASSESSMENT_CUTOFF for item in converted.request.field_sources
    )
    assert converted.applicability.status == ApplicabilityStatus.APPLICABLE


def test_changed_conflicting_metadata_preserves_original_and_forces_reassessment(
    resolver: CitationResolver,
) -> None:
    candidate = scope_candidate()
    original = resolver.resolve(citation("Plan: Vascular.", "chart"))
    annotation = TextAnnotation(
        annotation_id="plan-selection",
        field="plan",
        value="Other plan",
        created_at=NOW,
        resolves_conflict=True,
        resolution_reason="Staff selected the plan for this request.",
        original_sources=(original,),
    )
    converted = convert_scope(candidate, resolver, (annotation,))
    assert converted.request.plan == "Other plan"
    assert converted.extracted_request.plan == "Vascular"
    assert converted.annotations[0].original_sources == (original,)
    assert converted.applicability.status == ApplicabilityStatus.UNRESOLVED
    assert RequestField.PLAN in converted.applicability.unresolved_fields
    assert candidate.request.plan == "Vascular"


@pytest.mark.parametrize("mutation", ["no_reason", "wrong_source", "duplicate_annotations"])
def test_conflicting_annotations_cannot_overwrite_source_metadata(
    resolver: CitationResolver, mutation: str
) -> None:
    original = resolver.resolve(citation("Plan: Vascular.", "chart"))
    annotation = TextAnnotation(
        annotation_id="plan-selection", field="plan", value="Other plan", created_at=NOW
    )
    if mutation != "no_reason":
        annotation = changed(
            annotation,
            resolves_conflict=True,
            resolution_reason="Select the request plan.",
            original_sources=(
                resolver.resolve(citation("Payer: Fixture Health.", "chart"))
                if mutation == "wrong_source"
                else original,
            ),
        )
    annotations = (annotation, annotation) if mutation == "duplicate_annotations" else (annotation,)
    with pytest.raises(CandidateConversionError) as error:
        convert_scope(scope_candidate(), resolver, annotations)
    assert_invalid(error, RunPhase.CHECKING_APPLICABILITY)


def test_reassessed_staff_selection_is_not_relabelled_as_chart_extraction(
    resolver: CitationResolver,
) -> None:
    candidate = scope_candidate()
    original = resolver.resolve(citation("Plan: Vascular.", "chart"))
    annotation = TextAnnotation(
        annotation_id="selection",
        field="plan",
        value="Other plan",
        created_at=NOW,
        original_sources=(original,),
        resolves_conflict=True,
        resolution_reason="Explicit request selection.",
    )
    candidate = changed(
        candidate,
        request=changed(candidate.request, plan="Other plan"),
        field_sources=tuple(item for item in candidate.field_sources if item.field != "plan"),
        status="mismatch",
    )
    converted = convert_scope(candidate, resolver, (annotation,))
    assert converted.request.plan == "Other plan"
    assert converted.extracted_request.plan is None
    assert converted.applicability.status == ApplicabilityStatus.MISMATCH
    assert converted.annotations[0].original_sources == (original,)


def test_policy_metadata_dates_and_supported_predicate_survive_conversion(
    resolver: CitationResolver,
) -> None:
    candidate = policy_candidate()
    converted = convert_policy(candidate, resolver, policy_id="policy-interpretation-1")
    assert converted.document_id == "policy"
    assert converted.document_sha256 == "a" * 64
    assert converted.revision_date == date(2026, 10, 1)
    assert converted.effective_from is None  # never borrow the revision date
    assert isinstance(converted.criteria[0].predicate, NumericPredicate)
    assert converted.issues == ()
    assert converted.criteria[0].sources[0].excerpt == candidate.criteria[0].wording


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_policy_title_keeps_the_section_and_blocks_a_favorable_result(
    resolver: CitationResolver, blank: str
) -> None:
    converted = convert_policy(
        changed(policy_candidate(), title=blank, scope_summary=blank),
        resolver,
        policy_id="policy-interpretation-1",
    )
    assert converted.title == "Diameter"
    assert converted.scope_summary == "The section scope was not extracted."
    label = next(issue for issue in converted.issues if issue.issue_id == "conversion-policy-label")
    assert label.blocks_readiness is True
    assert converted.criteria[0].wording == "Right vein diameter must be at least 3.0 mm."


def test_blank_path_label_keeps_the_cited_path(resolver: CitationResolver) -> None:
    converted = convert_policy(
        policy_candidate().model_copy(
            update={
                "paths": (
                    CandidatePolicyPath(
                        path_id="vein",
                        title="",
                        scope="   ",
                        root_id="root",
                        citations=(citation("Right vein diameter must be at least 3.0 mm."),),
                    ),
                )
            }
        ),
        resolver,
        policy_id="policy-interpretation-1",
    )
    assert converted.title == "Fixture policy"
    assert converted.paths[0].title == "vein"
    assert converted.paths[0].scope == "The path scope was not extracted."
    label = next(
        issue for issue in converted.issues if issue.issue_id == "conversion-path-label-0000"
    )
    assert label.blocks_readiness is True


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_policy_identifier_is_unset_not_a_contract_failure(
    resolver: CitationResolver, blank: str
) -> None:
    converted = convert_policy(
        changed(policy_candidate(), identifier=blank),
        resolver,
        policy_id="policy-interpretation-1",
    )
    assert converted.identifier is None


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown_operator",
        "unknown_unit",
        "unknown_predicate",
        "missing_context",
        "missing_threshold",
        "fabricated_threshold",
    ],
)
def test_unsupported_policy_semantics_are_preserved_as_blocking_review(
    resolver: CitationResolver, mutation: str
) -> None:
    candidate = policy_candidate()
    changes: dict[str, dict[str, object]] = {
        "unknown_operator": {"operator": "between"},
        "unknown_unit": {"unit": "months"},
        "unknown_predicate": {"predicate_kind": "unsupported"},
        "missing_context": {"context": ()},
        "missing_threshold": {"threshold": None},
        "fabricated_threshold": {"threshold": 4.0},
    }
    updates = changes[mutation]
    candidate = changed(candidate, criteria=(changed(candidate.criteria[0], **updates),))
    converted = convert_policy(candidate, resolver, policy_id="converted")
    assert converted.issues and converted.issues[0].blocks_readiness
    assert converted.issues[0].sources == converted.criteria[0].sources
    assert converted.issues[0].criterion_ids == ("diameter",)


def test_a_group_with_a_stray_criterion_id_keeps_its_children(
    resolver: CitationResolver,
) -> None:
    candidate = policy_candidate()
    leaf = candidate.nodes[0]
    group = changed(leaf, node_id="group", kind="all", children=("root",), criterion_id="diameter")
    converted = convert_policy(
        changed(candidate, nodes=(group, leaf), root_id="group"),
        resolver,
        policy_id="converted",
    )
    assert converted.root_id == "group"
    assert converted.nodes[0].kind == "all"
    assert converted.nodes[0].children == ("root",)
    assert converted.nodes[1].criterion_id == "diameter"


def test_unreadable_policy_dates_ask_staff_and_keep_the_guideline(
    resolver: CitationResolver,
) -> None:
    candidate = policy_candidate()
    dated = changed(
        candidate.criteria[0],
        predicate_kind="date",
        operator="on_or_before",
        threshold=None,
        unit=None,
        date_boundary="08/15/25",
        date_role="event_date",
        wording="Observation must be on or before 2026-10-18.",
        interpretation="The observation date is on or before the cited policy date.",
        citations=(citation("Observation must be on or before 2026-10-18."),),
    )
    candidate = changed(
        candidate,
        revision_date="08/15/25",
        criteria=(dated,),
        sections=(
            changed(
                candidate.sections[0],
                citations=dated.citations,
                explanation="The stated date condition.",
            ),
        ),
        nodes=(changed(candidate.nodes[0], citations=dated.citations),),
    )
    converted = convert_policy(candidate, resolver, policy_id="converted")
    assert converted.criteria[0].predicate is None
    assert converted.criteria[0].wording == dated.wording
    assert converted.revision_date is None
    assert "08/15/25" not in converted.model_dump_json()
    messages = {issue.message: issue.action for issue in converted.issues}
    assert any(
        "YYYY-MM-DD" in message and "Confirm" in action for message, action in messages.items()
    )
    assert all(issue.blocks_readiness for issue in converted.issues)
    date_issue = next(
        issue for issue in converted.issues if issue.issue_id == "conversion-policy-date"
    )
    # The candidate has no citation for its metadata fields, so the issue must
    # not borrow the first criterion's passage as if it supported the date.
    assert date_issue.sources == ()
    assert date_issue.criterion_ids == ()


def test_chart_unknown_block_keeps_the_unique_quote(resolver: CitationResolver) -> None:
    fact = evidence_candidate().facts[0]
    converted = convert_chart(
        ChartCandidate(
            facts=(
                changed(
                    fact,
                    citations=(changed(fact.citations[0], block_id="p0007.b0099"),),
                ),
            )
        ),
        resolver,
        document_sha256="b" * 64,
    )
    assert converted.facts[0].sources[0].block_id == "p1"
    assert converted.interpretation_issues == ()


def test_chart_unknown_block_drops_a_quote_that_is_not_on_the_page(
    resolver: CitationResolver,
) -> None:
    fact = evidence_candidate().facts[0]
    missing = changed(
        fact,
        fact_id="missing",
        citations=(changed(fact.citations[0], quote="not on the page", block_id="invented"),),
    )
    kept = changed(fact, fact_id="kept", conflicting_fact_ids=("missing",))
    converted = convert_chart(
        ChartCandidate(facts=(missing, kept)),
        resolver,
        document_sha256="b" * 64,
    )
    assert [item.fact_id for item in converted.facts] == ["kept"]
    assert converted.facts[0].conflicting_fact_ids == ()
    assert any("was not kept" in note for note in converted.facts[0].uncertainty)
    assert any(
        "missing" in note and "cited page" in note for note in converted.interpretation_issues
    )
    assert chart_omission_issue(converted.interpretation_issues) is not None


def test_blank_chart_anatomy_is_absent_not_a_contract_failure(
    resolver: CitationResolver,
) -> None:
    fact = evidence_candidate().facts[0]
    converted = convert_chart(
        ChartCandidate(
            facts=(
                changed(
                    fact,
                    anatomical_target="",
                    laterality="   ",
                    unit="",
                    context=("", "right vein"),
                    uncertainty=(" ",),
                ),
            )
        ),
        resolver,
        document_sha256="b" * 64,
    )
    saved = converted.facts[0]
    assert saved.proposition == fact.proposition
    assert saved.anatomical_target is None
    assert saved.laterality is None
    assert saved.unit is None
    assert saved.value == fact.value
    assert saved.context == ("right vein",)
    assert saved.uncertainty == ()


def test_chart_quote_without_a_block_id_must_still_match(resolver: CitationResolver) -> None:
    fact = evidence_candidate().facts[0]
    with pytest.raises(CandidateConversionError) as error:
        convert_chart(
            ChartCandidate(
                facts=(
                    changed(
                        fact,
                        citations=(changed(fact.citations[0], quote="not on the page"),),
                    ),
                )
            ),
            resolver,
            document_sha256="b" * 64,
        )
    assert error.value.error.code == ErrorCode.CITATION_INVALID
    assert "quote_not_found" in error.value.error.message


def test_unreadable_chart_date_asks_staff_and_keeps_the_fact(resolver: CitationResolver) -> None:
    fact = evidence_candidate().facts[0]
    converted = convert_chart(
        ChartCandidate(facts=(changed(fact, event_date="October 28, 2026"),)),
        resolver,
        document_sha256="b" * 64,
    )
    assert converted.facts[0].event_date is None
    assert converted.facts[0].proposition == fact.proposition
    assert converted.interpretation_issues
    assert fact.fact_id in converted.interpretation_issues[0]
    assert "YYYY-MM-DD" in converted.interpretation_issues[0]
    assert "October 28, 2026" not in converted.model_dump_json()


@pytest.mark.parametrize(
    "mutation",
    [
        "cycle",
        "unknown_criterion",
        "leaf_with_children",
        "group_with_criterion",
        "missing_sections",
        "unmapped_requirement",
    ],
)
def test_policy_domain_contradictions_fail_conversion(
    resolver: CitationResolver, mutation: str
) -> None:
    candidate = policy_candidate()
    node = candidate.nodes[0]
    if mutation == "cycle":
        candidate = changed(
            candidate,
            nodes=(
                changed(node, kind="all", children=("root", "leaf"), criterion_id=None),
                changed(node, node_id="leaf"),
            ),
        )
    elif mutation == "unknown_criterion":
        candidate = changed(candidate, nodes=(changed(node, criterion_id="unknown"),))
    elif mutation == "leaf_with_children":
        candidate = changed(candidate, nodes=(changed(node, children=("root",)),))
    elif mutation == "group_with_criterion":
        candidate = changed(candidate, nodes=(changed(node, kind="all", children=("root",)),))
    elif mutation == "missing_sections":
        candidate = changed(candidate, sections=())
    elif mutation == "unmapped_requirement":
        candidate = changed(
            candidate,
            sections=(changed(candidate.sections[0], disposition="context", criterion_ids=()),),
        )
    with pytest.raises(CandidateConversionError) as error:
        convert_policy(candidate, resolver, policy_id="converted")
    assert_invalid(error, RunPhase.INTERPRETING_POLICY)


def test_narrative_criterion_keeps_wording_and_drops_hidden_operators(
    resolver: CitationResolver,
) -> None:
    candidate = policy_candidate()
    hidden = changed(
        candidate.criteria[0],
        predicate_kind="narrative",
        date_boundary="2026-10-01",
        date_role="service",
    )
    converted = convert_policy(
        changed(candidate, criteria=(hidden,)), resolver, policy_id="converted"
    )
    assert isinstance(converted.criteria[0].predicate, NarrativePredicate)
    assert converted.criteria[0].wording == hidden.wording
    assert converted.issues and converted.issues[0].blocks_readiness
    assert "not applied" in converted.issues[0].message
    assert "operator" in converted.issues[0].message


def test_every_policy_record_rejects_chart_citations(resolver: CitationResolver) -> None:
    candidate = policy_candidate()
    wrong = (citation("Right vein diameter is 2.7 mm.", "chart"),)
    for altered in (
        changed(candidate, criteria=(changed(candidate.criteria[0], citations=wrong),)),
        changed(candidate, nodes=(changed(candidate.nodes[0], citations=wrong),)),
        changed(candidate, sections=(changed(candidate.sections[0], citations=wrong),)),
    ):
        with pytest.raises(CandidateConversionError) as error:
            convert_policy(altered, resolver, policy_id="converted")
        assert error.value.error.code == ErrorCode.CITATION_INVALID


def test_interpretation_issues_and_unresolved_sections_still_block_true_tree(
    resolver: CitationResolver,
) -> None:
    candidate = policy_candidate()
    narrative = changed(
        candidate.criteria[0],
        predicate_kind="narrative",
        operator=None,
        threshold=None,
        unit=None,
        context=(),
    )
    unresolved = changed(
        candidate.sections[0],
        section_id="exception",
        disposition="unresolved",
        criterion_ids=(),
        explanation="Uninterpreted governing exception.",
    )
    candidate = changed(
        candidate,
        criteria=(narrative,),
        sections=(*candidate.sections, unresolved),
        interpretation_issues=("An exception needs review.",),
    )
    policy = convert_policy(candidate, resolver, policy_id="converted")
    evidence = convert_chart_and_findings(evidence_candidate(), policy, resolver)
    result = evaluate_policy(
        policy, evidence.findings, convert_scope(scope_candidate(), resolver).applicability
    )
    assert result.outcome == AssessmentOutcome.REVIEW_REQUIRED
    assert len(result.blockers) == 2


def test_evidence_conversion_preserves_fact_provenance_and_recomputes_numeric_findings(
    resolver: CitationResolver,
) -> None:
    policy = convert_policy(policy_candidate(), resolver, policy_id="converted")
    candidate = evidence_candidate()
    converted = convert_chart_and_findings(candidate, policy, resolver)
    assert converted.facts[0].provenance == FactProvenance.DIRECT
    assert converted.facts[0].value == 2.7
    assert converted.facts[0].sources[0].document_id == "chart"
    assert converted.candidate_findings[0].status == EvidenceStatus.MET
    assert converted.findings[0].status == EvidenceStatus.NOT_MET
    assert converted.findings[0].evidence[0].relation == EvidenceRelation.CONTRADICTING
    assert candidate.findings[0].status == "met"


def test_clinician_summary_does_not_generate_underlying_measurements(
    resolver: CitationResolver,
) -> None:
    candidate = evidence_candidate()
    fact = changed(candidate.facts[0], provenance="clinician_summary", value=None, unit=None)
    policy = convert_policy(policy_candidate(), resolver, policy_id="converted")
    result = convert_chart_and_findings(changed(candidate, facts=(fact,)), policy, resolver)
    assert result.facts[0].provenance == FactProvenance.CLINICIAN_SUMMARY
    assert result.facts[0].value is None
    assert result.findings[0].status == EvidenceStatus.NEEDS_REVIEW


@pytest.mark.parametrize(
    ("mutation", "phase"),
    [
        ("no_facts", RunPhase.MAPPING_EVIDENCE),
        ("unknown_reference", RunPhase.MAPPING_EVIDENCE),
        ("duplicate_fact", RunPhase.EXTRACTING_CHART),
        ("missing_finding", RunPhase.MAPPING_EVIDENCE),
        ("missing_fact_citation", RunPhase.EXTRACTING_CHART),
        ("unknown_conflict", RunPhase.EXTRACTING_CHART),
        ("positive_without_support", RunPhase.MAPPING_EVIDENCE),
    ],
)
def test_invalid_evidence_never_silently_becomes_a_missing_finding(
    resolver: CitationResolver, mutation: str, phase: RunPhase
) -> None:
    candidate = evidence_candidate()
    if mutation == "no_facts":
        candidate = changed(candidate, facts=())
    elif mutation == "unknown_reference":
        candidate = changed(
            candidate,
            findings=(
                changed(
                    candidate.findings[0],
                    evidence=(
                        CandidateEvidenceReference(fact_id="unknown", relation="supporting"),
                    ),
                ),
            ),
        )
    elif mutation == "duplicate_fact":
        candidate = changed(candidate, facts=(candidate.facts[0], candidate.facts[0]))
    elif mutation == "missing_finding":
        candidate = changed(candidate, findings=())
    elif mutation == "missing_fact_citation":
        candidate = changed(candidate, facts=(changed(candidate.facts[0], citations=()),))
    elif mutation == "unknown_conflict":
        candidate = changed(
            candidate, facts=(changed(candidate.facts[0], conflicting_fact_ids=("absent",)),)
        )
    else:
        candidate = changed(candidate, findings=(changed(candidate.findings[0], evidence=()),))
    policy = convert_policy(policy_candidate(), resolver, policy_id="converted")
    with pytest.raises(CandidateConversionError) as error:
        convert_chart_and_findings(candidate, policy, resolver)
    assert_invalid(error, phase)


def test_explicit_missing_evidence_remains_missing_without_an_invented_span(
    resolver: CitationResolver,
) -> None:
    policy = convert_policy(policy_candidate(), resolver, policy_id="converted")
    candidate = EvidenceCandidate(
        facts=(),
        findings=(
            CandidateFinding(
                criterion_id="diameter",
                status="missing",
                rationale="The available chart has no relevant measurement.",
                evidence=(),
                unresolved_reasons=("not_documented",),
            ),
        ),
    )
    converted = convert_chart_and_findings(candidate, policy, resolver)
    assert converted.findings[0].status == EvidenceStatus.MISSING
    assert converted.findings[0].evidence == ()
    assert converted.facts == ()


def test_chart_fact_cannot_cite_the_policy_even_when_the_quote_exists(
    resolver: CitationResolver,
) -> None:
    candidate = evidence_candidate()
    candidate = changed(
        candidate,
        facts=(
            changed(
                candidate.facts[0],
                citations=(citation("Right vein diameter must be at least 3.0 mm."),),
            ),
        ),
    )
    policy = convert_policy(policy_candidate(), resolver, policy_id="converted")
    with pytest.raises(CandidateConversionError) as error:
        convert_chart_and_findings(candidate, policy, resolver)
    assert error.value.error.code == ErrorCode.CITATION_INVALID


def test_evidence_date_and_cutoff_conflicts_remain_review_states(
    resolver: CitationResolver,
) -> None:
    policy = convert_policy(policy_candidate(), resolver, policy_id="converted")
    candidate = evidence_candidate()
    fact = changed(
        candidate.facts[0],
        event_date="2026-10-12",
        documentation_date="2026-10-13",
        citations=(
            *candidate.facts[0].citations,
            citation("Observation date: 2026-10-12. Report signed: 2026-10-13.", "chart"),
        ),
    )
    request = convert_scope(scope_candidate(), resolver).request
    request = changed(request, assessment_cutoff=date(2026, 10, 12))
    converted = convert_chart_and_findings(
        changed(candidate, facts=(fact,)), policy, resolver, request
    )
    assert converted.findings[0].status == EvidenceStatus.NEEDS_REVIEW
    assert "documentation_date_after_cutoff" in converted.findings[0].unresolved_reasons


def make_multi_procedure_resolver() -> CitationResolver:
    chart_text = (
        "Payer: Fixture Health. Plan: Vascular. "
        "Primary candidate: endovenous ablation. "
        "Alternative candidate: ambulatory phlebectomy. "
        "Right vein diameter is 2.7 mm. Service date: 2026-10-28."
    )
    documents = [
        DocumentRecord(
            document_id="policy",
            role=DocumentRole.POLICY,
            filename="policy.pdf",
            sha256="a" * 64,
            byte_count=100,
            page_count=1,
            pages=(PageInventory(page=1),),
            created_at=NOW,
        ),
        DocumentRecord(
            document_id="chart",
            role=DocumentRole.CHART,
            filename="chart.pdf",
            sha256="b" * 64,
            byte_count=100,
            page_count=1,
            pages=(PageInventory(page=1),),
            created_at=NOW,
        ),
    ]
    extractions = [
        ExtractionRecord(
            extraction_id="policy-v1",
            document_id="policy",
            document_sha256="a" * 64,
            parser_name="artificial-contract-blocks",
            parser_version="1",
            configuration_sha256="c" * 64,
            created_at=NOW,
            pages=(
                ExtractedPage(
                    page=1,
                    quality=PageQuality.USABLE,
                    method=ExtractionMethod.NATIVE_TEXT,
                    blocks=(TextBlock(block_id="p1", text=POLICY, reading_order=0),),
                ),
            ),
        ),
        ExtractionRecord(
            extraction_id="chart-v1",
            document_id="chart",
            document_sha256="b" * 64,
            parser_name="artificial-contract-blocks",
            parser_version="1",
            configuration_sha256="c" * 64,
            created_at=NOW,
            pages=(
                ExtractedPage(
                    page=1,
                    quality=PageQuality.USABLE,
                    method=ExtractionMethod.NATIVE_TEXT,
                    blocks=(TextBlock(block_id="p1", text=chart_text, reading_order=0),),
                ),
            ),
        ),
    ]
    return CitationResolver(documents, extractions)


def test_multiple_procedure_candidate_without_selection_remains_unresolved() -> None:
    res = make_multi_procedure_resolver()
    payer_cite = CandidateCitation(document_id="chart", page=1, quote="Payer: Fixture Health.")
    plan_cite = CandidateCitation(document_id="chart", page=1, quote="Plan: Vascular.")
    service_cite = CandidateCitation(document_id="chart", page=1, quote="Service date: 2026-10-28.")
    policy_scope_cite = CandidateCitation(
        document_id="policy", page=1, quote="Policy applies to endovenous ablation."
    )

    candidate = ScopeCandidate(
        request=CandidateRequest(
            procedure=None,
            procedure_code=None,
            anatomical_target=None,
            laterality=None,
            payer="Fixture Health",
            plan="Vascular",
            service_date="2026-10-28",
            assessment_cutoff=None,
        ),
        status="unresolved",
        rationale="Multiple procedures are documented in the medical chart.",
        citations=(
            policy_scope_cite,
            CandidateCitation(
                document_id="chart", page=1, quote="Primary candidate: endovenous ablation."
            ),
        ),
        unresolved_fields=("procedure",),
        field_sources=(
            CandidateFieldSources(
                field="procedure",
                citations=(
                    CandidateCitation(
                        document_id="chart", page=1, quote="Primary candidate: endovenous ablation."
                    ),
                    CandidateCitation(
                        document_id="chart",
                        page=1,
                        quote="Alternative candidate: ambulatory phlebectomy.",
                    ),
                ),
            ),
            CandidateFieldSources(field="payer", citations=(payer_cite,)),
            CandidateFieldSources(field="plan", citations=(plan_cite,)),
            CandidateFieldSources(field="service_date", citations=(service_cite,)),
        ),
    )

    converted = convert_scope(candidate, res)
    assert converted.applicability.status == ApplicabilityStatus.UNRESOLVED
    assert RequestField.PROCEDURE in converted.applicability.unresolved_fields
    assert converted.request.procedure is None
    assert converted.extracted_request.procedure is None
    assert len(converted.extracted_request.field_sources[0].sources) == 2

    # Attempting to declare applicable without staff resolution fails closed
    # (no automatic top-one choice or policy substitution)
    with pytest.raises(CandidateConversionError) as error:
        convert_scope(changed(candidate, status="applicable", unresolved_fields=()), res)
    assert_invalid(error, RunPhase.CHECKING_APPLICABILITY)


@pytest.mark.parametrize(
    "defect", ["unmarked_conflict", "omits_competing_source", "unrelated_source"]
)
def test_multiple_procedure_annotation_requires_resolution_reason_and_all_sources(
    defect: str,
) -> None:
    res = make_multi_procedure_resolver()
    proc1 = res.resolve(
        CandidateCitation(
            document_id="chart", page=1, quote="Primary candidate: endovenous ablation."
        )
    )
    proc2 = res.resolve(
        CandidateCitation(
            document_id="chart", page=1, quote="Alternative candidate: ambulatory phlebectomy."
        )
    )
    payer_cite = CandidateCitation(document_id="chart", page=1, quote="Payer: Fixture Health.")
    payer_span = res.resolve(payer_cite)
    plan_cite = CandidateCitation(document_id="chart", page=1, quote="Plan: Vascular.")
    service_cite = CandidateCitation(document_id="chart", page=1, quote="Service date: 2026-10-28.")
    policy_scope_cite = CandidateCitation(
        document_id="policy", page=1, quote="Policy applies to endovenous ablation."
    )

    candidate = ScopeCandidate(
        request=CandidateRequest(
            procedure=None,
            procedure_code=None,
            anatomical_target=None,
            laterality=None,
            payer="Fixture Health",
            plan="Vascular",
            service_date="2026-10-28",
            assessment_cutoff=None,
        ),
        status="unresolved",
        rationale="Multiple procedures are documented.",
        citations=(
            policy_scope_cite,
            CandidateCitation(
                document_id="chart", page=1, quote="Primary candidate: endovenous ablation."
            ),
        ),
        unresolved_fields=("procedure",),
        field_sources=(
            CandidateFieldSources(
                field="procedure",
                citations=(
                    CandidateCitation(
                        document_id="chart", page=1, quote="Primary candidate: endovenous ablation."
                    ),
                    CandidateCitation(
                        document_id="chart",
                        page=1,
                        quote="Alternative candidate: ambulatory phlebectomy.",
                    ),
                ),
            ),
            CandidateFieldSources(field="payer", citations=(payer_cite,)),
            CandidateFieldSources(field="plan", citations=(plan_cite,)),
            CandidateFieldSources(field="service_date", citations=(service_cite,)),
        ),
    )

    if defect == "unmarked_conflict":
        annotation = TextAnnotation(
            annotation_id="select-procedure",
            field="procedure",
            value="endovenous ablation",
            created_at=NOW,
            resolves_conflict=False,
            original_sources=(proc1, proc2),
        )
    elif defect == "omits_competing_source":
        annotation = TextAnnotation(
            annotation_id="select-procedure",
            field="procedure",
            value="endovenous ablation",
            created_at=NOW,
            resolves_conflict=True,
            resolution_reason="Staff selected primary indicated procedure.",
            original_sources=(proc1,),
        )
    else:
        annotation = TextAnnotation(
            annotation_id="select-procedure",
            field="procedure",
            value="endovenous ablation",
            created_at=NOW,
            resolves_conflict=True,
            resolution_reason="Staff selected primary indicated procedure.",
            original_sources=(proc1, payer_span),
        )

    with pytest.raises(CandidateConversionError) as error:
        convert_scope(candidate, res, (annotation,))
    assert_invalid(error, RunPhase.CHECKING_APPLICABILITY)


def test_conflict_annotation_schema_rejects_missing_reason_or_empty_sources() -> None:
    res = make_multi_procedure_resolver()
    proc1 = res.resolve(
        CandidateCitation(
            document_id="chart", page=1, quote="Primary candidate: endovenous ablation."
        )
    )
    with pytest.raises(ValidationError):
        TextAnnotation(
            annotation_id="select-procedure",
            field="procedure",
            value="endovenous ablation",
            created_at=NOW,
            resolves_conflict=True,
            resolution_reason=None,
            original_sources=(proc1,),
        )
    with pytest.raises(ValidationError):
        TextAnnotation(
            annotation_id="select-procedure",
            field="procedure",
            value="endovenous ablation",
            created_at=NOW,
            resolves_conflict=True,
            resolution_reason="Reason given.",
            original_sources=(),
        )


def test_multiple_procedure_selection_resolves_conflict_and_preserves_extraction_provenance() -> (
    None
):
    res = make_multi_procedure_resolver()
    proc1 = res.resolve(
        CandidateCitation(
            document_id="chart", page=1, quote="Primary candidate: endovenous ablation."
        )
    )
    proc2 = res.resolve(
        CandidateCitation(
            document_id="chart", page=1, quote="Alternative candidate: ambulatory phlebectomy."
        )
    )
    payer_cite = CandidateCitation(document_id="chart", page=1, quote="Payer: Fixture Health.")
    plan_cite = CandidateCitation(document_id="chart", page=1, quote="Plan: Vascular.")
    service_cite = CandidateCitation(document_id="chart", page=1, quote="Service date: 2026-10-28.")
    policy_scope_cite = CandidateCitation(
        document_id="policy", page=1, quote="Policy applies to endovenous ablation."
    )

    annotation = TextAnnotation(
        annotation_id="select-procedure",
        field="procedure",
        value="endovenous ablation",
        created_at=NOW,
        resolves_conflict=True,
        resolution_reason="Staff selected primary indicated procedure from clinical notes.",
        original_sources=(proc1, proc2),
    )

    # In reassessment, candidate provides the staff-selected procedure
    # without fake extraction citations:
    candidate = ScopeCandidate(
        request=CandidateRequest(
            procedure="endovenous ablation",
            procedure_code=None,
            anatomical_target=None,
            laterality=None,
            payer="Fixture Health",
            plan="Vascular",
            service_date="2026-10-28",
            assessment_cutoff=None,
        ),
        status="applicable",
        rationale="Payer, plan, and selected procedure match guideline.",
        citations=(
            policy_scope_cite,
            CandidateCitation(
                document_id="chart", page=1, quote="Primary candidate: endovenous ablation."
            ),
        ),
        unresolved_fields=(),
        field_sources=(
            CandidateFieldSources(field="payer", citations=(payer_cite,)),
            CandidateFieldSources(field="plan", citations=(plan_cite,)),
            CandidateFieldSources(field="service_date", citations=(service_cite,)),
        ),
    )

    converted = convert_scope(candidate, res, (annotation,))
    assert converted.applicability.status == ApplicabilityStatus.APPLICABLE
    assert converted.request.procedure == "endovenous ablation"
    assert converted.extracted_request.procedure is None
    assert converted.annotations[0].resolves_conflict is True
    assert converted.annotations[0].original_sources == (proc1, proc2)
