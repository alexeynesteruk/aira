"""Pure compiler negative controls; synthetic source text is independently authored."""

from dataclasses import replace
from datetime import date

import pytest
from long_support import fragment, wire
from support import CREATED_AT

from app.policies.compiler import (
    BuildLimits,
    assemble_merged,
    audit_packet,
    compile_policy,
    group_packet,
    merge_slices,
    plan_sections,
    require_resolutions,
    validate_section,
)
from app.schemas import (
    DocumentRecord,
    DocumentRole,
    ExtractedPage,
    ExtractionMethod,
    ExtractionRecord,
    PageInventory,
    PageQuality,
    SourceSpan,
    TextBlock,
)
from app.schemas.builds import (
    AuditCandidate,
    ReconciliationCandidate,
    ReconciliationGroup,
    SectionCandidate,
    SectionPlan,
    SectionResult,
    SourceUnit,
)


def source():
    pages = tuple(
        ExtractedPage(
            page=i,
            quality=PageQuality.USABLE,
            method=ExtractionMethod.NATIVE_TEXT,
            blocks=(
                TextBlock(
                    block_id=f"p{i}.rule",
                    text=f"{family} requires documented condition R{i:03}.",
                    reading_order=0,
                ),
            ),
        )
        for i, family in enumerate(("Alpha", "Beta"), 1)
    )
    doc = DocumentRecord(
        document_id="policy",
        role=DocumentRole.POLICY,
        filename="fictional.pdf",
        sha256="a" * 64,
        byte_count=1,
        page_count=2,
        pages=(PageInventory(page=1), PageInventory(page=2)),
        created_at=CREATED_AT,
    )
    extraction = ExtractionRecord(
        extraction_id="extraction",
        document_id=doc.document_id,
        document_sha256=doc.sha256,
        parser_name="synthetic",
        parser_version="1",
        configuration_sha256="b" * 64,
        created_at=CREATED_AT,
        pages=pages,
    )
    plans = plan_sections(extraction, replace(BuildLimits(), primary_tokens=600))
    sections = tuple(
        validate_section(
            doc,
            extraction,
            plan,
            wire(
                SectionCandidate,
                dispositions=[
                    dict(
                        unit_id=unit.unit_id,
                        kind="requirements",
                        explanation="Mandatory condition.",
                    )
                    for unit in plan.primary
                ],
                fragment=fragment(doc.document_id, plan.primary),
                definitions=[],
                dependencies=[],
                issues=[],
            ),
        )
        for plan in plans
    )
    paths = [
        dict(
            path_id=path.path_id,
            title=path.title,
            scope=path.scope,
            root_id=path.root_id,
            citations=[
                dict(document_id=span.document_id, page=span.page, quote=span.excerpt)
                for span in path.sources
            ],
        )
        for section in sections
        for path in section.policy.paths
    ]
    reconciliation = wire(ReconciliationCandidate, nodes=[], paths=paths, resolutions=[], issues=[])
    audits = tuple(
        AuditCandidate(
            checked_unit_ids=tuple(unit.unit_id for unit in section.plan.primary),
            missing_conditions=(),
            issues=(),
        )
        for section in sections
    )
    return doc, extraction, sections, reconciliation, audits


def test_compiler_preserves_metadata_established_by_a_later_section():
    doc, extraction, sections, reconciliation, audits = source()
    first, second = sections
    sections = (
        first.model_copy(
            update={
                "policy": first.policy.model_copy(
                    update={"identifier": None, "revision_date": None}
                )
            }
        ),
        second.model_copy(
            update={
                "policy": second.policy.model_copy(
                    update={
                        "identifier": "GUIDE-2",
                        "revision_date": date(2026, 1, 1),
                        "effective_from": date(2026, 2, 1),
                    }
                )
            }
        ),
    )
    policy, _ = compile_policy(
        doc, extraction, sections, reconciliation, audits, policy_id="compiled"
    )
    assert policy.identifier == "GUIDE-2"
    assert policy.revision_date == date(2026, 1, 1)
    assert policy.effective_from == date(2026, 2, 1)
    assert not any("Conflicting policy" in issue.message for issue in policy.issues)


