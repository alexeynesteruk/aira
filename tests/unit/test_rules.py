"""Truth-table, independent annotated-graph, and mechanical evidence checks."""

import json
import re
from datetime import UTC, datetime
from itertools import product
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from app.assessment import evaluate_policy
from app.evidence import CitationResolver, EvidenceValidationError, validate_findings
from app.schemas import (
    AllNode,
    AnyNode,
    ApplicabilityResult,
    ApplicabilityStatus,
    AssessmentOutcome,
    CandidateCitation,
    ChartFact,
    Criterion,
    CriterionNode,
    DocumentRecord,
    DocumentRole,
    EvidenceReference,
    EvidenceRelation,
    EvidenceStatus,
    ExtractedPage,
    ExtractionMethod,
    ExtractionRecord,
    FactPolarity,
    Finding,
    IssueCategory,
    LogicalValue,
    NarrativePredicate,
    NumericPredicate,
    PageInventory,
    PageQuality,
    Policy,
    PolicySection,
    ReviewIssue,
    SourceSpan,
    TextBlock,
)

ROOT = Path(__file__).resolve().parents[2]


def changed[T: BaseModel](model: T, **updates: object) -> T:
    return type(model).model_validate({**model.model_dump(), **updates})


def span() -> SourceSpan:
    return SourceSpan(
        document_id="policy",
        document_sha256="a" * 64,
        extraction_id="policy-v1",
        page=1,
        block_id="p1",
        start=0,
        end=6,
        excerpt="policy",
    )


def policy(kind: str = "all") -> Policy:
    criteria = tuple(
        Criterion(
            criterion_id=name,
            wording=f"Requirement {name}",
            interpretation=f"Question {name}",
            sources=(span(),),
            predicate=NarrativePredicate(question=f"Is {name} documented?"),
        )
        for name in ("a", "b")
    )
    root = (AllNode if kind == "all" else AnyNode)(
        node_id="root", children=("a_node", "b_node"), sources=(span(),)
    )
    return Policy(
        policy_id="test-policy",
        document_id="policy",
        document_sha256="a" * 64,
        title="Truth table",
        scope_summary="Artificial domain test",
        criteria=criteria,
        nodes=(
            root,
            *(
                CriterionNode(node_id=name + "_node", criterion_id=name, sources=(span(),))
                for name in ("a", "b")
            ),
        ),
        root_id="root",
        sections=(
            PolicySection(
                section_id="requirements",
                heading="Requirements",
                sources=(span(),),
                disposition="requirements",
                criterion_ids=("a", "b"),
                explanation="Both leaves retained.",
            ),
        ),
    )


def finding(criterion_id: str, status: EvidenceStatus) -> Finding:
    evidence = {
        EvidenceStatus.MET: (
            EvidenceReference(fact_id=criterion_id + "_yes", relation=EvidenceRelation.SUPPORTING),
        ),
        EvidenceStatus.NOT_MET: (
            EvidenceReference(
                fact_id=criterion_id + "_no", relation=EvidenceRelation.CONTRADICTING
            ),
        ),
        EvidenceStatus.CONFLICTING: (
            EvidenceReference(fact_id=criterion_id + "_yes", relation=EvidenceRelation.SUPPORTING),
            EvidenceReference(
                fact_id=criterion_id + "_no", relation=EvidenceRelation.CONTRADICTING
            ),
        ),
        EvidenceStatus.MISSING: (),
        EvidenceStatus.NEEDS_REVIEW: (),
    }[status]
    return Finding(
        criterion_id=criterion_id,
        status=status,
        rationale="Independent test state.",
        evidence=evidence,
        unresolved_reasons=()
        if status in (EvidenceStatus.MET, EvidenceStatus.NOT_MET)
        else (criterion_id + "_" + status.value,),
    )


def applicable() -> ApplicabilityResult:
    return ApplicabilityResult(
        status=ApplicabilityStatus.APPLICABLE, rationale="Scope reviewed.", sources=(span(),)
    )


