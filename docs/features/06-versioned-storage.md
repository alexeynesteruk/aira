# Versioned local storage and artifact identity

Staff can reopen an assessment with the exact sources and processing configuration that produced it. Backend developers can safely reuse completed work while preserving old results after a document, request, or implementation changes.

**Work package:** [WP-06](../work-breakdown.md#wp-06-storage-and-identity). **Kind:** Enabler. **Milestone:** M3. **Owner role:** Backend. **Status:** [Work breakdown](../work-breakdown.md#work-packages-and-dependencies).

## Business requirements

- [BR-008](../requirements/business-requirements.md#br-008-saved-assessments-and-versioned-exports): save traceable results and retain their original document/configuration associations.
- [BR-006](../requirements/business-requirements.md#br-006-inspectable-policy-and-chart-citations): keep the source content behind stored citations available.
- [BR-009](../requirements/business-requirements.md#br-009-progress-and-useful-failure-recovery): preserve failed/interrupted attempts and recovery history.

## Technical requirements

[TR-012](../requirements/technical-requirements.md#tr-012-storage-identity-and-cache-isolation) requires SQLite repositories, immutable local artifacts, explicit document roles/run references, and fingerprints covering relevant inputs, parser, provider/model, SDK, prompts, schemas, and inference settings. Request context and annotations also affect assessment identity. [TR-002](../requirements/technical-requirements.md#tr-002-immutable-sources-and-layout-extraction) requires immutable originals and extraction revisions. Stored annotations retain provenance; they do not replace source evidence.

## Implementation tasks

- [x] Implement `backend/app/storage/` repositories for documents, extractions, runs, annotations, and validated artifacts.
- [x] Define fingerprint construction and lookup rules; reuse only compatible completed artifacts.
- [x] Persist artifact files before publishing completed-stage metadata, so incomplete writes cannot appear reusable.
- [x] Add reload, lineage, role/reference, configuration-change, and interrupted-write tests without contacting a model provider.

## Acceptance criteria

- [x] A09 retains an old result while a changed guideline produces a distinct result tied to its new input.
- [x] A15 rejects wrong-document references rather than resolving similar content elsewhere.
- [x] A17 reuses compatible work but invalidates affected artifacts after parser, prompt, model, request, or annotation changes.
- [x] A17 preserves failed/interrupted attempts and does not expose missing artifact files as completed reusable stages.

Checks follow the [evaluation matrix](../evaluation.md#required-scenarios). Duplicate uploads may share immutable bytes while retaining correct application metadata and roles. Fixed temperature is not a substitute for saving actual model output.

## Dependencies and references

Completion dependency: [WP-02](../work-breakdown.md#wp-02-domain-and-interface-contracts).

Design references: [domain records](../architecture.md#domain-records), [execution and persistence](../architecture.md#execution-and-persistence), and [run lifecycle](../architecture.md#request-and-run-lifecycle). Workflow transition ownership remains with WP-11; storage does not invoke parsers/models or advance the assessment itself. The verified results are recorded in [results/storage.md](../results/storage.md); the remaining boundary is workflow integration in WP-11.
