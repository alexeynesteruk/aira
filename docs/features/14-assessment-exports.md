# Traceable assessment exports

Clinic staff and assessors can download a readable checklist or structured assessment that matches the saved run, including unresolved issues and the sources behind its findings.

Work package and status: [WP-14](../work-breakdown.md#wp-14-exports). Kind: **Feature**. Milestone: **M4**. Owner: [Backend/frontend](../work-breakdown.md#work-packages-and-dependencies).

## Business requirements

- [BR-008](../requirements/business-requirements.md#br-008-saved-assessments-and-versioned-exports): retain exact input/version identities and earlier results when a later assessment changes.
- [BR-006](../requirements/business-requirements.md#br-006-inspectable-policy-and-chart-citations): preserve requirement and evidence references in the downloaded artifact.
- [BR-007](../requirements/business-requirements.md#br-007-actionable-gaps-and-human-clarification): retain uncertainty, metadata clarifications, and documentation actions without inventing a conclusion.

Exports are assessment records, not insurer submissions, authorization letters, or payment guarantees.

## Technical requirements

Implement [TR-015](../requirements/technical-requirements.md#tr-015-traceable-exports) from persisted validated artifacts without another model call. Support JSON and readable Markdown for `completed` and `needs_input` runs using the [export endpoint](../requirements/technical-requirements.md#http-interface-contracts).

Include run/parent IDs, export time, workflow/outcome, document names/hashes, policy version fields, request/annotations, available criteria/findings, citations, unresolved issues, and model/parser/prompt/schema provenance. A run stopped for clarification must identify unassessed content rather than invent missing criteria or a necessity conclusion. Exclude credentials and internal secrets. Content type and download filename must match the requested format.

## Implementation tasks

- [ ] Implement deterministic JSON serialization and Markdown checklist rendering.
- [ ] Add state-aware export routing and useful unavailable-artifact responses.
- [ ] Provide the staff interface with the implemented endpoint, format, filename, and error contracts.
- [ ] Compare exported content with saved records across changed-policy and linked-run cases.

## Acceptance criteria

- [ ] Exported findings, source identities, citations, and unresolved issues match the saved run; WP-16 checks parity with the integrated UI. [A19](../evaluation.md#required-scenarios)
- [ ] An older assessment's substantive content remains unchanged after a new policy or annotation creates another run. [A09, A17](../evaluation.md#required-scenarios)
- [ ] A `needs_input` export clearly records the stop and no invented necessity outcome; failed, interrupted, or running executions cannot masquerade as completed checklists. [A16, A19](../evaluation.md#required-scenarios)
- [ ] Export generation makes no inference call and exposes no credentials. [A19](../evaluation.md#required-scenarios)

## Dependencies and references

Completion depends on [WP-11](../work-breakdown.md#wp-11-workflow-and-recovery) and [WP-12](../work-breakdown.md#wp-12-http-and-source-api). Coordinate the download contract with [WP-13](13-staff-review-interface.md); [WP-16](16-evaluation-regression.md) verifies UI integration. Follow the [run lifecycle](../architecture.md#request-and-run-lifecycle) and [execution and persistence](../architecture.md#execution-and-persistence) boundaries.
