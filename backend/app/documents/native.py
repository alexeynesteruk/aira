"""Bounded native-text extraction with complete original-page accounting.

The adapter knows PDF layout, not patient facts or policy rules. Its provisional
resource limits are distinct from the model's eventual measured input envelope.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from io import BytesIO
from typing import cast
from uuid import uuid4

import pdfplumber
from pdfminer.pdfdocument import PDFEncryptionError, PDFPasswordIncorrect
from pdfminer.pdfpage import PDFPage
from pdfminer.psparser import PSLiteral, literal_name
from pdfplumber.page import Page
from pdfplumber.pdf import PDF
from pdfplumber.table import Table
from pdfplumber.utils.exceptions import PdfminerException

from app.schemas import (
    BoundingBox,
    DocumentRecord,
    DocumentRole,
    ErrorCode,
    ExtractedPage,
    ExtractionMethod,
    ExtractionRecord,
    OperationalError,
    PageInventory,
    PageQuality,
    RunPhase,
    SourceSpan,
    TextBlock,
)

ADAPTER_VERSION = "0.1.1"
PARSER_VERSION = f"{pdfplumber.__version__}+aira.{ADAPTER_VERSION}"
UNMAPPED_GLYPH = re.compile(r"\(cid:\d+\)|\ufffd")
type Box = tuple[float, float, float, float]


@dataclass(frozen=True)
class NativePdfConfig:
    """Provisional parser guardrails, all included in the configuration hash."""

    max_bytes: int = 10 * 1024 * 1024
    max_pages: int = 100
    max_characters_per_page: int = 50_000
    max_total_characters: int = 500_000
    max_table_cells_per_page: int = 10_000
    x_tolerance: float = 3.0
    y_tolerance: float = 3.0
    column_gap: float = 30.0
    ocr_enabled: bool = True
    ocr_command: str = "tesseract"
    ocr_languages: str = "eng"

    def __post_init__(self) -> None:
        for name in (
            "max_bytes",
            "max_pages",
            "max_characters_per_page",
            "max_total_characters",
            "max_table_cells_per_page",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        for name in ("x_tolerance", "y_tolerance", "column_gap"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be positive and finite")

    @property
    def sha256(self) -> str:
        payload = {
            "adapter_version": ADAPTER_VERSION,
            "pdfplumber_version": pdfplumber.__version__,
            "pdfminer_version": version("pdfminer.six"),
            "settings": asdict(self),
            "table_strategy": "lines",
            "overlapping_tables": "largest_nonoverlapping",
            "unicode_normalization": None,
            "expand_ligatures": False,
            "image_content": "reject",
            "annotations": "reject_except_noncontent_zero_border_uri_or_goto_links",
            "ocr_enabled": self.ocr_enabled,
            "ocr_command": self.ocr_command,
            "ocr_languages": self.ocr_languages,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class PdfInputError(ValueError):
    """Actionable boundary error; carries no source content or parser traceback."""

    def __init__(
        self,
        reason: str,
        message: str,
        *,
        action: str,
        http_status: int = 422,
        document_id: str | None = None,
        page: int | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.http_status = http_status
        self.error = OperationalError(
            code=ErrorCode.EXTRACTION_FAILED
            if reason in {"malformed_pdf", "identity_mismatch", "unusable_extraction"}
            else ErrorCode.UNSUPPORTED_INPUT,
            message=message,
            action=action,
            retryable=False,
            stage=RunPhase.EXTRACTING,
            document_id=document_id,
            page=page,
        )


class _PageLimitExceeded(ValueError):
    pass


def _validate_bytes(data: bytes, config: NativePdfConfig) -> None:
    if len(data) > config.max_bytes:
        raise PdfInputError(
            "byte_limit",
            f"The PDF exceeds the configured {config.max_bytes}-byte upload limit.",
            action="Upload a smaller complete document or change the configured input limit.",
            http_status=413,
        )
    if not data.startswith(b"%PDF-"):
        raise PdfInputError(
            "not_pdf",
            "The upload does not have a PDF signature.",
            action="Upload an original PDF document.",
            http_status=415,
        )
    if b"%%EOF" not in data[-1024:]:
        raise PdfInputError(
            "malformed_pdf",
            "The PDF is incomplete or has no supported end marker.",
            action="Export the complete document as a new PDF and upload it again.",
        )


def _open_pdf(data: bytes) -> PDF:
    try:
        pdf = pdfplumber.open(BytesIO(data), strict_metadata=True, unicode_norm=None)
    except Exception as exc:
        underlying = exc.args[0] if isinstance(exc, PdfminerException) and exc.args else exc
        if isinstance(underlying, (PDFPasswordIncorrect, PDFEncryptionError)):
            raise PdfInputError(
                "encrypted_pdf",
                "Encrypted PDFs are not supported.",
                action="Upload an unencrypted copy of the document.",
            ) from exc
        raise PdfInputError(
            "malformed_pdf",
            "The PDF cannot be read.",
            action="Export a readable PDF and upload it again.",
        ) from exc
    if pdf.doc.encryption is not None:
        pdf.close()
        raise PdfInputError(
            "encrypted_pdf",
            "Encrypted PDFs are not supported, even with an empty password.",
            action="Upload an unencrypted copy of the document.",
        )
    if pdf.doc.catalog.get("AcroForm") is not None:
        pdf.close()
        raise PdfInputError(
            "interactive_form",
            "Interactive PDF forms are outside the native-text input boundary.",
            action="Export a flattened, native-text PDF including the completed form values.",
        )
    return pdf


def _page_count(pdf: PDF, config: NativePdfConfig) -> int:
    count = 0
    try:
        for _ in PDFPage.create_pages(pdf.doc):
            count += 1
            if count > config.max_pages:
                raise PdfInputError(
                    "page_limit",
                    f"The PDF exceeds the configured {config.max_pages}-page limit.",
                    action="Upload a complete document within the supported page limit.",
                    http_status=413,
                )
    except PdfInputError:
        raise
    except Exception as exc:
        raise PdfInputError(
            "malformed_pdf",
            "The PDF page inventory cannot be read.",
            action="Export a readable PDF with a valid page tree and upload it again.",
        ) from exc
    if count == 0:
        raise PdfInputError(
            "malformed_pdf",
            "The PDF contains no pages.",
            action="Upload a PDF containing the complete document.",
        )
    return count


def inspect_pdf(
    data: bytes,
    *,
    document_id: str,
    filename: str,
    role: DocumentRole,
    config: NativePdfConfig | None = None,
    created_at: datetime | None = None,
) -> DocumentRecord:
    """Validate intake and inventory every page without claiming content extraction."""
    settings = config or NativePdfConfig()
    _validate_bytes(data, settings)
    with _open_pdf(data) as pdf:
        page_count = _page_count(pdf, settings)
    return DocumentRecord(
        document_id=document_id,
        role=role,
        filename=filename,
        sha256=hashlib.sha256(data).hexdigest(),
        byte_count=len(data),
        page_count=page_count,
        pages=tuple(PageInventory(page=number) for number in range(1, page_count + 1)),
        created_at=created_at or datetime.now(UTC),
    )


def _number(obj: Mapping[str, object], name: str) -> float:
    value = obj[name]
    if not isinstance(value, (float, int)) or isinstance(value, bool) or not math.isfinite(value):
        raise ValueError("Invalid PDF object coordinate")
    return float(value)


def _box(obj: Mapping[str, object]) -> Box:
    return (_number(obj, "x0"), _number(obj, "top"), _number(obj, "x1"), _number(obj, "bottom"))


def _geometry(box: Box, page: Page) -> BoundingBox:
    x0, top, x1, bottom = box
    origin_x, origin_y = float(page.bbox[0]), float(page.bbox[1])
    return BoundingBox(x0=x0 - origin_x, y0=top - origin_y, x1=x1 - origin_x, y1=bottom - origin_y)


def _inside(obj: Mapping[str, object], box: Box) -> bool:
    if obj.get("object_type") != "char":
        return False
    x = (_number(obj, "x0") + _number(obj, "x1")) / 2
    y = (_number(obj, "top") + _number(obj, "bottom")) / 2
    return box[0] <= x < box[2] and box[1] <= y < box[3]


def _characters(text: str) -> Counter[str]:
    return Counter(character for character in text if not character.isspace())


def _line_blocks(page: Page, config: NativePdfConfig, excluded_cells: list[Box]) -> list[TextBlock]:
    filtered = page.filter(lambda obj: not any(_inside(obj, box) for box in excluded_cells))
    words = filtered.extract_words(
        x_tolerance=config.x_tolerance,
        y_tolerance=config.y_tolerance,
        keep_blank_chars=False,
        use_text_flow=False,
        expand_ligatures=False,
    )
    words.sort(key=lambda word: (_number(word, "top"), _number(word, "x0")))
    groups: list[list[Mapping[str, object]]] = []
    for word in words:
        if groups:
            previous = groups[-1][-1]
            same_line = (
                abs(_number(word, "top") - _number(groups[-1][0], "top")) <= config.y_tolerance
            )
            close = _number(word, "x0") - _number(previous, "x1") < config.column_gap
            if same_line and close:
                groups[-1].append(word)
                continue
        groups.append([word])
    result: list[TextBlock] = []
    for index, group in enumerate(groups):
        text_parts = [word["text"] for word in group]
        if not all(isinstance(part, str) for part in text_parts):
            raise ValueError("Invalid word text")
        text = " ".join(str(part) for part in text_parts).strip()
        if not text:
            continue
        bounds = (
            min(_number(word, "x0") for word in group),
            min(_number(word, "top") for word in group),
            max(_number(word, "x1") for word in group),
            max(_number(word, "bottom") for word in group),
        )
        result.append(
            TextBlock(
                block_id=f"p{page.page_number:04d}.b{index:05d}",
                text=text,
                reading_order=index,
                bbox=_geometry(bounds, page),
            )
        )
    return result


def _extract_blocks(page: Page, config: NativePdfConfig) -> tuple[TextBlock, ...]:
    blocks: list[TextBlock] = []
    cell_boxes: list[Box] = []
    cell_count = 0
    candidates = sorted(
        page.find_tables(),
        key=lambda table: (table.bbox[2] - table.bbox[0]) * (table.bbox[3] - table.bbox[1]),
        reverse=True,
    )
    tables: list[Table] = []
    for candidate in candidates:
        # Intersecting line grids can produce nested detections of the same cells.
        # Keep one containing representation; native-character accounting still
        # rejects omissions or duplication after table and prose extraction.
        left, top, right, bottom = candidate.bbox
        overlaps = any(
            min(right, other.bbox[2]) - max(left, other.bbox[0]) > 0.1
            and min(bottom, other.bbox[3]) - max(top, other.bbox[1]) > 0.1
            for other in tables
        )
        if not overlaps:
            tables.append(candidate)
    tables.sort(key=lambda table: (table.bbox[1], table.bbox[0]))
    for table_index, table in enumerate(tables):
        values = table.extract(
            x_tolerance=config.x_tolerance,
            y_tolerance=config.y_tolerance,
            expand_ligatures=False,
        )
        table_id = f"p{page.page_number:04d}.t{table_index:03d}"
        for row_index, row in enumerate(table.rows):
            for column_index, cell in enumerate(row.cells):
                cell_count += 1
                if cell_count > config.max_table_cells_per_page:
                    raise _PageLimitExceeded("table_cell_limit")
                value = values[row_index][column_index]
                if cell is None or value is None or not value.strip():
                    continue
                box: Box = (float(cell[0]), float(cell[1]), float(cell[2]), float(cell[3]))
                cell_boxes.append(box)
                blocks.append(
                    TextBlock(
                        block_id=f"{table_id}.r{row_index:04d}.c{column_index:04d}",
                        text=value,
                        reading_order=len(blocks),
                        bbox=_geometry(box, page),
                        table_id=table_id,
                        row=row_index,
                        column=column_index,
                    )
                )
    blocks.extend(_line_blocks(page, config, cell_boxes))
    blocks.sort(key=lambda block: (block.bbox.y0, block.bbox.x0) if block.bbox else (0, 0))
    return tuple(
        block.model_copy(update={"reading_order": index}) for index, block in enumerate(blocks)
    )


def _failed_page(
    number: int, issue: str, *, needs_ocr: bool = False, extraction_score: float | None = None
) -> ExtractedPage:
    return ExtractedPage(
        page=number,
        quality=PageQuality.NEEDS_OCR if needs_ocr else PageQuality.UNUSABLE,
        issues=(issue,),
        extraction_score=extraction_score,
    )


def _pdf_name(value: object) -> str | None:
    return literal_name(value) if isinstance(value, PSLiteral) else None


def _noncontent_navigation_link(annotation: Mapping[str, object]) -> bool:
    """Allow only inert navigation metadata, never an annotation's visible content."""
    raw = annotation.get("data")
    if not isinstance(raw, dict):
        return False
    data = cast(Mapping[str, object], raw)
    allowed_fields = {
        "Type",
        "Subtype",
        "Rect",
        "Border",
        "BS",
        "A",
        "Dest",
        "H",
        "C",
        "F",
        "P",
        "StructParent",
        "NM",
        "M",
        "Contents",
        "T",
        "Subj",
        "RC",
    }
    if _pdf_name(data.get("Subtype")) != "Link" or set(data) - allowed_fields:
        return False
    if any(data.get(key) not in (None, b"", "") for key in ("Contents", "T", "Subj", "RC")):
        return False
    # A missing border defaults to a visible one; require explicit zero width.
    border = data.get("Border")
    style = data.get("BS")
    if border is None and style is None:
        return False
    if border is not None and (
        not isinstance(border, (list, tuple)) or len(border) < 3 or border[2] != 0
    ):
        return False
    if style is not None and (not isinstance(style, dict) or style.get("W") != 0):
        return False
    action = data.get("A")
    if action is None:
        return data.get("Dest") is not None
    if not isinstance(action, dict):
        return False
    if _pdf_name(action.get("S")) == "URI":
        return set(action) <= {"Type", "S", "URI"} and isinstance(action.get("URI"), bytes)
    if _pdf_name(action.get("S")) == "GoTo":
        return set(action) <= {"Type", "S", "D"} and action.get("D") is not None
    return False


