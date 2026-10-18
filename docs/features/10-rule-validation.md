# Provenance validation and rule evaluation

The application produces a traceable result from validated evidence and supported policy logic. This enabler protects staff from plausible but invalid citations, malformed rule graphs, and incorrect aggregation.

Work package and status: [WP-10](../work-breakdown.md#wp-10-validation-and-evaluation-core). Kind: **Enabler**. Milestone: **M3**. Owner: [Domain](../work-breakdown.md#work-packages-and-dependencies).

## Business requirements

- [BR-004](../requirements/business-requirements.md#br-004-faithful-and-complete-policy-requirements): evaluate the policy's actual mandatory and alternative relationships; unresolved governing conditions block favorable readiness.
- [BR-005](../requirements/business-requirements.md#br-005-distinct-evidence-states): preserve uncertainty and contrary evidence rather than reducing findings to a percentage.
- [BR-006](../requirements/business-requirements.md#br-006-inspectable-policy-and-chart-citations): reject references that do not resolve to the correct input and source passage.

Deterministic validation cannot prove that a real quotation supports an interpretation or that an extractor found every condition; semantic evaluation remains separate.

## Technical requirements

Implement [TR-008](../requirements/technical-requirements.md#tr-008-citation-and-domain-validation) and [TR-009](../requirements/technical-requirements.md#tr-009-deterministic-aggregation-and-blockers) as pure functions. Validate types, IDs, source revisions/pages/spans, excerpts, numeric evidence, and graph invariants. Permit documented whitespace normalization, not fuzzy repair of invented quotations.

Map `met` to true, `not_met` to false, and other finding states to unknown. Apply three-valued AND/OR, preserving child findings and reasons. Keep applicability, completeness, and unsupported-interpretation blockers independent of tree truth. Unsupported date/unit semantics require review. No HTTP, storage, model, or cloud dependency is needed to execute this core.

## Implementation tasks

- [x] Implement span resolution and typed domain/graph validation.
- [x] Implement bounded numeric/date predicates and three-valued aggregation.
- [x] Return evaluation traces and independent readiness blockers.
- [x] Add direct tests with deliberately broken citation, graph, and operator controls.

## Acceptance criteria

- [x] AND/OR truth tables preserve unknown reasons and valid alternative paths. [A06, A07](../evaluation.md#required-scenarios)
- [x] Boundaries work only with supported units, contexts, and date semantics. [A08](../evaluation.md#required-scenarios)
- [x] Wrong pages/documents, invented excerpts, cycles, and unresolved references cannot produce valid findings. [A15](../evaluation.md#required-scenarios)
- [x] A true tree cannot override a known unresolved mandatory condition. [A20](../evaluation.md#required-scenarios)

## Dependencies and references

Completion depends on [WP-02](../work-breakdown.md#wp-02-domain-and-interface-contracts) and [WP-03](../work-breakdown.md#wp-03-annotated-fixtures-and-evaluation-expectations). Follow [finding and aggregation semantics](../architecture.md#finding-and-aggregation-semantics) and [validation boundaries](../architecture.md#validation-boundaries). The verified results are recorded in [results/rules.md](../results/rules.md); the remaining boundary is semantic evaluation in WP-16.
