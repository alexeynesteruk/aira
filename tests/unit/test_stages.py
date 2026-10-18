"""Rendered stage inputs are the shared model-facing text form, not raw records."""

import json
from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from app.assessment.stages import (
    DocumentInputs,
    StageInputs,
    render_document_input,
    render_stage_input,
)
from app.schemas import (
    AllNode,
    BoundingBox,
    ChartData,
    ChartFact,
    Criterion,
    CriterionNode,
    DateAnnotation,
    DocumentRecord,
    DocumentRole,
    ExtractedPage,
    ExtractionMethod,
    ExtractionRecord,
    FactPolarity,
    FieldSources,
    NumericPredicate,
    PageInventory,
    PageQuality,
    Policy,
    PolicySection,
    RequestContext,
    RequestField,
    SourceSpan,
    TextAnnotation,
    TextBlock,
)

NOW = datetime(2026, 10, 18, tzinfo=UTC)
POLICY_SHA = "a" * 64
CHART_SHA = "b" * 64


def document(document_id: str, role: DocumentRole, sha256: str) -> DocumentRecord:
    return DocumentRecord(
        document_id=document_id,
        role=role,
        filename=f"{document_id}.pdf",
        sha256=sha256,
        byte_count=100,
        page_count=2,
        pages=(PageInventory(page=1), PageInventory(page=2)),
        created_at=NOW,
    )


def extraction(document_id: str, sha256: str) -> ExtractionRecord:
    return ExtractionRecord(
        extraction_id=f"{document_id}-extraction",
        document_id=document_id,
        document_sha256=sha256,
        parser_name="hand-built",
        parser_version="1",
        configuration_sha256="c" * 64,
        created_at=NOW,
        pages=(
            ExtractedPage(
                page=1,
                quality=PageQuality.USABLE,
                method=ExtractionMethod.NATIVE_TEXT,
                blocks=(
                    TextBlock(
                        block_id="p0001.b00000",
                        text=f"{document_id} first block",
                        reading_order=0,
                        bbox=BoundingBox(x0=0, y0=0, x1=10, y1=10),
                    ),
                    TextBlock(
                        block_id="p0001.b00001",
                        text=f"{document_id} second block",
                        reading_order=1,
                    ),
                ),
            ),
            ExtractedPage(page=2, quality=PageQuality.BLANK),
        ),
    )


@pytest.fixture
def inputs() -> StageInputs:
    return StageInputs(
        policy_document=document("policy-doc", DocumentRole.POLICY, POLICY_SHA),
        chart_document=document("chart-doc", DocumentRole.CHART, CHART_SHA),
        policy_extraction=extraction("policy-doc", POLICY_SHA),
        chart_extraction=extraction("chart-doc", CHART_SHA),
    )


def span(document_id: str = "policy-doc", sha256: str = POLICY_SHA) -> SourceSpan:
    return SourceSpan(
        document_id=document_id,
        document_sha256=sha256,
        extraction_id=f"{document_id}-extraction",
        page=1,
        block_id="p0001.b00000",
        start=0,
        end=4,
        excerpt="word",
        bbox=BoundingBox(x0=0, y0=0, x1=10, y1=10),
    )


