# WP-15 input support boundary and limit evidence

Verified October 18, 2026. [WP-15](../work-breakdown.md#wp-15-ocr-decision-and-supported-input-limits) owns the supported-input envelope. This record collects the parser and API evidence that already exists; the remaining piece (a measured model token envelope) is live-gated by the deferred quota.

## Declared native-text boundary

The extraction adapter processes only native-text PDFs. Raster content of any kind — scans, decorative logos, images beside usable text — makes a page `needs_ocr` or `unusable`; mixed pages stay inventoried and failed/blank pages cannot disappear from a completed assessment. The full rejection matrix (signature, encryption, malformed structure, unsupported annotations, rotation, vector-only content, unusable text accounting) is recorded in [pdf-extraction.md](pdf-extraction.md); page accounting, table/row/column preservation, and adjacent-page continuity are verified there on the supplied chart and policy snapshots plus the controlled fixture corpus.

## Limit enforcement

Parser limits are configured in `NativePdfConfig` and enforced at intake:

| Limit | Configured | Response |
| --- | --- | --- |
| Upload bytes | `max_bytes` (read bounded at `max_bytes + 1`) | 413 `unsupported_input` naming the byte limit |
| Page count | `max_pages` | explicit page-limit rejection |
| Page characters | `max_chars_per_page` | explicit unusable-page record |
| Table cells / gap splitting | table strategy bounds | per `NativePdfConfig` |

API-level evidence: `tests/integration/test_api.py` exercises 415 non-PDF, 422 truncated/malformed, 422 encrypted, 422 bad role, 422 missing file, and 413 oversize responses ([HTTP API record](http-api.md)); `tests/integration/test_documents.py` exercises the parser-level blank/mixed/annotated/vector cases.

## Rendered stage-input guardrail

`render_stage_input` produces the model packet; the workflow guards each stage at 200,000 rendered characters (provisional, `WorkflowLimits`). Measured A01 lengths ([workflow record](workflow.md)): scope 51,533, policy 40,776, evidence 10,992 characters — the supplied pair clears the guardrail by roughly 4× on the largest stage.

## No OCR; what remains unmeasured

- **OCR is not implemented.** `needs_ocr` pages are explicit rejections, not a degradation path.
- **Model token envelope** — rendered characters are not tokens; the actual input token utilization and whether `max_output_tokens=4096` suffices per stage require live calls. The quota is deferred, so no measured token envelope exists.
- **Output-budget sufficiency** — same gate. A live run would need the adapter's finish-reason/length accounting to confirm the budget.

## Evidence that would justify an OCR experiment

A scan/OCR path is worth reopening only if real clinic inputs demonstrably fail intake — e.g., sampled uploads rejected as `needs_ocr`/`unsupported_image_content` at a meaningful rate in the field, or a mandatory source family (fax scans, photographed charts) that cannot be re-exported to native text. Absent that, the conservative rejection boundary is the cheaper, safer stance.
