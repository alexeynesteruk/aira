# OCR decision and supported input limits

Staff and assessors know which PDFs the release can process and receive explicit rejection when an input exceeds that boundary. Document and model-integration owners establish measured limits and decide whether verified scan support fits the MVP.

**Work package:** [WP-15](../work-breakdown.md#wp-15-ocr-and-input-envelope). **Kind:** Enabler. **Milestone:** M2. **Owner role:** Documents/model integration. **Status:** [Work breakdown](../work-breakdown.md#work-packages-and-dependencies).

## Business requirements

- [BR-001](../requirements/business-requirements.md#br-001-new-guideline-and-chart-uploads): process unfamiliar inputs within a declared boundary rather than silently dropping unsupported content.
- [BR-009](../requirements/business-requirements.md#br-009-progress-and-useful-failure-recovery): identify unreadable pages and exceeded limits with a next action.
- [BR-011](../requirements/business-requirements.md#br-011-generality-and-independent-evaluation): substantiate input-support claims with representative reviewed cases.

## Technical requirements

[TR-003](../requirements/technical-requirements.md#tr-003-ocr-support-and-input-limits) requires either verified OCR or an explicit text-only limitation. Conditional OCR uses synchronous Textract on individual suspect pages, preserves method/model/block provenance, and remaps original page numbers. Synchronous PDF/TIFF inputs are limited to one page and 10 MB; application limits must remain within service ceilings. [TR-016](../requirements/technical-requirements.md#tr-016-measurement-and-resource-budgets) requires measured byte/page/token budgets, OCR-page accounting, and visible exhaustion rather than truncation.

## Implementation tasks

- [ ] Create full-scan, mixed-page, table, and adjacent-page fixtures from reviewed examples.
- [ ] Trial pagewise Textract if access permits; compare output with original rendered pages and preserve native/OCR distinction.
- [ ] Combine parser and Bedrock results to select upload/page/OCR/input-output token limits and test their boundaries.
- [ ] Record the support decision and limitations; ship the OCR adapter only if its extraction and failure checks pass.

## Acceptance criteria

- [ ] If OCR is included, A13 preserves table relationships and cross-page continuity after pagewise processing.
- [ ] A14 accounts for every original page, including blank and failed pages. A failed page cannot disappear from a completed assessment.
- [ ] A14 explicitly rejects unsupported scans or over-limit documents; no text-only path claims tested OCR support.
- [ ] A16/A18 expose token-budget exhaustion and, if OCR is included, OCR failure without accepting partial input as complete; measurements identify actual tested limits.

Use the [evaluation matrix](../evaluation.md#required-scenarios). Missing Textract access permits a documented text-only decision; Bedrock access for live assessment remains required.

## Dependencies and references

Completion dependencies: [WP-03](../work-breakdown.md#wp-03-annotated-fixtures-and-evaluation-expectations), [WP-04](../work-breakdown.md#wp-04-native-pdf-extraction), [WP-05](../work-breakdown.md#wp-05-bedrock-experiment-and-adapter); Textract access if trialing OCR.

Design references: [verified Textract constraints](../aws.md#textract-scan-experiment), [measured decisions](../requirements/technical-requirements.md#measured-limits-and-open-feasibility-decisions), and [source representation](../architecture.md#domain-records).
