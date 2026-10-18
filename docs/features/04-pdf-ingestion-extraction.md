# PDF intake and native extraction

Clinic staff and assessors can supply unfamiliar policy and chart PDFs. The document pipeline produces a complete, traceable page representation that downstream interpretation can use without losing labels, units, negation, or source identity.

**Work package:** [WP-04](../work-breakdown.md#wp-04-native-pdf-extraction). **Kind:** Feature. **Milestone:** M2. **Owner role:** Documents. **Status:** [Work breakdown](../work-breakdown.md#work-packages-and-dependencies).

## Business requirements

- [BR-001](../requirements/business-requirements.md#br-001-new-guideline-and-chart-uploads): accept new documents and derive content from their bytes rather than example-specific templates.
- [BR-006](../requirements/business-requirements.md#br-006-inspectable-policy-and-chart-citations) and [BR-008](../requirements/business-requirements.md#br-008-saved-assessments-and-versioned-exports): preserve original sources and page identity for inspection and later runs.
- [BR-009](../requirements/business-requirements.md#br-009-progress-and-useful-failure-recovery): explain unusable input and account for every page.

## Technical requirements

[TR-001](../requirements/technical-requirements.md#tr-001-pdf-intake-and-page-inventory) requires format, readability, encryption, size, role, and page-inventory checks. [TR-002](../requirements/technical-requirements.md#tr-002-immutable-sources-and-layout-extraction) requires original-byte hashes, versioned extraction, blocks/spans, table relationships, and coordinates where available. Cross-page passages retain multiple source spans. Bounded local intake checks may run during upload; full extraction runs in the assessment executor.

## Implementation tasks

- [x] Implement intake validation and one-based page inventory in `backend/app/documents/`.
- [x] Implement native extraction with parser/configuration identity, page quality issues, and layout-aware blocks.
- [x] Inspect rendered columns, tables, dates, units, and cross-page passages against extracted output.
- [x] Produce an extraction report describing tested settings, failures, and unsupported pages informing the WP-15 input boundary.

## Acceptance criteria

- [x] A05/A13 preserve the chart's conflicting date roles, table labels/values, and adjacent-page passages; citations identify the original pages.
- [x] A10 preserves both policy snapshots without inventing effective dates or clinical changes.
- [x] A14 rejects malformed, encrypted, or over-limit input clearly; blank/suspect pages remain in the inventory.
- [x] Extraction records preserve distinct document/page/span identities across inputs for WP-10's A15 citation checks. Unusable extraction never appears as fully processed input.

Checks use the [evaluation matrix](../evaluation.md#required-scenarios); this package does not claim OCR support.

## Dependencies and references

Completion dependencies: [WP-02](../work-breakdown.md#wp-02-domain-and-interface-contracts), [WP-03](../work-breakdown.md#wp-03-annotated-fixtures-and-evaluation-expectations).

Design references: [document records](../architecture.md#domain-records), [sample extraction observations](../exploration.md#pdf-extraction-observations), and [OCR/input-envelope decision](15-ocr-input-limits.md). The verified results are recorded in [results/pdf-extraction.md](../results/pdf-extraction.md); the remaining boundary is persistence/workflow use in WP-06/WP-11 and the measured model envelope in WP-15.