TRUTH_INDEX = {
    EvidenceStatus.MET: 0,
    EvidenceStatus.NOT_MET: 1,
    EvidenceStatus.MISSING: 2,
    EvidenceStatus.CONFLICTING: 2,
    EvidenceStatus.NEEDS_REVIEW: 2,
}
T, F, U = LogicalValue.TRUE, LogicalValue.FALSE, LogicalValue.UNKNOWN
TABLES = {
    "all": ((T, F, U), (F, F, F), (U, F, U)),
    "any": ((T, T, T), (T, F, U), (T, U, U)),
}


@pytest.mark.parametrize(
    ("kind", "left", "right"), tuple(product(("all", "any"), EvidenceStatus, EvidenceStatus))
)
def test_all_five_statuses_obey_three_valued_truth_tables(
    kind: str, left: EvidenceStatus, right: EvidenceStatus
) -> None:
    findings = (finding("a", left), finding("b", right))
    result = evaluate_policy(policy(kind), findings, applicable())
    assert result.logical_value == TABLES[kind][TRUTH_INDEX[left]][TRUTH_INDEX[right]]
    leaves = {trace.criterion_id: trace for trace in result.traces if trace.criterion_id}
    assert leaves["a"].finding == findings[0]
    assert leaves["b"].finding == findings[1]
    root = result.traces[0]
    assert set(root.unresolved_reasons) == {
        reason for item in findings for reason in item.unresolved_reasons
    }


def test_true_or_unknown_has_a_supporting_path_without_filling_unused_branch() -> None:
    findings = (finding("a", EvidenceStatus.MET), finding("b", EvidenceStatus.MISSING))
    result = evaluate_policy(policy("any"), findings, applicable())
    assert result.outcome == AssessmentOutcome.DOCUMENTED_REQUIREMENTS_SATISFIED
    assert result.satisfied_path == ("root", "a_node")
    assert result.traces[0].supporting_children == ("a_node",)
    assert result.traces[2].finding == findings[1]
    assert result.traces[0].unresolved_reasons == ("b_missing",)


def test_changing_and_to_or_changes_the_known_counterexample() -> None:
    findings = (finding("a", EvidenceStatus.MET), finding("b", EvidenceStatus.NOT_MET))
    assert (
        evaluate_policy(policy("all"), findings, applicable()).logical_value == LogicalValue.FALSE
    )
    assert evaluate_policy(policy("any"), findings, applicable()).logical_value == LogicalValue.TRUE


@pytest.mark.parametrize("blocker", ["section", "predicate", "issue", "unsupported_unit"])
def test_true_tree_cannot_override_known_governing_blockers(blocker: str) -> None:
    current = policy("any")
    issues: tuple[ReviewIssue, ...] = ()
    if blocker == "section":
        unresolved = PolicySection(
            section_id="exception",
            heading="Unresolved exception",
            sources=(span(),),
            disposition="unresolved",
            explanation="This mandatory exception has not been interpreted.",
        )
        current = changed(current, sections=(*current.sections, unresolved))
    elif blocker == "predicate":
        current = changed(
            current, criteria=(current.criteria[0], changed(current.criteria[1], predicate=None))
        )
    elif blocker == "unsupported_unit":
        unsupported = NumericPredicate(
            operator="gte", threshold=3.0, unit="months", context="therapy"
        )
        current = changed(
            current,
            criteria=(current.criteria[0], changed(current.criteria[1], predicate=unsupported)),
        )
    else:
        issues = (
            ReviewIssue(
                issue_id="omitted",
                category=IssueCategory.COMPLETENESS,
                message="Known governing requirement omitted from the graph.",
                action="Interpret the cited condition.",
                blocks_readiness=True,
                sources=(span(),),
            ),
        )
    result = evaluate_policy(
        current,
        (finding("a", EvidenceStatus.MET), finding("b", EvidenceStatus.MISSING)),
        applicable(),
        issues,
    )
    assert result.logical_value == LogicalValue.TRUE
    assert result.outcome == AssessmentOutcome.REVIEW_REQUIRED
    assert len(result.blockers) == 1
    assert result.satisfied_path == ("root", "a_node")