def _ocr_page(page: Page, config: NativePdfConfig) -> str:
    """Run the configured OCR command on a rendered page image."""
    if not shutil.which(config.ocr_command):
        return ""
    temporary_directory = tempfile.mkdtemp(prefix="aira-ocr-")
    image_path = os.path.join(temporary_directory, "page.png")
    try:
        rendered = page.to_image(resolution=200)
        rendered.original.convert("RGB").save(image_path, format="PNG")
        completed = subprocess.run(
            [config.ocr_command, image_path, "stdout", "-l", config.ocr_languages, "--psm", "6"],
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            return ""
        return completed.stdout.decode("utf-8", errors="replace")
    except (OSError, ValueError, RuntimeError):
        return ""
    finally:
        for name in os.listdir(temporary_directory):
            try:
                os.unlink(os.path.join(temporary_directory, name))
            except OSError:
                pass
        try:
            os.rmdir(temporary_directory)
        except OSError:
            pass


def _ocr_blocks(page: Page, text: str) -> tuple[TextBlock, ...]:
    blocks: list[TextBlock] = []
    for index, line in enumerate(line for line in text.splitlines() if line.strip()):
        blocks.append(
            TextBlock(
                block_id=f"p{page.page_number:04d}.o{index:05d}",
                text=" ".join(line.split()),
                reading_order=index,
                bbox=None,
            )
        )
    return tuple(blocks)


def _extract_page(
    page: Page, config: NativePdfConfig, remaining_characters: int
) -> tuple[ExtractedPage, int]:
    annotations = page.annots
    if any(not _noncontent_navigation_link(annotation) for annotation in annotations):
        return _failed_page(
            page.page_number,
            "unsupported_annotations: page annotations may alter visible source meaning; "
            "export a flattened native-text PDF that preserves all amendments.",
            extraction_score=0.0,
        ), 0
    navigation_issues = (
        (
            (
                f"navigation_links_retained: {len(annotations)} noncontent links remain in the "
                "original PDF; targets are not followed."
            ),
        )
        if annotations
        else ()
    )
    characters = page.chars
    count = sum(len(str(character.get("text", ""))) for character in characters)
    if count > config.max_characters_per_page or count > remaining_characters:
        return _failed_page(
            page.page_number,
            "character_limit: native text exceeds the configured parser budget.",
            extraction_score=0.0,
        ), count
    if page.rotation != 0:
        return _failed_page(
            page.page_number,
            "rotated_page: export an upright native-text PDF.",
            extraction_score=0.0,
        ), count
    if not characters:
        if config.ocr_enabled and page.images:
            ocr_text = _ocr_page(page, config)
            if ocr_text.strip():
                blocks = _ocr_blocks(page, ocr_text)
                return ExtractedPage(
                    page=page.page_number,
                    quality=PageQuality.USABLE,
                    method=ExtractionMethod.OCR,
                    blocks=blocks,
                    issues=navigation_issues,
                    extraction_score=1.0,
                ), len(ocr_text)
        if page.images:
            issue = (
                "unsupported_image_content: raster content requires unsupported OCR "
                "or visual interpretation."
            )
            return _failed_page(
                page.page_number, issue, needs_ocr=True, extraction_score=0.0
            ), count
        if page.lines or page.rects or page.curves:
            return _failed_page(
                page.page_number,
                "unusable_vector_content: visible content has no native text.",
                extraction_score=0.0,
            ), count
        return ExtractedPage(
            page=page.page_number,
            quality=PageQuality.BLANK,
            issues=navigation_issues,
            extraction_score=1.0,
        ), count

    if page.images:
        issue = (
            "unsupported_image_content: raster content requires unsupported OCR "
            "or visual interpretation."
        )
        return _failed_page(
            page.page_number, issue, needs_ocr=not characters, extraction_score=0.0
        ), count
    blocks = _extract_blocks(page, config)
    original_text = "".join(str(character.get("text", "")) for character in characters)
    extracted_text = "".join(block.text for block in blocks)
    source_characters = len(_characters(original_text))
    extracted_characters = len(_characters(extracted_text))
    score = 1.0 if source_characters == 0 else min(1.0, extracted_characters / source_characters)
    issues: list[str] = []
    if not blocks:
        issues.append("unusable_text: native glyphs did not produce readable blocks.")
    if UNMAPPED_GLYPH.search(extracted_text):
        issues.append("unmapped_glyph: the text layer contains unresolved glyph mappings.")
    if _characters(original_text) != _characters(extracted_text):
        issues.append(
            "text_coverage_mismatch: layout extraction omitted or duplicated native characters."
        )
    return ExtractedPage(
        page=page.page_number,
        quality=PageQuality.UNUSABLE if issues else PageQuality.USABLE,
        method=ExtractionMethod.NATIVE_TEXT,
        blocks=blocks,
        issues=tuple(issues) + navigation_issues,
        extraction_score=score,
    ), count


def extract_pdf(
    data: bytes,
    document: DocumentRecord,
    *,
    config: NativePdfConfig | None = None,
    created_at: datetime | None = None,
) -> ExtractionRecord:
    """Create a new immutable revision; retain unsuccessful pages as explicit records."""
    settings = config or NativePdfConfig()
    _validate_bytes(data, settings)
    if hashlib.sha256(data).hexdigest() != document.sha256 or len(data) != document.byte_count:
        raise PdfInputError(
            "identity_mismatch",
            "The supplied bytes do not match the original document.",
            action="Load the original document bytes for this document identity.",
            document_id=document.document_id,
        )
    pages: list[ExtractedPage] = []
    remaining = settings.max_total_characters
    with _open_pdf(data) as pdf:
        if _page_count(pdf, settings) != document.page_count:
            raise PdfInputError(
                "identity_mismatch",
                "The page inventory differs from the original document record.",
                action="Reinspect the original PDF before extraction.",
                document_id=document.document_id,
            )
        for number, page_object in enumerate(PDFPage.create_pages(pdf.doc), start=1):
            page: Page | None = None
            try:
                page = Page(pdf, page_object, page_number=number)
                if remaining <= 0:
                    result = _failed_page(
                        number,
                        "character_limit: parser budget exhausted; page was not extracted.",
                        extraction_score=0.0,
                    )
                else:
                    result, count = _extract_page(page, settings, remaining)
                    remaining -= count
                pages.append(result)
            except _PageLimitExceeded:
                pages.append(
                    _failed_page(
                        number,
                        "table_cell_limit: page exceeds table-cell budget.",
                        extraction_score=0.0,
                    )
                )
            except Exception:
                # Retain the failed page and continue inventory, never a partial-success document.
                pages.append(
                    _failed_page(
                        number,
                        "page_extraction_failed: native layout could not be read; "
                        "export a new native-text PDF.",
                        extraction_score=0.0,
                    )
                )
            finally:
                if page is not None:
                    page.close()
    return ExtractionRecord(
        extraction_id=f"ext-{uuid4().hex}",
        document_id=document.document_id,
        document_sha256=document.sha256,
        parser_name="pdfplumber",
        parser_version=PARSER_VERSION,
        configuration_sha256=settings.sha256,
        created_at=created_at or datetime.now(UTC),
        pages=tuple(pages),
    )


def require_usable_extraction(document: DocumentRecord, extraction: ExtractionRecord) -> None:
    """Gate interpretation; page inventory and diagnostic blocks are not a success flag."""
    if (
        extraction.document_id != document.document_id
        or extraction.document_sha256 != document.sha256
        or len(extraction.pages) != document.page_count
    ):
        raise PdfInputError(
            "identity_mismatch",
            "The extraction does not belong to the complete original document.",
            action="Load the extraction revision for this document.",
            document_id=document.document_id,
        )
    failed = [
        page
        for page in extraction.pages
        if page.quality not in {PageQuality.USABLE, PageQuality.BLANK}
    ]
    if failed or not any(page.quality == PageQuality.USABLE for page in extraction.pages):
        page = failed[0].page if failed else None
        raise PdfInputError(
            "unusable_extraction",
            "The complete document is not usable for native-text assessment.",
            action=(
                "Inspect page issues and upload a complete native-text PDF; scans are unsupported."
            ),
            document_id=document.document_id,
            page=page,
        )


def source_span(
    extraction: ExtractionRecord,
    *,
    page: int,
    block_id: str,
    start: int = 0,
    end: int | None = None,
) -> SourceSpan:
    """Construct an exact half-open block span; never fuzzy-match or cross page boundaries.

    Geometry describes the containing block, including for a substring. A passage
    spanning blocks/pages must be represented by multiple SourceSpan records.
    """
    if page < 1 or page > len(extraction.pages):
        raise ValueError("Source page does not exist in this extraction")
    extracted_page = extraction.pages[page - 1]
    if extracted_page.quality != PageQuality.USABLE:
        raise ValueError("An unusable or blank page cannot supply assessment evidence")
    block = next((item for item in extracted_page.blocks if item.block_id == block_id), None)
    if block is None:
        raise ValueError("Source block does not exist on the specified page")
    stop = len(block.text) if end is None else end
    if start < 0 or stop > len(block.text) or stop <= start:
        raise ValueError("Source offsets are outside the exact block text")
    return SourceSpan(
        document_id=extraction.document_id,
        document_sha256=extraction.document_sha256,
        extraction_id=extraction.extraction_id,
        page=page,
        block_id=block_id,
        start=start,
        end=stop,
        excerpt=block.text[start:stop],
        bbox=block.bbox,
    )
