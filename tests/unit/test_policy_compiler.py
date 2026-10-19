"""Pure compiler negative controls; synthetic source text is independently authored."""

from dataclasses import replace

import pytest
from long_support import fragment, wire
from support import CREATED_AT

from app.policies.compiler import BuildLimits, compile_policy, plan_sections, validate_section
from app.schemas import (
    DocumentRecord,
    DocumentRole,
    ExtractedPage,
    ExtractionMethod,
    ExtractionRecord,
    PageInventory,
    PageQuality,
    TextBlock,
)
from app.schemas.builds import AuditCandidate, ReconciliationCandidate, SectionCandidate


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


@pytest.mark.parametrize("mutation", ["drop_path", "rewrite_local", "unknown_edge"])
def test_reconciliation_cannot_drop_a_local_branch_or_rewrite_local_rules(mutation):
    doc, extraction, sections, reconciliation, audits = source()
    data = reconciliation.model_dump(mode="json")
    if mutation == "drop_path":
        data["paths"] = data["paths"][:1]
    elif mutation == "rewrite_local":
        data["nodes"] = [
            dict(
                node_id=sections[0].policy.root_id,
                kind="all",
                children=[sections[1].policy.root_id],
                criterion_id=None,
                citations=data["paths"][0]["citations"],
            )
        ]
    else:
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
    with pytest.raises(ValueError):
        compile_policy(
            doc,
            extraction,
            sections,
            wire(ReconciliationCandidate, **data),
            audits,
            policy_id="invalid",
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