def test_nonblocking_issue_does_not_turn_an_unused_alternative_into_a_requirement() -> None:
    issue = ReviewIssue(
        issue_id="context",
        category=IssueCategory.EVIDENCE,
        message="Unused branch lacks history.",
        action="Inspect if that branch becomes relevant.",
        blocks_readiness=False,
    )
    result = evaluate_policy(
        policy("any"),
        (finding("a", EvidenceStatus.MET), finding("b", EvidenceStatus.MISSING)),
        applicable(),
        (issue,),
    )
    assert result.outcome == AssessmentOutcome.DOCUMENTED_REQUIREMENTS_SATISFIED
    assert result.blockers == ()


def test_scope_gates_do_not_produce_clinical_traces() -> None:
    mismatch = ApplicabilityResult(
        status=ApplicabilityStatus.MISMATCH, rationale="Different procedure.", sources=(span(),)
    )
    result = evaluate_policy(policy(), (), mismatch)
    assert result.logical_value is None and result.traces == ()
    assert result.outcome == AssessmentOutcome.APPLICABILITY_MISMATCH
    with pytest.raises(ValueError, match="before applicability"):
        evaluate_policy(policy(), (finding("a", EvidenceStatus.MET),), mismatch)


def test_missing_duplicate_and_unknown_finding_ids_are_rejected() -> None:
    one = finding("a", EvidenceStatus.MET)
    for findings in ((one,), (one, one), (one, finding("unknown", EvidenceStatus.MET))):
        with pytest.raises(ValueError, match="Exactly one finding"):
            evaluate_policy(policy(), findings, applicable())


def test_existing_schema_rejects_cycles_unknown_children_and_disconnected_graphs() -> None:
    current = policy()
    for root in (
        AllNode(node_id="root", children=("root", "a_node", "b_node"), sources=(span(),)),
        AllNode(node_id="root", children=("unknown", "a_node", "b_node"), sources=(span(),)),
        AllNode(node_id="root", children=("a_node",), sources=(span(),)),
    ):
        with pytest.raises(ValidationError):
            changed(current, nodes=(root, *current.nodes[1:]))


def json_file(path: str) -> dict[str, Any]:
    value: dict[str, Any] = json.loads((ROOT / path).read_text())
    return value


GOLD = json_file("evals/expected/development.json")["cases"]
MANIFEST = {item["case_id"]: item for item in json_file("evals/cases/development.json")["cases"]}
POLICIES = json_file("evals/expected/policies.json")["policies"]
SOURCES = json_file("evals/source-registry.json")["sources"]


def extraction_for_text(
    document_id: str, text: str, role: DocumentRole
) -> tuple[DocumentRecord, ExtractionRecord]:
    pages = re.split(r"<!-- page:\d+ -->", text)[1:] if "<!-- page:" in text else [text]
    digest = "a" * 64 if role == DocumentRole.POLICY else "b" * 64
    document = DocumentRecord(
        document_id=document_id,
        role=role,
        filename=document_id + ".md",
        sha256=digest,
        byte_count=len(text.encode()),
        page_count=len(pages),
        pages=tuple(PageInventory(page=i) for i in range(1, len(pages) + 1)),
        created_at=datetime(2026, 10, 18, tzinfo=UTC),
    )
    extraction = ExtractionRecord(
        extraction_id=document_id + "-logical-page-test",
        document_id=document_id,
        document_sha256=digest,
        parser_name="test-logical-pages-not-pdf",
        parser_version="1",
        configuration_sha256="c" * 64,
        created_at=document.created_at,
        pages=tuple(
            ExtractedPage(
                page=i,
                quality=PageQuality.USABLE,
                method=ExtractionMethod.NATIVE_TEXT,
                blocks=(TextBlock(block_id=f"p{i}", text=page, reading_order=0),),
            )
            for i, page in enumerate(pages, 1)
        ),
    )
    return document, extraction


