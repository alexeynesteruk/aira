# OCR decision and supported input limits

Staff and assessors know which PDFs the release can process and receive explicit rejection when an input exceeds that boundary. Document and model-integration owners establish measured native-text limits. Unsupported scans are explicitly rejected in the initial MVP; adding OCR requires a later justified scope decision.

**Work package:** [WP-15](../work-breakdown.md#wp-15-ocr-and-input-envelope). **Kind:** Enabler. **Milestone:** M2. **Owner role:** Documents/model integration. **Status:** [Work breakdown](../work-breakdown.md#work-packages-and-dependencies).

## Business requirements

- [BR-001](../requirements/business-requirements.md#br-001-new-guideline-and-chart-uploads): process unfamiliar inputs within a declared boundary rather than silently dropping unsupported content.
- [BR-009](../requirements/business-requirements.md#br-009-progress-and-useful-failure-recovery): identify unreadable pages and exceeded limits with a next action.
- [BR-011](../requirements/business-requirements.md#br-011-generality-and-independent-evaluation): substantiate input-support claims with representative reviewed cases.

## Technical requirements

[TR-003](../requirements/technical-requirements.md#tr-003-ocr-support-and-input-limits) requires an explicit native-text support boundary and complete page accounting. Image-only or unusable pages must be identified rather than represented as absent clinical evidence. A later OCR adapter would need extraction-method, model/block, and original-page provenance plus its own failure and limit checks. [TR-016](../requirements/technical-requirements.md#tr-016-measurement-and-resource-budgets) requires measured byte/page/token budgets and visible exhaustion rather than truncation.

## Implementation tasks

- [x] Create full-scan, mixed-page, table, and adjacent-page fixtures from reviewed examples.
- [x] Compare native extraction with original rendered pages; detect unsupported scans, mixed-page failures, and misleading text layers.
- [x] Record a per-page extraction completeness score (`extraction_score`) on `ExtractedPage`, based on retained native characters versus source characters.
- [ ] Combine parser and model results to select upload/page/input-output token limits and test their boundaries.
- [x] Record the native-text support decision and scan limitations; document any evidence that would justify a later OCR experiment.
- [x] Implement an optional Tesseract OCR fallback for image-only pages when `ocr_enabled` is true and the configured command is available; OCR pages are marked `method=ocr`.

- [ ] Establish the [WP-19](19-long-document-rule-compilation.md) 100/200-page native-guideline envelope with parser/intake tests, tokenizer and output reservations, oversized atomic-unit handling, and measured total build budgets. Current limits are not acceptance evidence.

## Acceptance criteria

- [x] A13 preserves table relationships and cross-page continuity for the supported native-text inputs.
- [x] A14 accounts for every original page, including blank and failed pages. A failed page cannot disappear from a completed assessment.
- [x] A14 explicitly rejects unsupported scans or over-limit documents; no text-only path claims tested OCR support.
- [ ] A16/A18 expose token-budget exhaustion and unusable extraction without accepting partial input as complete; measurements identify actual tested limits.

Use the [evaluation matrix](../evaluation.md#required-scenarios). Live model access is verified separately in WP-05.

## Dependencies and references

Completion dependencies: [WP-03](../work-breakdown.md#wp-03-annotated-fixtures-and-evaluation-expectations), [WP-04](../work-breakdown.md#wp-04-native-pdf-extraction), [WP-05](../work-breakdown.md#wp-05-model-experiment-and-adapter).

Evidence is recorded in [results/input-limits.md](../results/input-limits.md); the token-envelope task stays open behind the deferred quota. Design references: [PDF support boundary](../model-provider.md#pdf-support-and-future-options), [measured decisions](../requirements/technical-requirements.md#measured-limits-and-open-feasibility-decisions), and [source representation](../architecture.md#domain-records).
