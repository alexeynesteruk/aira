"""Provider-shaped candidates exercise domain conversion without provider calls."""

from datetime import UTC, date, datetime

import pytest
from pydantic import BaseModel

from app.assessment import evaluate_policy
from app.evidence import CitationResolver
from app.policies import (
    CandidateConversionError,
    convert_evidence,
    convert_policy,
    convert_scope,
)
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
    NumericPredicate,
    PageInventory,
    PageQuality,
    PolicyCandidate,
    RequestField,
    RunPhase,
    ScopeCandidate,
    TextAnnotation,
    TextBlock,
)

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
    with pytest.raises(CandidateConversionError) as error:
        convert_scope(changed(candidate, field_sources=()), resolver)
    assert_invalid(error, RunPhase.CHECKING_APPLICABILITY)


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
def test_scope_dates_require_exact_valid_iso_calendar_dates(
    resolver: CitationResolver, invalid_date: str
) -> None:
    candidate = scope_candidate()
    with pytest.raises(CandidateConversionError) as error:
        convert_scope(
            changed(candidate, request=changed(candidate.request, service_date=invalid_date)),
            resolver,
        )
    assert_invalid(error, RunPhase.CHECKING_APPLICABILITY)
    assert invalid_date not in error.value.error.message


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


@pytest.mark.parametrize(
    "mutation",
    [
        "cycle",
        "unknown_criterion",
        "leaf_with_children",
        "group_with_criterion",
        "missing_sections",
        "unmapped_requirement",
        "bad_date",
        "hidden_parameters",
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
    elif mutation == "hidden_parameters":
        candidate = changed(
            candidate, criteria=(changed(candidate.criteria[0], predicate_kind="narrative"),)
        )
    else:
        candidate = changed(candidate, effective_from="20260230")
    with pytest.raises(CandidateConversionError) as error:
        convert_policy(candidate, resolver, policy_id="converted")
    assert_invalid(error, RunPhase.INTERPRETING_POLICY)


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
    evidence = convert_evidence(evidence_candidate(), policy, resolver)
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
    converted = convert_evidence(candidate, policy, resolver)
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
    result = convert_evidence(changed(candidate, facts=(fact,)), policy, resolver)
    assert result.facts[0].provenance == FactProvenance.CLINICIAN_SUMMARY
    assert result.facts[0].value is None
    assert result.findings[0].status == EvidenceStatus.NEEDS_REVIEW


@pytest.mark.parametrize(
    "mutation",
    [
        "no_facts",
        "unknown_reference",
        "duplicate_fact",
        "missing_finding",
        "missing_fact_citation",
        "malformed_date",
        "unknown_conflict",
        "positive_without_support",
    ],
)
def test_invalid_evidence_never_silently_becomes_a_missing_finding(
    resolver: CitationResolver, mutation: str
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
    elif mutation == "malformed_date":
        candidate = changed(candidate, facts=(changed(candidate.facts[0], event_date="20261012"),))
    elif mutation == "unknown_conflict":
        candidate = changed(
            candidate, facts=(changed(candidate.facts[0], conflicting_fact_ids=("absent",)),)
        )
    else:
        candidate = changed(candidate, findings=(changed(candidate.findings[0], evidence=()),))
    policy = convert_policy(policy_candidate(), resolver, policy_id="converted")
    with pytest.raises(CandidateConversionError) as error:
        convert_evidence(candidate, policy, resolver)
    assert_invalid(error, RunPhase.MAPPING_EVIDENCE)


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
    converted = convert_evidence(candidate, policy, resolver)
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
        convert_evidence(candidate, policy, resolver)
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
    converted = convert_evidence(changed(candidate, facts=(fact,)), policy, resolver, request)
    assert converted.findings[0].status == EvidenceStatus.NEEDS_REVIEW
    assert "documentation_date_after_cutoff" in converted.findings[0].unresolved_reasons
