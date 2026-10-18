"""Native PDF intake, immutable extraction, and exact source-span construction."""

from .native import (
    NativePdfConfig,
    PdfInputError,
    extract_pdf,
    inspect_pdf,
    require_usable_extraction,
    source_span,
)

__all__ = [
    "NativePdfConfig",
    "PdfInputError",
    "extract_pdf",
    "inspect_pdf",
    "require_usable_extraction",
    "source_span",
]