def test_compiler_keeps_conflicting_metadata_as_a_blocking_issue():
    doc, extraction, sections, reconciliation, audits = source()
    first, second = sections
    sections = (
        first.model_copy(
            update={"policy": first.policy.model_copy(update={"identifier": "GUIDE-1"})}
        ),
        second.model_copy(
            update={"policy": second.policy.model_copy(update={"identifier": "GUIDE-2"})}
        ),
    )
    policy, _ = compile_policy(
        doc, extraction, sections, reconciliation, audits, policy_id="compiled"
    )
    assert policy.identifier == "GUIDE-1"
    assert any(issue.blocks_readiness and "identifier" in issue.message for issue in policy.issues)


def test_rules_without_a_requirements_label_stay_in_the_build():
    doc, extraction, sections, _, _ = source()
    plan = sections[0].plan
    candidate = sections[0].candidate
    dispositions = tuple(
        item.model_copy(update={"kind": "context"}) for item in candidate.dispositions
    )
    result = validate_section(
        doc,
        extraction,
        plan,
        candidate.model_copy(update={"dispositions": dispositions}),
    )
    assert result.policy is not None
    assert result.policy.criteria
    assert any("not marked as requirements" in issue for issue in result.candidate.issues)


def test_a_requirements_section_without_rules_stays_in_the_build():
    doc, extraction, sections, _, _ = source()
    plan = sections[0].plan
    empty = sections[0].candidate.fragment.model_copy(update={"criteria": (), "nodes": ()})
    result = validate_section(
        doc,
        extraction,
        plan,
        sections[0].candidate.model_copy(update={"fragment": empty}),
    )
    assert result.policy is None
    assert any("did not produce a cited rule" in issue for issue in result.candidate.issues)


def test_compiler_preserves_all_local_edges_and_omission_audit_blocks_readiness():
    doc, extraction, sections, reconciliation, audits = source()
    audits = (
        audits[0].model_copy(
            update={"missing_conditions": ("The governing exception is not encoded.",)}
        ),
        *audits[1:],
    )
    policy, coverage = compile_policy(
        doc, extraction, sections, reconciliation, audits, policy_id="compiled"
    )
    assert policy.nodes == tuple(node for section in sections for node in section.policy.nodes)
    assert len(coverage) == 2
    assert any(issue.blocks_readiness and "exception" in issue.message for issue in policy.issues)


def test_reconciliation_cannot_rewrite_a_local_rule():
    doc, extraction, sections, reconciliation, audits = source()
    data = reconciliation.model_dump(mode="json")
    data["nodes"] = [
        dict(
            node_id=sections[0].policy.root_id,
            kind="all",
            children=[sections[1].policy.root_id],
            criterion_id=None,
            citations=data["paths"][0]["citations"],
        )
    ]
    with pytest.raises(ValueError, match="cannot introduce or rewrite local criteria"):
        compile_policy(
            doc,
            extraction,
            sections,
            wire(ReconciliationCandidate, **data),
            audits,
            policy_id="invalid",
        )


def test_an_omitted_section_keeps_its_local_path():
    doc, extraction, sections, reconciliation, audits = source()
    data = reconciliation.model_dump(mode="json")
    data["paths"] = data["paths"][:1]
    policy, _ = compile_policy(
        doc,
        extraction,
        sections,
        wire(ReconciliationCandidate, **data),
        audits,
        policy_id="compiled",
    )
    local_ids = {node.node_id for section in sections for node in section.policy.nodes}
    assert local_ids <= {node.node_id for node in policy.nodes}
    assert sections[1].policy.root_id in {path.root_id for path in policy.paths}
    assert any(
        issue.blocks_readiness and "local path was kept" in issue.message for issue in policy.issues
    )


