"""Bounded helpers for splitting oversized policy inputs.

The production workflow still validates complete inputs. These helpers make a
future page-range orchestrator explicit without changing the current safety
boundary.
"""

from __future__ import annotations

from app.schemas import ExtractionRecord


def page_ranges_for_character_budget(
    extraction: ExtractionRecord, max_characters: int
) -> list[tuple[int, int]]:
    """Return inclusive one-based page ranges whose rendered text fits a budget."""
    if max_characters < 1:
        raise ValueError("max_characters must be positive")
    ranges: list[tuple[int, int]] = []
    start = 1
    current = 0
    for page in extraction.pages:
        page_characters = sum(len(block.text) for block in page.blocks)
        if current and current + page_characters > max_characters:
            ranges.append((start, page.page - 1))
            start = page.page
            current = page_characters
        else:
            current += page_characters
    if start <= len(extraction.pages):
        ranges.append((start, len(extraction.pages)))
    return ranges or [(1, len(extraction.pages))]