def policy() -> Policy:
    source = span()
    numeric = Criterion(
        criterion_id="criterion-diameter",
        wording="The measured structure is at least 3.0 mm.",
        interpretation="The documented measurement reaches the threshold.",
        sources=(source,),
        context=("diameter",),
        predicate=NumericPredicate(operator="gte", threshold=3.0, unit="mm", context="diameter"),
    )
    unsupported = Criterion(
        criterion_id="criterion-narrative",
        wording="The history documents the indication.",
        interpretation="A clinical judgment that has no bounded comparison.",
        sources=(source,),
    )
    return Policy(
        policy_id="policy-interpretation",
        document_id="policy-doc",
        document_sha256=POLICY_SHA,
        title="Hand-built policy",
        scope_summary="Hand-built scope.",
        criteria=(numeric, unsupported),
        nodes=(
            AllNode(
                node_id="root",
                children=("node-diameter", "node-narrative"),
                sources=(source,),
            ),
            CriterionNode(
                node_id="node-diameter", criterion_id="criterion-diameter", sources=(source,)
            ),
            CriterionNode(
                node_id="node-narrative", criterion_id="criterion-narrative", sources=(source,)
            ),
        ),
        root_id="root",
        sections=(
            PolicySection(
                section_id="requirements",
                heading="Requirements",
                sources=(source,),
                disposition="requirements",
                criterion_ids=("criterion-diameter", "criterion-narrative"),
                explanation="Every extracted criterion is a requirement.",
            ),
        ),
    )


def chart_data() -> ChartData:
    return ChartData(
        document_id="chart-doc",
        document_sha256=CHART_SHA,
        facts=(
            ChartFact(
                fact_id="fact-heart-rate",
                proposition="The chart documents a resting heart rate of 44 bpm.",
                sources=(span("chart-doc", CHART_SHA),),
                polarity=FactPolarity.AFFIRMED,
            ),
        ),
    )


def assessed(inputs: StageInputs, **changes: object) -> StageInputs:
    return replace(inputs, policy=policy(), chart=chart_data(), **changes)


def test_scope_renders_saved_artifacts_without_raw_pages(inputs: StageInputs) -> None:
    packet = json.loads(render_stage_input(assessed(inputs), "scope"))
    assert packet["input_kind"] == "saved_document_interpretations"
    assert "documents" not in packet
    assert packet["policy"]["title"] == "Hand-built policy"
    assert packet["chart"]["facts"][0]["fact_id"] == "fact-heart-rate"
    assert packet["selected_request"] is None
    assert packet["staff_annotations"] == []
    rendered = json.dumps(packet)
    assert "policy-doc first block" not in rendered
    assert "chart-doc first block" not in rendered


def test_policy_stage_renders_only_the_policy_document(inputs: StageInputs) -> None:
    annotated = assessed(
        inputs,
        request_context=RequestContext(procedure="endovenous ablation"),
        annotations=(
            TextAnnotation(annotation_id="staff-plan", field="plan", value="Plan", created_at=NOW),
        ),
    )
    packet = json.loads(render_stage_input(annotated, "policy"))
    assert packet["input_kind"] == "pdf_text_blocks"
    assert [item["document_id"] for item in packet["documents"]] == ["policy-doc"]
    rendered = json.dumps(packet)
    assert "chart-doc" not in rendered
    assert "selected_request" not in packet
    assert "staff_annotations" not in packet
    assert "endovenous ablation" not in rendered


def test_chart_stage_renders_only_the_chart_document(inputs: StageInputs) -> None:
    packet = json.loads(
        render_document_input(DocumentInputs(inputs.chart_document, inputs.chart_extraction))
    )
    assert [item["document_id"] for item in packet["documents"]] == ["chart-doc"]
    rendered = json.dumps(packet)
    assert "policy-doc" not in rendered
    assert "selected_request" not in packet
    assert "criterion" not in rendered


def test_evidence_stage_renders_saved_facts_and_criteria(
    inputs: StageInputs,
) -> None:
    packet = json.loads(render_stage_input(assessed(inputs), "evidence", policy()))
    assert "documents" not in packet
    assert packet["chart"]["facts"][0]["fact_id"] == "fact-heart-rate"
    criteria = packet["criteria"]
    assert [item["criterion_id"] for item in criteria] == [
        "criterion-diameter",
        "criterion-narrative",
    ]
    first = criteria[0]
    assert set(first) == {
        "criterion_id",
        "wording",
        "interpretation",
        "context",
        "predicate",
    }
    assert first["context"] == ["diameter"]
    assert first["predicate"]["kind"] == "numeric"
    assert first["predicate"]["operator"] == "gte"
    assert criteria[1]["predicate"] is None