def test_a_leaf_path_keeps_the_rest_of_the_saved_section():
    doc, extraction, sections, reconciliation, audits = source()
    data = reconciliation.model_dump(mode="json")
    leaf_id = next(node.node_id for node in sections[0].policy.nodes if node.kind == "criterion")
    data["paths"][0]["root_id"] = leaf_id
    policy, _ = compile_policy(
        doc,
        extraction,
        sections,
        wire(ReconciliationCandidate, **data),
        audits,
        policy_id="compiled",
    )
    assert sections[0].policy.root_id in {path.root_id for path in policy.paths}
    local_ids = {node.node_id for node in sections[0].policy.nodes}
    assert local_ids <= {node.node_id for node in policy.nodes}


def test_an_unresolved_reconciliation_quote_keeps_the_local_rules():
    doc, extraction, sections, reconciliation, audits = source()
    data = reconciliation.model_dump(mode="json")
    data["paths"][0]["citations"] = [
        dict(document_id=doc.document_id, page=1, quote="this sentence is not in the source")
    ]
    data["nodes"] = [
        dict(
            node_id="joined",
            kind="all",
            children=[section.policy.root_id for section in sections],
            criterion_id=None,
            citations=[
                dict(
                    document_id=doc.document_id,
                    page=1,
                    quote="this sentence is not in the source",
                )
            ],
        )
    ]
    policy, _ = compile_policy(
        doc,
        extraction,
        sections,
        wire(ReconciliationCandidate, **data),
        audits,
        policy_id="compiled",
    )
    local_ids = {node.node_id for section in sections for node in section.policy.nodes}
    assert local_ids <= {node.node_id for node in policy.nodes}
    assert "joined" not in {node.node_id for node in policy.nodes}
    assert any(issue.blocks_readiness and "not found" in issue.message for issue in policy.issues)


def test_an_unknown_reconciliation_edge_is_not_added():
    doc, extraction, sections, reconciliation, audits = source()
    data = reconciliation.model_dump(mode="json")
    data["nodes"] = [
        dict(
            node_id="fabricated",
            kind="all",
            children=["unknown"],
            criterion_id=None,
            citations=data["paths"][0]["citations"],
        )
    ]
    data["paths"][0]["root_id"] = "fabricated"
    policy, _ = compile_policy(
        doc,
        extraction,
        sections,
        wire(ReconciliationCandidate, **data),
        audits,
        policy_id="compiled",
    )
    assert "fabricated" not in {node.node_id for node in policy.nodes}
    assert all("unknown" not in getattr(node, "children", ()) for node in policy.nodes)
    assert sections[0].policy.root_id in {path.root_id for path in policy.paths}
    assert any(issue.blocks_readiness for issue in policy.issues)


def _join_sections(reconciliation, sections):
    data = reconciliation.model_dump(mode="json")
    citation = data["paths"][0]["citations"]
    data["nodes"] = [
        dict(
            node_id="joined",
            kind="all",
            children=[section.policy.root_id for section in sections],
            criterion_id=None,
            citations=citation,
        )
    ]
    for path in data["paths"]:
        path["root_id"] = "joined"
    return data


@pytest.mark.parametrize("criterion_id", ["crit_reflux", "null", "", "   "])
def test_reconciliation_keeps_a_group_when_criterion_id_is_filled_in(criterion_id):
    doc, extraction, sections, reconciliation, audits = source()
    data = _join_sections(reconciliation, sections)
    data["nodes"][0]["criterion_id"] = criterion_id
    policy, _ = compile_policy(
        doc,
        extraction,
        sections,
        wire(ReconciliationCandidate, **data),
        audits,
        policy_id="compiled",
    )
    joined = next(node for node in policy.nodes if node.node_id == "joined")
    assert joined.kind == "all"
    assert [node.node_id for node in policy.nodes if node.node_id == "joined"] == ["joined"]
    local_ids = {node.node_id for section in sections for node in section.policy.nodes}
    assert local_ids <= {node.node_id for node in policy.nodes}
    if criterion_id == "crit_reflux":
        assert any(
            issue.blocks_readiness
            and "crit_reflux" in issue.message
            and "not applied" in issue.message
            for issue in policy.issues
        )
    else:
        assert not any("not applied" in issue.message for issue in policy.issues)