@pytest.mark.parametrize(
    "case_id",
    [name for name, case in GOLD.items() if case["applicability"]["status"] == "applicable"],
)
def test_independent_development_annotations_aggregate_without_rewriting_gold(case_id: str) -> None:
    case = MANIFEST[case_id]
    expected = GOLD[case_id]
    annotation = POLICIES[case["policy_expectation_id"]]
    source_id = case["policy_source_id"]
    text = (ROOT / SOURCES[source_id]["path"]).read_text()
    document, extraction = extraction_for_text(source_id, text, DocumentRole.POLICY)
    resolver = CitationResolver((document,), (extraction,))

    def quote(item: dict[str, Any]) -> SourceSpan:
        return resolver.resolve(
            CandidateCitation(
                document_id=item["source_id"], page=item["page"], quote=item["excerpt"]
            )
        )

    criteria = tuple(
        Criterion(
            criterion_id=item["criterion_id"],
            wording=item["wording"],
            interpretation=item["wording"],
            sources=tuple(quote(ref) for ref in item["sources"]),
            predicate=NarrativePredicate(question=item["wording"]),
        )
        for item in annotation["criteria"]
    )
    connective = tuple(quote(ref) for ref in annotation["connective_sources"])
    node_data = tuple({**node, "sources": connective} for node in annotation["nodes"])
    sections = tuple(
        PolicySection(
            **{
                **item,
                "criterion_ids": tuple(item["criterion_ids"]),
                "sources": tuple(quote(ref) for ref in item["sources"]),
            }
        )
        for item in annotation["sections"]
    )
    current = Policy.model_validate(
        {
            "policy_id": source_id,
            "document_id": source_id,
            "document_sha256": document.sha256,
            "title": annotation["title"],
            "scope_summary": annotation["scope_summary"],
            "criteria": criteria,
            "nodes": tuple(
                {**node, **({"children": tuple(node["children"])} if "children" in node else {})}
                for node in node_data
            ),
            "root_id": annotation["root_id"],
            "sections": sections,
        }
    )
    findings = tuple(
        Finding(
            criterion_id=item["criterion_id"],
            status=EvidenceStatus(item["status"]),
            rationale=item["rationale"],
            evidence=tuple(
                EvidenceReference(
                    fact_id=f"{item['criterion_id']}_{i}",
                    relation=EvidenceRelation(reference["relation"]),
                )
                for i, reference in enumerate(item["evidence"])
            ),
            unresolved_reasons=tuple(item["unresolved_reasons"]),
        )
        for item in expected["findings"]
    )
    result = evaluate_policy(current, findings, applicable())
    assert result.logical_value == LogicalValue(expected["logical_value"])
    assert result.outcome == AssessmentOutcome(expected["outcome"])
    if "satisfied_path" in expected:
        assert result.satisfied_path == tuple(expected["satisfied_path"])


def numeric_finding_case(value: float = 2.7) -> tuple[CitationResolver, Policy, ChartFact, Finding]:
    policy_text = "Right vein diameter must be at least 3.0 mm."
    chart_text = f"Right vein diameter is {value} mm."
    p, pe = extraction_for_text("policy", policy_text, DocumentRole.POLICY)
    c, ce = extraction_for_text("chart", chart_text, DocumentRole.CHART)
    resolver = CitationResolver((p, c), (pe, ce))
    ps = resolver.resolve(CandidateCitation(document_id="policy", page=1, quote=policy_text))
    cs = resolver.resolve(CandidateCitation(document_id="chart", page=1, quote=chart_text))
    criterion = Criterion(
        criterion_id="diameter",
        wording=policy_text,
        interpretation="Compare stated diameter.",
        sources=(ps,),
        predicate=NumericPredicate(operator="gte", threshold=3.0, unit="mm", context="right vein"),
    )
    current = Policy(
        policy_id="numeric",
        document_id="policy",
        document_sha256=p.sha256,
        title="Numeric test",
        scope_summary="Artificial context.",
        criteria=(criterion,),
        nodes=(CriterionNode(node_id="root", criterion_id="diameter", sources=(ps,)),),
        root_id="root",
        sections=(
            PolicySection(
                section_id="requirements",
                heading="Diameter",
                sources=(ps,),
                disposition="requirements",
                criterion_ids=("diameter",),
                explanation="One numeric condition.",
            ),
        ),
    )
    fact = ChartFact(
        fact_id="measurement",
        proposition="Source diameter",
        sources=(cs,),
        polarity=FactPolarity.AFFIRMED,
        value=value,
        unit="mm",
        context=("right vein",),
    )
    candidate = Finding(
        criterion_id="diameter",
        status=EvidenceStatus.MET,
        rationale="Untrusted model says met.",
        evidence=(EvidenceReference(fact_id=fact.fact_id, relation=EvidenceRelation.SUPPORTING),),
    )
    return resolver, current, fact, candidate