def test_stage_policy_argument_contract(inputs: StageInputs) -> None:
    with pytest.raises(ValueError, match="requires the interpreted policy"):
        render_stage_input(inputs, "evidence")
    for stage in ("scope", "policy"):
        with pytest.raises(ValueError, match="Only the evidence stage"):
            render_stage_input(inputs, stage, policy())


def test_rendering_is_deterministic(inputs: StageInputs) -> None:
    saved = assessed(inputs)
    first = render_stage_input(saved, "evidence", policy())
    assert render_stage_input(saved, "evidence", policy()) == first
    assert render_stage_input(saved, "scope") == render_stage_input(saved, "scope")


def test_pages_are_ordered_one_based_and_blank_pages_render_empty_blocks(
    inputs: StageInputs,
) -> None:
    packet = json.loads(render_stage_input(inputs, "policy"))
    pages = packet["documents"][0]["pages"]
    assert [page["page"] for page in pages] == [1, 2]
    assert pages[0] == {
        "page": 1,
        "quality": "usable",
        "blocks": ["policy-doc first block", "policy-doc second block"],
    }
    assert pages[1] == {"page": 2, "quality": "blank", "blocks": []}


def _keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_keys(item) for item in value))
    return set()


def test_render_omits_provenance_geometry_and_record_identity(inputs: StageInputs) -> None:
    rendered = render_stage_input(assessed(inputs), "evidence", policy())
    keys = _keys(json.loads(rendered))
    assert not keys & {
        "block_id",
        "bbox",
        "extraction_id",
        "sha256",
        "document_sha256",
        "field_sources",
        "sources",
        "reading_order",
        "issues",
        "table_id",
    }
    assert POLICY_SHA not in rendered and CHART_SHA not in rendered
    assert "policy-doc-extraction" not in rendered
    assert "p0001.b00000" not in rendered


def test_request_and_annotations_render_values_without_provenance(
    inputs: StageInputs,
) -> None:
    annotated = assessed(
        inputs,
        request_context=RequestContext(
            procedure="endovenous ablation",
            payer="Fixture Health",
            service_date=date(2026, 10, 30),
            unresolved_fields=(RequestField.PLAN,),
            field_sources=(
                FieldSources(field=RequestField.PROCEDURE, sources=(span("chart-doc", CHART_SHA),)),
            ),
        ),
        annotations=(
            TextAnnotation(
                annotation_id="staff-plan",
                field="plan",
                value="Fixture Plan B",
                created_at=NOW,
                resolves_conflict=True,
                resolution_reason="Staff selected the submitted plan.",
                original_sources=(span("chart-doc", CHART_SHA),),
            ),
            DateAnnotation(
                annotation_id="staff-cutoff",
                field="assessment_cutoff",
                value=date(2026, 10, 18),
                created_at=NOW,
            ),
        ),
    )
    packet = json.loads(render_stage_input(annotated, "scope"))
    request = packet["selected_request"]
    assert request["procedure"] == "endovenous ablation"
    assert request["service_date"] == "2026-10-30"
    assert request["assessment_cutoff"] is None
    assert request["unresolved_fields"] == ["plan"]
    assert "field_sources" not in request
    assert packet["staff_annotations"] == [
        {
            "field": "plan",
            "value": "Fixture Plan B",
            "resolves_conflict": True,
            "resolution_reason": "Staff selected the submitted plan.",
        },
        {
            "field": "assessment_cutoff",
            "value": "2026-10-18",
            "resolves_conflict": False,
            "resolution_reason": None,
        },
    ]


def test_no_request_context_renders_null(inputs: StageInputs) -> None:
    packet = json.loads(render_stage_input(assessed(inputs), "scope"))
    assert packet["selected_request"] is None
    assert packet["staff_annotations"] == []