def test_reconciliation_does_not_add_a_local_criterion():
    doc, extraction, sections, reconciliation, audits = source()
    data = reconciliation.model_dump(mode="json")
    data["nodes"] = [
        dict(
            node_id="extra-rule",
            kind="criterion",
            children=[],
            criterion_id="invented",
            citations=data["paths"][0]["citations"],
        )
    ]
    before = {node.node_id for section in sections for node in section.policy.nodes}
    policy, _ = compile_policy(
        doc,
        extraction,
        sections,
        wire(ReconciliationCandidate, **data),
        audits,
        policy_id="compiled",
    )
    assert {node.node_id for node in policy.nodes} == before
    assert all(getattr(node, "criterion_id", None) != "invented" for node in policy.nodes)
    assert any(
        issue.blocks_readiness and "cannot introduce or rewrite" in issue.message
        for issue in policy.issues
    )


def test_reconciliation_drops_an_unknown_child_and_keeps_the_local_group():
    doc, extraction, sections, reconciliation, audits = source()
    data = _join_sections(reconciliation, sections)
    data["nodes"][0]["children"].append("invented-child")
    policy, _ = compile_policy(
        doc,
        extraction,
        sections,
        wire(ReconciliationCandidate, **data),
        audits,
        policy_id="compiled",
    )
    joined = next(node for node in policy.nodes if node.node_id == "joined")
    assert "invented-child" not in joined.children
    assert any(
        issue.blocks_readiness and "invented-child" in issue.message for issue in policy.issues
    )


def test_oversized_atomic_unit_is_rejected_without_truncation():
    _, extraction, *_ = source()
    with pytest.raises(ValueError, match="no text was cut"):
        plan_sections(extraction, replace(BuildLimits(), primary_tokens=1))


def test_planner_retains_table_header_context_without_duplicating_primary_blocks():
    _, extraction, *_ = source()
    header = TextBlock(block_id="header", text="ALPHA TABLE", reading_order=0, table_id="table")
    rows = tuple(
        TextBlock(
            block_id=f"row-{i}",
            text=f"Documented condition R{i:03} applies.",
            reading_order=i,
            table_id="table",
            row=i,
            column=0,
        )
        for i in (1, 2, 3)
    )
    page = ExtractedPage(
        page=1,
        quality=PageQuality.USABLE,
        method=ExtractionMethod.NATIVE_TEXT,
        blocks=(header, *rows),
    )
    extraction = extraction.model_copy(update={"pages": (page,)})
    plans = plan_sections(extraction, replace(BuildLimits(), primary_tokens=600))
    assert len(plans) > 1
    primary = [unit.source.block_id for plan in plans for unit in plan.primary]
    assert primary == ["header", "row-1", "row-2", "row-3"]
    assert all(any(unit.source.block_id == "header" for unit in plan.context) for plan in plans[1:])


def _referenced_section(section_id: str, reference_id: str) -> SectionResult:
    excerpt = f"Source text for {section_id}."
    span = SourceSpan(
        document_id="policy",
        document_sha256="a" * 64,
        extraction_id="extraction",
        page=1,
        block_id=f"b-{section_id}",
        start=0,
        end=len(excerpt),
        excerpt=excerpt,
    )
    return SectionResult(
        section_id=section_id,
        plan=SectionPlan(
            section_id=section_id,
            primary=(SourceUnit(unit_id=f"u-{section_id}", source=span),),
        ),
        candidate=wire(
            SectionCandidate,
            dispositions=[],
            fragment=None,
            definitions=[],
            dependencies=[
                dict(
                    reference_id=reference_id,
                    target=f"Outside material {reference_id}",
                    kind="reference",
                    citations=[dict(document_id="policy", page=1, quote=excerpt)],
                )
            ],
            issues=[],
        ),
    )


