"""Original document identity and versioned extraction contracts."""

from enum import StrEnum
from typing import Self

from pydantic import AwareDatetime, Field, model_validator

from .base import (
    FiniteNumber,
    Identifier,
    NonEmptyText,
    NonNegativeInt,
    PositiveInt,
    Sha256,
    StrictModel,
    VersionedModel,
)


class DocumentRole(StrEnum):
    POLICY = "policy"
    CHART = "chart"


class PageQuality(StrEnum):
    UNINSPECTED = "uninspected"
    USABLE = "usable"
    BLANK = "blank"
    NEEDS_OCR = "needs_ocr"
    UNUSABLE = "unusable"


class ExtractionMethod(StrEnum):
    NATIVE_TEXT = "native_text"
    OCR = "ocr"


class BoundingBox(StrictModel):
    """PDF-point coordinates with a top-left origin in the original page."""

    x0: FiniteNumber = Field(ge=0)
    y0: FiniteNumber = Field(ge=0)
    x1: FiniteNumber = Field(ge=0)
    y1: FiniteNumber = Field(ge=0)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.x1 < self.x0 or self.y1 < self.y0:
            raise ValueError("bounding box edges must be ordered")
        return self


class PageInventory(StrictModel):
    page: PositiveInt
    quality: PageQuality = PageQuality.UNINSPECTED
    issues: tuple[NonEmptyText, ...] = ()


class DocumentRecord(VersionedModel):
    document_id: Identifier
    role: DocumentRole
    filename: NonEmptyText
    sha256: Sha256
    byte_count: PositiveInt
    page_count: PositiveInt
    pages: tuple[PageInventory, ...]
    created_at: AwareDatetime

    @model_validator(mode="after")
    def complete_inventory(self) -> Self:
        if tuple(page.page for page in self.pages) != tuple(range(1, self.page_count + 1)):
            raise ValueError("page inventory must contain every page once in original order")
        return self


class TextBlock(StrictModel):
    block_id: Identifier
    text: NonEmptyText
    reading_order: NonNegativeInt
    bbox: BoundingBox | None = None
    table_id: Identifier | None = None
    row: NonNegativeInt | None = None
    column: NonNegativeInt | None = None

    @model_validator(mode="after")
    def table_coordinates(self) -> Self:
        if (self.row is None) != (self.column is None):
            raise ValueError("table row and column must be supplied together")
        if self.row is not None and self.table_id is None:
            raise ValueError("table coordinates require a table identifier")
        return self


class ExtractedPage(StrictModel):
    page: PositiveInt
    quality: PageQuality
    method: ExtractionMethod | None = None
    blocks: tuple[TextBlock, ...] = ()
    issues: tuple[NonEmptyText, ...] = ()
    extraction_score: FiniteNumber | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def consistent_page(self) -> Self:
        block_ids = [block.block_id for block in self.blocks]
        orders = [block.reading_order for block in self.blocks]
        if len(block_ids) != len(set(block_ids)) or len(orders) != len(set(orders)):
            raise ValueError("block identifiers and reading-order positions must be unique")
        if self.quality == PageQuality.USABLE and (not self.blocks or self.method is None):
            raise ValueError("usable pages require extracted blocks and their extraction method")
        if self.quality == PageQuality.BLANK and self.blocks:
            raise ValueError("blank pages cannot contain extracted blocks")
        return self


class ExtractionRecord(VersionedModel):
    extraction_id: Identifier
    document_id: Identifier
    document_sha256: Sha256
    parser_name: NonEmptyText
    parser_version: NonEmptyText
    configuration_sha256: Sha256
    created_at: AwareDatetime
    pages: tuple[ExtractedPage, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def ordered_pages(self) -> Self:
        if tuple(page.page for page in self.pages) != tuple(range(1, len(self.pages) + 1)):
            raise ValueError("extraction pages must retain contiguous original numbering")
        return self


class SourceSpan(StrictModel):
    document_id: Identifier
    document_sha256: Sha256
    extraction_id: Identifier
    page: PositiveInt
    block_id: Identifier
    start: NonNegativeInt
    end: PositiveInt
    excerpt: NonEmptyText
    bbox: BoundingBox | None = None

    @model_validator(mode="after")
    def ordered_offsets(self) -> Self:
        if self.end <= self.start:
            raise ValueError("source offsets must describe a nonempty half-open span")
        return self
