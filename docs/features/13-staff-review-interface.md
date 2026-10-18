# Staff upload and review interface

Clinic staff upload a policy and chart, inspect the resulting checklist and source pages, and understand what clarification or documentation is needed next.

Work package and status: [WP-13](../work-breakdown.md#wp-13-staff-interface). Kind: **Feature**. Milestone: **M4**. Owner: [Frontend](../work-breakdown.md#work-packages-and-dependencies).

## Business requirements

- [BR-002](../requirements/business-requirements.md#br-002-one-selected-request-with-relevant-side-and-dates) and [BR-003](../requirements/business-requirements.md#br-003-policy-applicability-gate): confirm one request and make applicability or clarification needs clear.
- [BR-005](../requirements/business-requirements.md#br-005-distinct-evidence-states) and [BR-006](../requirements/business-requirements.md#br-006-inspectable-policy-and-chart-citations): distinguish findings and open their actual sources.
- [BR-007](../requirements/business-requirements.md#br-007-actionable-gaps-and-human-clarification) and [BR-009](../requirements/business-requirements.md#br-009-progress-and-useful-failure-recovery): explain next actions, preserve annotations, and support useful retry.

The interface displays backend judgments; it does not evaluate coverage rules or provide a manual clinical `met` override.

## Technical requirements

Implement [TR-014](../requirements/technical-requirements.md#tr-014-review-and-clarification-interface) using the [HTTP contracts](../requirements/technical-requirements.md#http-interface-contracts). Provide upload, request summary, applicability, grouped findings, source inspection, progress, issues, and linked clarification/retry flows. Keep execution status separate from readiness outcome.

Use original page numbering and extraction-specific spans. Missing findings display documentation needs without an invented citation. Conflicting metadata clarification shows the original source, chosen value, and reason. Persisted runs reopen through their URL after restart. Keep technical traces in an inspection view and wire export actions to the HTTP contract.

## Implementation tasks

- [x] Build React/TypeScript upload, review, source, and clarification views.
- [x] Implement status polling, terminal outcomes, useful errors, and linked reruns.
- [x] Add source navigation, persisted-run loading, and export actions.
- [x] Verify review/source/clarification flows against the real API with saved browser checks; test export actions against the endpoint contract until WP-14 is ready.

## Acceptance criteria

- [ ] Matched, mismatched, missing, contrary, and conflicting cases have distinguishable visible outcomes. [A01–A05](../evaluation.md#required-scenarios)
- [x] Clarification preserves source facts; both policy and chart citations open the correct pages. [A12, A13](../evaluation.md#required-scenarios)
- [x] Dependency failure explains recovery without displaying a clinical conclusion. [A16](../evaluation.md#required-scenarios)
- [x] A reviewer reopens a saved run and inspects sources; the export action sends the requested format and handles the documented response. Live download and content parity are verified in WP-16. [A19](../evaluation.md#required-scenarios)

## Dependencies and references

Completion depends on [WP-12](../work-breakdown.md#wp-12-http-and-source-api). Coordinate the download contract with [WP-14](../work-breakdown.md#wp-14-exports); [WP-16](16-evaluation-regression.md) verifies their integration. Follow [component boundaries](../architecture.md#components-and-dependency-direction) and the [run lifecycle](../architecture.md#request-and-run-lifecycle). The fixture-interpreter evidence is recorded in [results/review-ui.md](../results/review-ui.md); the remaining boundary covers contrary/conflicting run cases and WP-16 live parity.