def test_merge_slices_keep_every_reference_when_one_packet_does_not_fit():
    sections = tuple(
        _referenced_section(f"section-{index:04}", f"ref-{index}") for index in range(1, 4)
    )
    group = wire(
        ReconciliationGroup,
        group_id="group-1:",
        section_ids=["section-0001"],
        result=dict(nodes=[], paths=[], resolutions=[], issues=[]),
    )

    def fits(packet: dict[str, object]) -> bool:
        references = packet["references"]
        assert isinstance(references, list)
        groups = packet["groups"]
        assert isinstance(groups, list)
        if groups:
            return len(references) <= 1
        return len(references) <= 2

    slices = merge_slices((group,), sections, fits)
    assert len(slices) == 2
    assert slices[0][0] == (group,)
    assert [section.section_id for section in slices[0][1]] == ["section-0001"]
    assert slices[1][0] == ()
    assert [section.section_id for section in slices[1][1]] == ["section-0002", "section-0003"]
    assert merge_slices((group,), sections[:1], fits) == (((group,), sections[:1]),)
    covered = [
        section.section_id + ":" + reference.reference_id
        for _, slice_sections in slices
        for section in slice_sections
        for reference in section.candidate.dependencies
    ]
    assert covered == [
        "section-0001:ref-1",
        "section-0002:ref-2",
        "section-0003:ref-3",
    ]
    assert all(
        fits(group_packet(slice_groups, slice_sections)) for slice_groups, slice_sections in slices
    )

    first = wire(
        ReconciliationCandidate,
        nodes=[],
        paths=[
            dict(
                path_id="alpha",
                title="Alpha",
                scope="Alpha procedure",
                root_id="section-0001:root",
                citations=[
                    dict(document_id="policy", page=1, quote="Source text for section-0001.")
                ],
            )
        ],
        resolutions=[
            dict(
                reference_id="section-0001:ref-1",
                target_section_ids=[],
                explanation="Named outside the guideline.",
                status="unresolved",
            )
        ],
        issues=["first"],
    )
    second = wire(
        ReconciliationCandidate,
        nodes=[],
        paths=[
            dict(
                path_id="alpha",
                title="Alpha duplicate",
                scope="Ignored duplicate path id.",
                root_id="other",
                citations=[
                    dict(document_id="policy", page=1, quote="Source text for section-0002.")
                ],
            )
        ],
        resolutions=[
            dict(
                reference_id="section-0002:ref-2",
                target_section_ids=[],
                explanation="Named outside the guideline.",
                status="unresolved",
            ),
            dict(
                reference_id="section-0003:ref-3",
                target_section_ids=[],
                explanation="Named outside the guideline.",
                status="unresolved",
            ),
        ],
        issues=["second"],
    )
    require_resolutions(first, {"section-0001:ref-1"})
    with pytest.raises(ValueError, match="exactly one resolution"):
        require_resolutions(first, {"section-0001:ref-1", "section-0002:ref-2"})
    assembled = assemble_merged((group,), (first, second))
    assert [item.reference_id for item in assembled.resolutions] == covered
    assert [path.path_id for path in assembled.paths] == ["alpha"]
    assert assembled.issues == ("first", "second")


def test_audit_packet_keeps_the_source_and_this_sections_resolutions():
    document, _extraction, sections, reconciliation, _audits = source()
    section, other = sections
    packet = audit_packet(
        document,
        section,
        wire(
            ReconciliationCandidate,
            nodes=reconciliation.nodes,
            paths=reconciliation.paths,
            resolutions=[
                {
                    "reference_id": section.section_id + ":own",
                    "target_section_ids": [],
                    "explanation": "This section's reference.",
                    "status": "unresolved",
                },
                {
                    "reference_id": other.section_id + ":other",
                    "target_section_ids": [section.section_id],
                    "explanation": "Points at this section.",
                    "status": "resolved",
                },
                {
                    "reference_id": other.section_id + ":bibliography",
                    "target_section_ids": [],
                    "explanation": "Unrelated bibliography.",
                    "status": "unresolved",
                },
            ],
            issues=list(reconciliation.issues),
        ),
    )
    texts = [unit["text"] for unit in packet["source"]["primary"]]
    assert section.plan.primary[0].source.excerpt in texts
    policy = packet["interpretation"]["policy"]
    assert isinstance(policy, dict)
    criteria = policy["criteria"]
    assert isinstance(criteria, list) and criteria[0]["wording"]
    assert [item["reference_id"] for item in packet["reconciliation"]["resolutions"]] == [
        section.section_id + ":own",
        other.section_id + ":other",
    ]