def test_validated_finding_corrects_a_wrong_model_numeric_comparison() -> None:
    resolver, current, fact, candidate = numeric_finding_case()
    result = validate_findings(current, (fact,), (candidate,), resolver)[0]
    assert result.status == EvidenceStatus.NOT_MET
    assert result.evidence[0].relation == EvidenceRelation.CONTRADICTING
    assert candidate.status == EvidenceStatus.MET  # immutable candidate remains inspectable
    assert evaluate_policy(current, (result,), applicable()).logical_value == LogicalValue.FALSE


def test_fabricated_model_number_downgrades_to_review_instead_of_computing_true() -> None:
    resolver, current, fact, candidate = numeric_finding_case()
    fabricated = changed(fact, value=3.4)
    result = validate_findings(current, (fabricated,), (candidate,), resolver)[0]
    assert result.status == EvidenceStatus.NEEDS_REVIEW
    assert "unverified_or_ambiguous_numeric_value" in result.unresolved_reasons
    assert result.evidence[0].relation == EvidenceRelation.CONTEXT


def test_unknown_and_conflict_states_are_not_erased_by_numeric_recomputation() -> None:
    resolver, current, fact, candidate = numeric_finding_case(3.4)
    unknown = Finding(
        criterion_id="diameter",
        status=EvidenceStatus.NEEDS_REVIEW,
        rationale="Unresolved source context.",
        evidence=candidate.evidence,
        unresolved_reasons=("source_context",),
    )
    assert validate_findings(current, (fact,), (unknown,), resolver) == (unknown,)


def test_reference_validation_rejects_unknown_fact_and_conflict_references() -> None:
    resolver, current, fact, candidate = numeric_finding_case()
    with pytest.raises(EvidenceValidationError, match="unknown fact"):
        validate_findings(current, (), (candidate,), resolver)
    with pytest.raises(EvidenceValidationError, match="unknown conflicting fact"):
        validate_findings(
            current, (changed(fact, conflicting_fact_ids=("other",)),), (candidate,), resolver
        )


def test_two_source_supported_opposing_measurements_remain_conflicting() -> None:
    resolver, current, fact, candidate = numeric_finding_case(3.4)
    chart_text = "Right vein diameter is 3.4 mm.\nRight vein diameter is 2.7 mm."
    policy_text = "Right vein diameter must be at least 3.0 mm."
    p, pe = extraction_for_text("policy", policy_text, DocumentRole.POLICY)
    c, ce = extraction_for_text("chart", chart_text, DocumentRole.CHART)
    resolver = CitationResolver((p, c), (pe, ce))
    first = changed(
        fact,
        sources=(
            resolver.resolve(
                CandidateCitation(
                    document_id="chart", page=1, quote="Right vein diameter is 3.4 mm."
                )
            ),
        ),
    )
    second = changed(
        fact,
        fact_id="second",
        value=2.7,
        sources=(
            resolver.resolve(
                CandidateCitation(
                    document_id="chart", page=1, quote="Right vein diameter is 2.7 mm."
                )
            ),
        ),
    )
    both = changed(
        candidate,
        evidence=(
            *candidate.evidence,
            EvidenceReference(fact_id="second", relation=EvidenceRelation.SUPPORTING),
        ),
    )
    result = validate_findings(current, (first, second), (both,), resolver)[0]
    assert result.status == EvidenceStatus.CONFLICTING
    assert {reference.relation for reference in result.evidence} == {
        EvidenceRelation.SUPPORTING,
        EvidenceRelation.CONTRADICTING,
    }
