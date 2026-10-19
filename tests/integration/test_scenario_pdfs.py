"""Integrity of the rendered development scenario PDFs.

examples/synthetic/*.pdf are generated from the authored Markdown fixtures by
scripts/render_scenarios.py (pdf-tools pdf-create / WeasyPrint). This file
pins the manifest against the source registry, proves every PDF passes the
real intake gates, and proves every expected excerpt resolves through the real
CitationResolver — so reviewed expectations bind to PDF layout, not Markdown.

Resolution update: wrapped-line block merging in app.documents.native merges
consecutive lines of paragraphs into single blocks, so all six previously
unresolvable multi-line section sources in evals/expected/policies.json now
resolve cleanly into exact single-block source spans. UNRESOLVABLE is now empty
to assert that 100% of rendered selectors resolve exactly once.
"""

import json
import re
from hashlib import sha256
from pathlib import Path

import pytest

from app.documents import extract_pdf, inspect_pdf, require_usable_extraction
from app.evidence import CitationResolver
from app.schemas import CandidateCitation, DocumentRole

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "evals" / "source-registry.json"
MANIFEST_PATH = ROOT / "examples" / "synthetic" / "manifest.json"
EXPECTED_PATHS = (
    ROOT / "evals" / "expected" / "development.json",
    ROOT / "evals" / "expected" / "policies.json",
)

UNRESOLVABLE: set[tuple[str, int, str]] = set()

REGISTRY = json.loads(REGISTRY_PATH.read_text())["sources"]
MANIFEST = json.loads(MANIFEST_PATH.read_text())["sources"]


def _selectors(node: object, out: list[dict]) -> list[dict]:
    if isinstance(node, dict):
        if "excerpt" in node and "page" in node and "source_id" in node:
            out.append(node)
        for value in node.values():
            _selectors(value, out)
    elif isinstance(node, list):
        for item in node:
            _selectors(item, out)
    return out


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _logical_pages(path: Path) -> list[list[str]]:
    pages: list[list[str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        marker = re.match(r"<!--\s*page:(\d+)\s*-->\s*$", line)
        if marker:
            while len(pages) < int(marker.group(1)):
                pages.append([])
            continue
        if not pages:
            continue
        pages[-1].append(line)
    return pages


@pytest.fixture(scope="module")
def extractions() -> dict[str, object]:
    return {source_id: _extract(source_id) for source_id in MANIFEST}


def _extract(source_id: str):
    pdf = ROOT / "examples" / "synthetic" / f"{source_id}.pdf"
    raw = pdf.read_bytes()
    document = inspect_pdf(
        raw,
        document_id=source_id,
        filename=pdf.name,
        role=DocumentRole.CHART if "chart" in source_id else DocumentRole.POLICY,
    )
    return document, extract_pdf(raw, document)


def test_manifest_matches_the_registry_and_pdf_bytes():
    expected = {
        source_id
        for source_id, meta in REGISTRY.items()
        if meta.get("format") == "markdown" and meta.get("split") == "development"
    }
    assert set(MANIFEST) == expected == set(_sources_by_pdf())
    reserved = {
        source_id for source_id, meta in REGISTRY.items() if meta.get("split") == "reserved"
    }
    assert not (reserved & set(MANIFEST))
    for source_id, entry in MANIFEST.items():
        assert REGISTRY[source_id]["sha256"] == entry["derived_from"]["sha256"]
        assert REGISTRY[source_id]["path"] == entry["derived_from"]["path"]
        pdf = ROOT / "examples" / "synthetic" / f"{source_id}.pdf"
        assert sha256(pdf.read_bytes()).hexdigest() == entry["pdf_sha256"]
        assert entry["pdf_pages"] == len(REGISTRY[source_id]["logical_pages"])


def _sources_by_pdf() -> list[str]:
    return sorted(path.stem for path in (ROOT / "examples" / "synthetic").glob("*.pdf"))


def test_every_rendered_pdf_passes_the_real_intake_gates(extractions):
    for source_id, (document, extraction) in extractions.items():
        require_usable_extraction(document, extraction)
        assert len(extraction.pages) == MANIFEST[source_id]["pdf_pages"]


def test_every_logical_line_lands_on_the_mapped_pdf_page(extractions):
    for source_id, (_document, extraction) in extractions.items():
        entry = MANIFEST[source_id]
        logical = _logical_pages(ROOT / entry["derived_from"]["path"])
        for index, lines in enumerate(logical, start=1):
            page = extraction.pages[index - 1]
            text = _normalized("".join(block.text for block in page.blocks))
            for line in lines:
                if line.strip():
                    assert _normalized(line) in text, f"{source_id} page {index}: {line[:60]!r}"


def test_every_rendered_source_selector_resolves_exactly_once(extractions):
    selectors: list[dict] = []
    for path in EXPECTED_PATHS:
        _selectors(json.loads(path.read_text()), selectors)
    rendered = [item for item in selectors if item["source_id"] in MANIFEST]
    assert rendered
    failures: list[str] = []
    unresolvable_seen: set[tuple[str, int, str]] = set()
    for item in rendered:
        try:
            document, extraction = extractions[item["source_id"]]
            span = CitationResolver((document,), (extraction,)).resolve(
                CandidateCitation(
                    document_id=item["source_id"],
                    page=item["page"],
                    quote=item["excerpt"],
                )
            )
            assert span.page == item["page"]
        except Exception as exc:  # noqa: BLE001 - collect and classify
            if "\n" not in item["excerpt"]:
                failures.append(
                    f"{item['source_id']}:{item['page']} {item['excerpt'][:60]!r}: {exc}"
                )
                continue
            # Multi-line excerpts span blocks; the contract resolves only
            # inside one block, so these must be the known UNRESOLVABLE set.
            key = next(
                (
                    entry
                    for entry in UNRESOLVABLE
                    if entry[0] == item["source_id"]
                    and entry[1] == item["page"]
                    and item["excerpt"].startswith(entry[2])
                ),
                None,
            )
            assert key is not None, f"unexpected unresolvable selector: {item}"
            unresolvable_seen.add(key)
    assert failures == []
    # Pinned both ways: a removed or newly resolvable selector is as
    # review-worthy as a new unresolvable one.
    assert unresolvable_seen == UNRESOLVABLE
