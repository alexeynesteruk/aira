# Native PDF extraction verification

Verified on October 18, 2026 with Python 3.13, `pdfplumber 0.11.10`, and `pdfminer.six 20260107`. The application adapter reports parser version `0.11.10+aira.0.1.1`, including the annotation guard added after independent review. The locked runtime uses the packaged library; it does not invoke the author's local `pdf-tools` installation.

The [adapter](../../backend/app/documents/native.py) and [integration tests](../../tests/integration/test_documents.py) establish a native-text parsing baseline. All 35 pages of the supplied chart and the two guideline snapshots pass the complete-input gate. This verifies the checks below on these documents; it does not establish general clinical interpretation, arbitrary PDF layout support, or a model token envelope. Implementation status remains in the [work breakdown](../work-breakdown.md#wp-04-native-pdf-extraction).

## Adapter boundary and provenance

`inspect_pdf(bytes, document_id=..., filename=..., role=..., config=...)` validates the original-byte signature, supported end marker, readability, encryption, page tree, and upload/page limits. It returns a `DocumentRecord` with the original byte count and SHA-256, caller-supplied identity/role, and every original page numbered from one. Its page qualities remain `uninspected`; successful intake is not successful content extraction.

`extract_pdf(bytes, document, config=...)` first verifies the original hash and page count, then creates a new extraction ID. It records every usable, blank, OCR-needed, or failed page. Per-page layout failures remain explicit records while later pages are still accounted for. The configuration fingerprint includes every parser setting, adapter version, pdfplumber/pdfminer versions, table strategy, overlap handling, annotation boundary, and text-normalization choices. Re-extraction produces a distinct revision; the adapter does not overwrite an earlier record.

Before interpretation, callers must invoke `require_usable_extraction(document, extraction)`. It checks document identity and completeness and rejects any failed/uninspected/OCR-needed page. Blank pages may accompany usable pages; an entirely blank document cannot pass. Original bytes and immutable extraction records still need to be persisted by WP-06/WP-11.

Blocks retain native text, original-page geometry in PDF points with a top-left origin, reading-order positions, and detected table/row/column relationships. Ruled-table detections are resolved to nonoverlapping regions to avoid duplicate nested detections. Text outside their cells is grouped into geometric line fragments, split at substantial horizontal gaps. Every non-whitespace native character must remain accounted for without duplication; a mismatch makes the page unusable.

`source_span(extraction, page=..., block_id=..., start=..., end=...)` constructs an exact half-open substring with document hash, extraction revision, original page, and block ID. It rejects unknown pages/blocks, failed pages, and invalid offsets. Its box describes the containing block, not exact glyph-level selection. A cross-page passage uses multiple source spans; the parser does not invent a combined page or resolve conflicting dates.

## Provisional limits and exclusions

These are configurable `NativePdfConfig` guardrails, not measured release or model-capacity limits.

| Setting | Current default |
| --- | --- |
| Original upload bytes | 10 MiB: 10,485,760 bytes |
| Original pages | 100 |
| Native characters on one page | 50,000 |
| Native characters in the document | 500,000 |
| Detected table-cell positions on one page | 10,000 |
| Word x/y tolerances | 3 PDF points each |
| Horizontal gap splitting non-table fragments | 30 PDF points |

Byte and page limits reject intake with a suggested `413` response. Unsupported signatures suggest `415`; malformed/encrypted/unreadable inputs suggest `422`. Extraction budget failures identify affected pages and block assessment. No path silently truncates input and then treats it as complete. Character limits apply after a page's native objects are decoded; they are not hard decompression, memory, or wall-clock limits.

The initial support boundary excludes **all raster-image content**, including a decorative logo, a scan with an OCR text layer, and an image embedded beside usable native text. A page containing raster content requires OCR or visual interpretation that this adapter does not provide. Image-only pages are `needs_ocr`; mixed text/image pages are `unusable`. This deliberately conservative rule can reject otherwise useful documents; an image is not assumed decorative.

Other implemented guards reject encrypted PDFs even if an empty password opens them, interactive forms, nonzero page rotation, unresolved glyph markers, and visible vector-only content with no native text. Fully empty pages remain blank. The bounded signature check requires `%PDF-` at the beginning and `%%EOF` within the last 1,024 bytes; PDFs outside that boundary require re-export. The current real fixtures cover password protection, scans, mixed images, vector-only content, blanks, and malformed inputs. Dedicated real fixtures for empty-password encryption, interactive forms, rotated pages, and unresolved glyph mappings remain future checks.

Page annotations are checked **before** usable/blank classification. Comments, free text, highlights, strikeouts, redactions, and other unrecognized annotations make the page unusable: native characters do not include their potentially meaning-changing content. The only exception is a `/Link` carrying plain URI or GoTo navigation metadata, with an explicitly zero-width border, no appearance stream, no annotation contents/title/subject/rich text, no additional actions, and only recognized metadata fields. Any missing/default visible border, appearance, text, or unsupported action rejects the page. Accepted links produce a `navigation_links_retained` page diagnostic; their exact metadata remains in the original PDF, and targets are never followed or used as evidence. The supplied guidelines each have 18 accepted links across pages 1, 3, 7, and 8. A user must re-export an unsupported annotated document while preserving its amendments; deleting annotations merely to pass extraction would lose source meaning.

Ruled tables and separate line fragments were checked on the supplied layouts and the controlled fixture. Unruled table semantics, arbitrary multi-column reading order, nested/merged-table meaning, misleading native text layers without raster content, and general graphical meaning have not been established. Geometry and character accounting preserve inspectability; they cannot prove semantic reading order or correct clinical interpretation. Section continuation and date-role interpretation remain downstream work.

## Observed checks

The original source hashes remain in the [source registry](../../evals/source-registry.json); the parser tests use the actual files. Parser fixtures have a separate [hash/creation manifest](../../tests/fixtures/pdf/manifest.json).

| Input/check | Observed result |
| --- | --- |
| Supplied chart, 154,436 bytes, seven pages | Every page usable. The TSH row retains `2.4 mIU/L`, `0.4-4.0`, and `Normal` in the correct columns. Payer/plan and procedure-code table cells retain their original pages. |
| Chart chronology and negation | Page 5 retains the November 1–29 window, 29 days/14 hours, November 12 pause, sleep context, and zero symptom events. Page 6 retains the November 11 signature, absent AV block, and absent symptom-rhythm correlation. Page 7 retains the November 14 submission. No dates are repaired or inferred. |
| BCBS August 2025 snapshot, 675,577 bytes, 14 pages | Every page usable; original effective-date text and revision text remain distinct. |
| BCBS January 2026 snapshot, 677,728 bytes, 14 pages | Every page usable and original hash differs. The tested clinical pages 2–4 extract identically; page 5 differs. These snapshots do not substitute for the fictional changed-rule evaluation. |
| Controlled native fixture | Separate columns do not merge their labels. `Marker A / 7.2 mg / right side` remains one table row, distinct from the `72.0 mg` trap. A continued report retains pages 1 and 2. |
| Image-only, mixed-page, and mixed-document fixtures | Explicit rejection; the three-page mixed document retains native page 1, OCR-needed page 2, and blank page 3. Partial usable input cannot pass the gate. |
| Blank and vector-only fixtures | Empty pages are inventoried as blank; vector content is unusable rather than falsely blank. A native-plus-blank document passes; an all-blank document fails. |
| Annotation and navigation fixtures | A real sticky-note-only PDF is unusable rather than blank; a real strikeout over a native measurement makes that page unusable while its following page stays inventoried. A real plain navigation-link PDF retains its native label and measurement and passes with a nonblocking link diagnostic. |
| Encrypted and malformed input | Password protection is classified as encrypted, not a clinical gap. Invalid byte strings and incomplete PDFs fail intake. The encrypted fixture intentionally causes `pdf-inspect` to report that a password is required. |
| Injected failures | A page extraction exception preserves that page and later pages. Removing an extracted line triggers the native-character coverage check even though other blocks exist. Controlled Link metadata with an appearance stream, contents/title/rich text, visible/default border, script action, or additional action is rejected. These are adapter fault controls, not additional real malformed-PDF examples. |
| Limits, revisions, and spans | Inclusive byte/page boundaries, character/cell exhaustion, source-hash mismatch, configuration changes, distinct extraction IDs, exact offsets, and wrong-page block references are checked. |

Source review used `pdf-inspect`, `pdf-extract`, and `pdf-render`. Chart pages 1, 3, 5, 6, and 7 and August-policy pages 1, 2, and 5 were visually checked at 110 dpi. Native fixture pages and the image/mixed/vector/annotation/navigation fixtures were rendered and reviewed. Fictional PDFs were authored through `pdf-create`; protected, annotated, and combined variants used `pdf-crypto`, `pdf-annotate`, and dry-run-verified `pdf-merge`. No clinical expected answers were generated by this parser.

An initial policy-page failure exposed duplicate overlapping table detections. The character-accounting gate caught the duplication. Selecting nonoverlapping table regions fixed both snapshots without deleting source text or weakening the gate.

Independent review also identified that the original implementation ignored annotations. Real `pdf-annotate` fixtures reproduced both failure modes: a sticky note was classified blank, and a native page with a visible strikeout passed the complete-input gate. Revision `aira.0.1.1` closes those paths and fingerprints the changed boundary. The narrow noncontent-link exception retains all 35 originally tested pages without exempting annotations that could change the document's meaning.

## Repeatable verification

From `backend/`:

```sh
uv run --python 3.13 pytest ../tests/integration/test_documents.py -q
uv run --python 3.13 ruff check app/documents ../tests/integration/test_documents.py
uv run --python 3.13 mypy --strict app/documents ../tests/integration/test_documents.py
```

Observed result after the annotation regression: **34 tests passed**, Ruff passed, and strict mypy passed for the two application modules and test module. Repository-wide checks and UI verification are separate integration responsibilities. WP-15 still owns final support/limit verification; the OpenAI model envelope remains unverified while live inference is deferred for quota resolution.
