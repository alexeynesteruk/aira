"""Real PDF parsing checks, with injected failures clearly separated from fixtures."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pdfminer.psparser import LIT
from pdfplumber.page import Page

from app.documents import (
    NativePdfConfig,
    PdfInputError,
    extract_pdf,
    inspect_pdf,
    native,
    require_usable_extraction,
    source_span,
)
from app.schemas import DocumentRecord, DocumentRole, ExtractionRecord, PageQuality, TextBlock

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/pdf"
CHART = ROOT / "examples/charts/robert_mitchell_chart_final.pdf"
POLICIES = ROOT / "examples/guidelines"
CREATED_AT = datetime(2026, 10, 18, tzinfo=UTC)


def parse(
    path: Path, *, config: NativePdfConfig | None = None
) -> tuple[DocumentRecord, ExtractionRecord]:
    raw = path.read_bytes()
    document = inspect_pdf(
        raw,
        document_id=f"doc-{path.stem}",
        filename=path.name,
        role=DocumentRole.CHART,
        config=config,
        created_at=CREATED_AT,
    )
    return document, extract_pdf(raw, document, config=config, created_at=CREATED_AT)


@pytest.fixture(scope="module")
def native_result() -> tuple[DocumentRecord, ExtractionRecord]:
    return parse(FIXTURES / "native-layout.pdf")


@pytest.fixture(scope="module")
def chart_result() -> tuple[DocumentRecord, ExtractionRecord]:
    return parse(CHART)


def block_with(extraction: ExtractionRecord, page: int, text: str) -> TextBlock:
    return next(block for block in extraction.pages[page - 1].blocks if text in block.text)


def page_text(extraction: ExtractionRecord, page: int) -> str:
    return "\n".join(block.text for block in extraction.pages[page - 1].blocks)


def test_intake_hashes_original_bytes_without_claiming_extraction() -> None:
    raw = (FIXTURES / "native-layout.pdf").read_bytes()
    before = bytes(raw)
    document = inspect_pdf(
        raw,
        document_id="arbitrary-upload",
        filename="different-name.pdf",
        role=DocumentRole.POLICY,
        created_at=CREATED_AT,
    )
    assert raw == before
    assert document.sha256 == hashlib.sha256(before).hexdigest()
    assert document.byte_count == len(before)
    assert document.filename == "different-name.pdf" and document.role == DocumentRole.POLICY
    assert document.created_at == CREATED_AT
    assert [page.page for page in document.pages] == [1, 2]
    assert all(page.quality == PageQuality.UNINSPECTED for page in document.pages)


@pytest.mark.parametrize(
    ("data", "reason", "status"),
    [
        (b"", "not_pdf", 415),
        (b"A text document named .pdf", "not_pdf", 415),
        (b"%PDF-1.7\ntruncated", "malformed_pdf", 422),
        (b"%PDF-1.7\nThis is not a PDF object tree.\n%%EOF", "malformed_pdf", 422),
    ],
)
def test_rejects_non_pdf_and_malformed_bytes(data: bytes, reason: str, status: int) -> None:
    with pytest.raises(PdfInputError) as error:
        inspect_pdf(data, document_id="bad-input", filename="bad.pdf", role=DocumentRole.CHART)
    assert error.value.reason == reason and error.value.http_status == status
    assert error.value.error.retryable is False and error.value.error.action


def test_rejects_encryption_and_checks_inclusive_intake_limits() -> None:
    with pytest.raises(PdfInputError, match="Encrypted") as error:
        parse(FIXTURES / "encrypted.pdf")
    assert error.value.reason == "encrypted_pdf"
    raw = (FIXTURES / "native-layout.pdf").read_bytes()
    exact = NativePdfConfig(max_bytes=len(raw), max_pages=2)
    document = inspect_pdf(
        raw, document_id="limits", filename="test.pdf", role=DocumentRole.CHART, config=exact
    )
    assert document.page_count == 2
    for config, reason in (
        (replace(exact, max_bytes=len(raw) - 1), "byte_limit"),
        (replace(exact, max_pages=1), "page_limit"),
    ):
        with pytest.raises(PdfInputError) as failure:
            inspect_pdf(
                raw,
                document_id="limits",
                filename="test.pdf",
                role=DocumentRole.CHART,
                config=config,
            )
        assert failure.value.reason == reason and failure.value.http_status == 413


def test_table_rows_and_separate_columns_preserve_their_context(
    native_result: tuple[DocumentRecord, ExtractionRecord],
) -> None:
    document, extraction = native_result
    require_usable_extraction(document, extraction)
    marker_a = block_with(extraction, 1, "Marker A")
    marker_b = block_with(extraction, 1, "Marker B")
    assert marker_a.table_id and marker_b.table_id == marker_a.table_id
    rows = {
        block.column: block.text
        for block in extraction.pages[0].blocks
        if block.table_id == marker_a.table_id and block.row == marker_a.row
    }
    assert rows == {0: "Marker A", 1: "7.2 mg", 2: "right side"}
    assert marker_b.row != marker_a.row
    left = block_with(extraction, 1, "LEFT FIELD")
    right = block_with(extraction, 1, "RIGHT FIELD")
    assert "RIGHT FIELD" not in left.text and "LEFT FIELD" not in right.text
    assert left.bbox and right.bbox and left.bbox.x1 < right.bbox.x0
    for page in extraction.pages:
        for block in page.blocks:
            assert block.bbox and 0 <= block.bbox.x0 <= block.bbox.x1 <= 612
            assert 0 <= block.bbox.y0 <= block.bbox.y1 <= 792


def test_supplied_chart_retains_laboratory_rows_negation_and_conflicting_date_roles(
    chart_result: tuple[DocumentRecord, ExtractionRecord],
) -> None:
    document, extraction = chart_result
    require_usable_extraction(document, extraction)
    assert document.page_count == 7
    tsh = next(block for block in extraction.pages[2].blocks if block.text == "TSH")
    assert tsh.table_id is not None
    row = {
        block.column: block.text
        for block in extraction.pages[2].blocks
        if block.table_id == tsh.table_id and block.row == tsh.row
    }
    assert row == {0: "TSH", 1: "2.4 mIU/L", 2: "0.4-4.0", 3: "Normal"}
    assert "29 days, 14 hours" in block_with(extraction, 5, "Wear Duration:").text
    assert "Nov 12" in block_with(extraction, 5, "Longest Pause:").text
    assert "All nocturnal, during sleep" in block_with(extraction, 5, "Pause Context:").text
    assert "0 (zero)" in block_with(extraction, 5, "Symptom Events Logged:").text
    assert "November 1-29, 2025" in page_text(extraction, 5)
    assert "November 11, 2025" in page_text(extraction, 6)
    assert "AV Block: None." in page_text(extraction, 6)
    assert "No symptom-rhythm correlation can be established." in page_text(extraction, 6)
    assert "November 14" in block_with(extraction, 7, "PA Status:").text


def test_policy_snapshots_keep_versions_and_unchanged_clinical_pages_separate() -> None:
    old_doc, old = parse(POLICIES / "bcbs_fl_02-33000-31_2025-08-15.pdf")
    new_doc, new = parse(POLICIES / "bcbs_fl_02-33000-31_2026-01-01.pdf")
    require_usable_extraction(old_doc, old)
    require_usable_extraction(new_doc, new)
    assert old_doc.page_count == new_doc.page_count == 14
    assert old_doc.sha256 != new_doc.sha256 and old.extraction_id != new.extraction_id
    assert "Revised: 08/15/25" in page_text(old, 1)
    assert "Revised: 01/01/26" in page_text(new, 1)
    assert "Original Effective Date: 02/15/02" in page_text(old, 1)
    for page in (2, 3, 4):
        assert page_text(old, page) == page_text(new, page)
    assert page_text(old, 5) != page_text(new, 5)
    assert "at least 3 millimeters" in page_text(old, 2)


@pytest.mark.parametrize(
    ("filename", "quality", "issue"),
    [
        ("image-only.pdf", PageQuality.NEEDS_OCR, "unsupported_image_content"),
        ("mixed-page.pdf", PageQuality.UNUSABLE, "unsupported_image_content"),
        ("vector-only.pdf", PageQuality.UNUSABLE, "unusable_vector_content"),
        ("blank.pdf", PageQuality.BLANK, None),
    ],
)
def test_unreadable_and_all_blank_documents_never_pass_the_gate(
    filename: str, quality: PageQuality, issue: str | None
) -> None:
    document, extraction = parse(FIXTURES / filename)
    assert extraction.pages[0].quality == quality
    if issue:
        assert any(issue in item for item in extraction.pages[0].issues)
    with pytest.raises(PdfInputError) as failure:
        require_usable_extraction(document, extraction)
    assert failure.value.reason == "unusable_extraction"


def test_mixed_document_keeps_failed_and_blank_pages_in_original_order() -> None:
    document, extraction = parse(FIXTURES / "mixed-document.pdf")
    assert [page.page for page in extraction.pages] == [1, 2, 3]
    assert [page.quality for page in extraction.pages] == [
        PageQuality.USABLE,
        PageQuality.NEEDS_OCR,
        PageQuality.BLANK,
    ]
    assert document.page_count == 3
    with pytest.raises(PdfInputError) as failure:
        require_usable_extraction(document, extraction)
    assert failure.value.error.page == 2
    with pytest.raises(ValueError, match="unusable or blank"):
        source_span(extraction, page=2, block_id="p0002.b00000")


def test_blank_page_is_allowed_when_other_pages_are_usable() -> None:
    document, extraction = parse(FIXTURES / "native-with-blank.pdf")
    assert [page.quality for page in extraction.pages] == [PageQuality.USABLE, PageQuality.BLANK]
    require_usable_extraction(document, extraction)


@pytest.mark.parametrize("filename", ["annotation-only.pdf", "native-with-annotation.pdf"])
def test_visible_annotations_block_blank_and_usable_classification(filename: str) -> None:
    document, extraction = parse(FIXTURES / filename)
    assert extraction.pages[0].quality == PageQuality.UNUSABLE
    assert extraction.pages[0].blocks == ()
    assert "unsupported_annotations" in extraction.pages[0].issues[0]
    if filename == "native-with-annotation.pdf":
        assert extraction.pages[1].quality == PageQuality.USABLE
    with pytest.raises(PdfInputError) as failure:
        require_usable_extraction(document, extraction)
    assert failure.value.error.page == 1


def test_plain_navigation_links_preserve_native_labels_without_fetching_targets() -> None:
    document, extraction = parse(FIXTURES / "navigation-link.pdf")
    require_usable_extraction(document, extraction)
    page = extraction.pages[0]
    assert page.quality == PageQuality.USABLE
    assert "Visible native link label" in page_text(extraction, 1)
    assert "7.2 mg" in page_text(extraction, 1)
    assert "example.invalid" not in page_text(extraction, 1)
    assert any("navigation_links_retained: 1" in issue for issue in page.issues)


@pytest.mark.parametrize(
    "mutation",
    [
        "appearance",
        "contents",
        "title",
        "rich_text",
        "border",
        "no_border",
        "action",
        "extra_action",
    ],
)
def test_link_exemption_does_not_admit_visible_content_or_actions(
    monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    # Controlled annotation metadata on a real native PDF covers branches that
    # pdf-annotate does not author; it is not claimed to be another real fixture.
    data: dict[str, object] = {
        "Subtype": LIT("Link"),
        "Border": [0, 0, 0],
        "A": {"S": LIT("URI"), "URI": b"https://example.invalid/source"},
    }
    if mutation == "appearance":
        data["AP"] = {"N": b"visible appearance"}
    elif mutation == "contents":
        data["Contents"] = b"Amended measurement"
    elif mutation == "title":
        data["T"] = b"Annotation title"
    elif mutation == "rich_text":
        data["RC"] = b"<p>Amended measurement</p>"
    elif mutation == "border":
        data["Border"] = [0, 0, 1]
    elif mutation == "no_border":
        del data["Border"]
    elif mutation == "action":
        data["A"] = {"S": LIT("JavaScript"), "JS": b"do not execute"}
    else:
        data["AA"] = {"E": {"S": LIT("JavaScript")}}
    monkeypatch.setattr(Page, "annots", property(lambda _: [{"data": data}]))
    document, extraction = parse(FIXTURES / "native-layout.pdf")
    assert all(page.quality == PageQuality.UNUSABLE for page in extraction.pages)
    assert all("unsupported_annotations" in page.issues[0] for page in extraction.pages)
    with pytest.raises(PdfInputError):
        require_usable_extraction(document, extraction)


def test_per_page_failure_is_retained_without_hiding_later_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = Page.extract_words

    def fail_first(page: Page, **kwargs: Any) -> list[dict[str, Any]]:
        if page.page_number == 1:
            raise ValueError("injected PDF layout failure")
        return original(page, **kwargs)

    monkeypatch.setattr(Page, "extract_words", fail_first)
    document, extraction = parse(FIXTURES / "native-layout.pdf")
    assert [page.quality for page in extraction.pages] == [PageQuality.UNUSABLE, PageQuality.USABLE]
    assert "page_extraction_failed" in extraction.pages[0].issues[0]
    with pytest.raises(PdfInputError):
        require_usable_extraction(document, extraction)


def test_missing_native_characters_fail_quality_even_when_some_blocks_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = native._line_blocks

    def drop_a_line(
        page: Page, config: NativePdfConfig, boxes: list[native.Box]
    ) -> list[TextBlock]:
        return original(page, config, boxes)[:-1]

    monkeypatch.setattr(native, "_line_blocks", drop_a_line)
    document, extraction = parse(FIXTURES / "native-layout.pdf")
    assert extraction.pages[0].blocks
    assert extraction.pages[0].quality == PageQuality.UNUSABLE
    assert any("text_coverage_mismatch" in issue for issue in extraction.pages[0].issues)
    with pytest.raises(PdfInputError):
        require_usable_extraction(document, extraction)


@pytest.mark.parametrize(
    ("config", "issue"),
    [
        (NativePdfConfig(max_characters_per_page=10), "character_limit"),
        (NativePdfConfig(max_total_characters=10), "character_limit"),
        (NativePdfConfig(max_table_cells_per_page=1), "table_cell_limit"),
    ],
)
def test_extraction_budgets_are_explicit_and_never_drop_pages(
    config: NativePdfConfig, issue: str
) -> None:
    document, extraction = parse(FIXTURES / "native-layout.pdf", config=config)
    assert len(extraction.pages) == document.page_count == 2
    assert extraction.pages[0].quality == PageQuality.UNUSABLE
    assert issue in extraction.pages[0].issues[0]
    with pytest.raises(PdfInputError):
        require_usable_extraction(document, extraction)


def test_extraction_revisions_and_configuration_fingerprints_are_distinct(
    native_result: tuple[DocumentRecord, ExtractionRecord],
) -> None:
    document, first = native_result
    raw = (FIXTURES / "native-layout.pdf").read_bytes()
    second = extract_pdf(raw, document)
    changed = extract_pdf(raw, document, config=NativePdfConfig(x_tolerance=2.0))
    assert len({first.extraction_id, second.extraction_id, changed.extraction_id}) == 3
    assert first.configuration_sha256 == second.configuration_sha256
    assert first.configuration_sha256 != changed.configuration_sha256
    assert first.pages == second.pages
    assert first.parser_name == "pdfplumber" and first.parser_version
    with pytest.raises(PdfInputError) as failure:
        extract_pdf((FIXTURES / "blank.pdf").read_bytes(), document)
    assert failure.value.reason == "identity_mismatch"


def test_exact_spans_retain_hash_revision_offsets_and_original_pages(
    chart_result: tuple[DocumentRecord, ExtractionRecord],
) -> None:
    document, extraction = chart_result
    pause = block_with(extraction, 5, "Longest Pause:")
    start = pause.text.index("3.1")
    span = source_span(extraction, page=5, block_id=pause.block_id, start=start, end=start + 3)
    assert span.excerpt == "3.1" and span.document_sha256 == document.sha256
    assert (
        span.document_id == document.document_id and span.extraction_id == extraction.extraction_id
    )
    assert span.bbox == pause.bbox
    signature = block_with(extraction, 6, "November 11, 2025")
    other = source_span(extraction, page=6, block_id=signature.block_id)
    assert (span.page, other.page) == (5, 6)
    assert other.excerpt == signature.text
    for arguments in (
        {"page": 6, "block_id": pause.block_id},
        {"page": 0, "block_id": pause.block_id},
        {"page": 5, "block_id": pause.block_id, "start": -1},
        {"page": 5, "block_id": pause.block_id, "end": len(pause.text) + 1},
    ):
        with pytest.raises(ValueError):
            source_span(extraction, **arguments)  # type: ignore[arg-type]


def test_fixture_hashes_match_the_recorded_pdf_tools_outputs() -> None:
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    for fixture in manifest["fixtures"]:
        path = FIXTURES / fixture["filename"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == fixture["sha256"]
        assert fixture["origin"] == "fictional_pdf_tools_fixture"
        assert fixture["creation_commands"] and fixture["inspection"]
