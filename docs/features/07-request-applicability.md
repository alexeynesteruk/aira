# Request context and policy applicability

Clinic staff select the intended procedure and learn whether the uploaded policy can support its assessment. The outcome is a sourced match, a clear mismatch, or a specific clarification request.

Work package and status: [WP-07](../work-breakdown.md#wp-07-request-context-and-applicability). Kind: **Feature**. Milestone: **M3**. Owner: [Domain](../work-breakdown.md#work-packages-and-dependencies).

## Business requirements

- [BR-002](../requirements/business-requirements.md#br-002-one-selected-request-with-relevant-side-and-dates): identify one procedure, relevant side/anatomy, payer, plan, service date, and any assessment cutoff; preserve uncertainty.
- [BR-003](../requirements/business-requirements.md#br-003-policy-applicability-gate): stop necessity evaluation on a confirmed mismatch; request input when scope is unresolved.
- [BR-007](../requirements/business-requirements.md#br-007-actionable-gaps-and-human-clarification): keep metadata clarifications distinct from source facts and preserve the reason for resolving a conflict.

This feature establishes scope; it neither discovers another policy nor decides medical necessity.

## Technical requirements

Implement [TR-004](../requirements/technical-requirements.md#tr-004-request-context-and-user-annotations) and [TR-005](../requirements/technical-requirements.md#tr-005-applicability-gate). Return typed request fields, citations, unresolved fields, and applicability reasons. Revision, effective, submission, service, and observation dates remain distinct.

Return typed scope outcomes that WP-11 maps to `completed` with `applicability_mismatch` or to `needs_input`. Validate stage outputs before consumption. Clarification inputs retain original facts, annotations, and `parent_run_id`; WP-11 creates the linked run. Only request metadata is editable; clinical evidence changes require a new source document, not a manual `met` override.

## Implementation tasks

- [x] Implement scoped extraction and applicability functions using versioned prompts and contracts.
- [x] Add field-level source and annotation provenance, including conflict-resolution reasons.
- [x] Return typed mismatch, unresolved-scope, and annotation results for the workflow consumer.
- [ ] Add matched, mismatched, ambiguous, and conflicting-annotation fixtures.

## Acceptance criteria

- [ ] The supplied pair returns a cited payer/procedure mismatch that instructs the workflow to stop before necessity aggregation. [A01](../evaluation.md#required-scenarios)
- [ ] Multiple procedures, wrong-side evidence, and uncertain plan/date scope require explicit resolution. [A10, A12](../evaluation.md#required-scenarios)
- [ ] Invalid scope citations are rejected; clarification outputs retain original facts, chosen values, reasons, and the parent-run reference without mutating their inputs. [A15, A17](../evaluation.md#required-scenarios)

## Dependencies and references

Completion depends on [WP-04](../work-breakdown.md#wp-04-native-pdf-extraction), [WP-05](../work-breakdown.md#wp-05-model-experiment-and-adapter), and [WP-10](../work-breakdown.md#wp-10-validation-and-evaluation-core). Follow the [run lifecycle](../architecture.md#request-and-run-lifecycle) and [domain records](../architecture.md#domain-records). Persisted stopping and linked-run checks belong to [WP-11](11-assessment-workflow.md). Controlled-interpreter evidence is in [results/stage-interpreter.md](../results/stage-interpreter.md); acceptance requires live semantic evidence, blocked by the deferred API quota.
