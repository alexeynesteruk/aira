# Domain and interface contract baseline

Give parser, model, storage, evaluator, and UI contributors a shared vocabulary so the same evidence and uncertainty survive every stage.

Work package: [WP-02](../work-breakdown.md#wp-02-domain-and-interface-contracts). Kind: engineering enabler. Milestone: M0. Owner role: Backend/integration. Implementation status and ownership are tracked in the [work breakdown](../work-breakdown.md#work-packages-and-dependencies).

## Business requirements

- [BR-001](../requirements/business-requirements.md#br-001-new-guideline-and-chart-uploads), [BR-002](../requirements/business-requirements.md#br-002-one-selected-request-with-relevant-side-and-dates), and [BR-003](../requirements/business-requirements.md#br-003-policy-applicability-gate): represent new documents and one explicit request with unresolved scope.
- [BR-004](../requirements/business-requirements.md#br-004-faithful-and-complete-policy-requirements), [BR-005](../requirements/business-requirements.md#br-005-distinct-evidence-states), and [BR-006](../requirements/business-requirements.md#br-006-inspectable-policy-and-chart-citations): preserve policy structure, evidence states, and inspectable sources.
- [BR-007](../requirements/business-requirements.md#br-007-actionable-gaps-and-human-clarification), [BR-008](../requirements/business-requirements.md#br-008-saved-assessments-and-versioned-exports), [BR-009](../requirements/business-requirements.md#br-009-progress-and-useful-failure-recovery), and [BR-010](../requirements/business-requirements.md#br-010-one-command-live-reviewer-workflow): retain annotations, run identity, useful errors, and provider configuration. This package supplies contracts, not complete workflows.

## Technical requirements

- [TR-001](../requirements/technical-requirements.md#tr-001-pdf-intake-and-page-inventory), [TR-002](../requirements/technical-requirements.md#tr-002-immutable-sources-and-layout-extraction), [TR-003](../requirements/technical-requirements.md#tr-003-ocr-support-and-input-limits): document, page, span, extraction, and quality records.
- [TR-004](../requirements/technical-requirements.md#tr-004-request-context-and-user-annotations), [TR-005](../requirements/technical-requirements.md#tr-005-applicability-gate), [TR-006](../requirements/technical-requirements.md#tr-006-policy-requirements-and-logical-structure), [TR-007](../requirements/technical-requirements.md#tr-007-evidence-facts-and-uncertainty): request, scope, flat policy graph, fact, and finding contracts.
- [TR-008](../requirements/technical-requirements.md#tr-008-citation-and-domain-validation), [TR-009](../requirements/technical-requirements.md#tr-009-deterministic-aggregation-and-blockers), [TR-010](../requirements/technical-requirements.md#tr-010-bedrock-contract-and-configuration), [TR-011](../requirements/technical-requirements.md#tr-011-bounded-execution-and-failure-lifecycle), [TR-012](../requirements/technical-requirements.md#tr-012-storage-identity-and-cache-isolation): validation boundaries, result/blocker fields, configuration versions, lifecycle, and lineage.
- [TR-013](../requirements/technical-requirements.md#tr-013-http-and-health-contracts), [TR-014](../requirements/technical-requirements.md#tr-014-review-and-clarification-interface), [TR-015](../requirements/technical-requirements.md#tr-015-traceable-exports): shared API, UI, and export examples.

## Implementation tasks

- [ ] Implement versioned typed records in `backend/app/schemas/` and explicit enums for status, phase, outcome, and evidence state.
- [ ] Add provider-compatible flat schemas and distinguish transport validation from local invariants.
- [ ] Publish valid and invalid contract examples for independent contributors.
- [ ] Add rejection tests for invalid types, identifiers, states, and malformed references; leave pure rule evaluation to WP-10.
- [ ] Establish a schema owner and record reviewed amendments after the parser/Bedrock experiments.

## Acceptance criteria

- [ ] Contract fixtures represent mismatch, missing, contrary, conflict, clarification, failure, and completed review without collapsing their states.
- [ ] The versioned examples support [A07, A12, A15–A17, and A20](../evaluation.md#required-scenarios); domain behavior is verified by downstream packages.
- [ ] Parser/provider/storage consumers can share records without importing HTTP or cloud side effects into the schema package.

## Dependencies and references

Requires [WP-01](01-repository-foundation.md). See [domain records](../architecture.md#domain-records), [policy structure](../architecture.md#policy-structure), and the authoritative [HTTP/status contracts](../requirements/technical-requirements.md#http-interface-contracts). This is an initial baseline; reviewed feasibility findings may change it before integration.
