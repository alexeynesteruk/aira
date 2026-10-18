#!/usr/bin/env python3
"""Render the development Markdown scenario fixtures to native-text PDFs.

Each ``<!-- page:N -->`` logical page becomes PDF page N exactly; every source
line renders on one PDF line (``white-space: pre``, small landscape monospace).
Markdown header decorations (``# `` title, ``> `` disclaimer) are stripped so
the extracted text matches the reviewed expected excerpts. The held-out
reserved pair is deliberately not rendered.

Run: ``python3 scripts/render_scenarios.py`` (requires the pdf-tools
``pdf-create`` CLI; WeasyPrint produces the PDF). Output lands in
``examples/synthetic/`` with a hash-pinned ``manifest.json`` consumed by
``tests/integration/test_scenario_pdfs.py``.
"""

import html
import json
import re
import subprocess
import sys
import tempfile
from hashlib import sha256
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REGISTRY = REPO / "evals" / "source-registry.json"
OUT_DIR = REPO / "examples" / "synthetic"

CSS = """
@page { size: Letter landscape; margin: 10mm; }
body { font-family: monospace; font-size: 7pt; margin: 0; }
.page { white-space: pre; page-break-after: always; }
"""

TOOL = {
    "command": "pdf-create html <page>.html --out <source_id>.pdf",
    "tool": "pdf-tools pdf-create",
    "version": "0.4.0",
    "producer": "WeasyPrint 70.0",
}


def logical_pages(source: Path) -> tuple[list[str], list[str]]:
    """Split a fixture into header lines and per-logical-page lines."""
    lines = source.read_text(encoding="utf-8").splitlines()
    header: list[str] = []
    pages: list[list[str]] = []
    seen_marker = False
    for line in lines:
        marker = re.match(r"<!--\s*page:(\d+)\s*-->\s*$", line)
        if marker:
            seen_marker = True
            index = int(marker.group(1))
            while len(pages) < index:
                pages.append([])
            continue
        if not seen_marker:
            if line.startswith("# "):
                header.append(line[2:])
            elif line.startswith("> "):
                header.append(line[2:])
            elif line.strip():
                header.append(line)
            continue
        pages[-1].append(line)
    while pages and not any(pages[-1]):
        pages.pop()
    return header, pages


def render_html(header: list[str], pages: list[list[str]]) -> str:
    body = []
    first = [line for line in (*header, *pages[0])]
    body.append(f'<div class="page">{html.escape(chr(10).join(first))}</div>')
    for page in pages[1:]:
        body.append(f'<div class="page">{html.escape(chr(10).join(page))}</div>')
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        f"<style>{CSS}</style></head><body>{''.join(body)}</body></html>"
    )


def main() -> int:
    registry = json.loads(REGISTRY.read_text())
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    entries = {}
    for source_id, meta in sorted(registry["sources"].items()):
        if meta.get("format") != "markdown" or meta.get("split") != "development":
            continue
        source = REPO / meta["path"]
        header, pages = logical_pages(source)
        if len(pages) != len(meta["logical_pages"]):
            raise SystemExit(
                f"{source_id}: registry lists {len(meta['logical_pages'])} logical "
                f"pages but the Markdown yields {len(pages)}"
            )
        out_pdf = OUT_DIR / f"{source_id}.pdf"
        with tempfile.TemporaryDirectory() as temporary:
            page_html = Path(temporary) / f"{source_id}.html"
            page_html.write_text(render_html(header, pages), encoding="utf-8")
            subprocess.run(
                ["pdf-create", "html", str(page_html), "--out", str(out_pdf)],
                check=True,
                capture_output=True,
                text=True,
            )
        inspect = subprocess.run(
            ["pdf-inspect", str(out_pdf)], check=True, capture_output=True, text=True
        )
        match = re.search(r"^pages: (\d+)$", inspect.stdout, re.MULTILINE)
        pdf_pages = int(match.group(1))
        if pdf_pages != len(meta["logical_pages"]):
            raise SystemExit(
                f"{source_id}: rendered {pdf_pages} pages for "
                f"{len(meta['logical_pages'])} logical pages"
            )
        entries[source_id] = {
            "source_id": source_id,
            "derived_from": {"path": meta["path"], "sha256": meta["sha256"]},
            "pdf_sha256": sha256(out_pdf.read_bytes()).hexdigest(),
            "logical_pages": len(meta["logical_pages"]),
            "pdf_pages": pdf_pages,
            "rendering": TOOL,
        }
        print(f"{source_id}: {len(pages)} logical pages -> {pdf_pages} PDF pages")
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "0.1.0",
                "generated_by": "scripts/render_scenarios.py",
                "rendering": TOOL,
                "sources": entries,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"manifest: {len(entries)} sources")
    return 0


if __name__ == "__main__":
    sys.exit(main())
