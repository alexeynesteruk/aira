# Annotated fixtures and expected outcomes

Give implementers independent examples of correct and incorrect behavior before prompts or application logic are tuned.

Work package: [WP-03](../work-breakdown.md#wp-03-annotated-fixtures-and-evaluation-expectations). Kind: engineering enabler. Milestone: M0. Owner role: Evaluation. Implementation status and ownership are tracked in the [work breakdown](../work-breakdown.md#work-packages-and-dependencies).

## Business requirements

- [BR-011](../requirements/business-requirements.md#br-011-generality-and-independent-evaluation): evaluate two policy families and unseen charts with source-reviewed expectations and a held-out release pair.
- [BR-001](../requirements/business-requirements.md#br-001-new-guideline-and-chart-uploads): use examples to prove input-driven behavior, not to supply embedded production answers.

## Technical requirements

- [TR-017](../requirements/technical-requirements.md#tr-017-evaluation-and-release-gates): maintain independent expected applicability, criteria, logical edges, evidence spans, findings, and unresolved issues.
- Use the [WP-02 contracts](02-domain-contracts.md) for fixture formats. Keep development examples, held-out inputs, and recorded provider responses distinguishable; a response fixture tests an adapter rather than establishing model quality.

## Implementation tasks

- [ ] Create manifests with source hashes, selected request, fixture purpose, annotation provenance, and expected results.
- [ ] Add fictional matched vascular charts and missing, negative, conflicting, and wrong-context variants.
- [ ] Keep the supplied pair as a mismatch; test its chronology at the extraction stage and use an applicable fictional pair for end-to-end conflict handling.
- [ ] Add a controlled synthetic policy change and select a second policy family; reserve an independent release pair.
- [ ] Map every evaluation scenario to inputs or a concrete fixture-construction task; label synthetic materials clearly.

## Acceptance criteria

- [ ] Core matched, mismatched, missing, contrary, and conflicting cases have reviewed source-based expectations before prompt tuning: [A01–A05](../evaluation.md#required-scenarios).
- [ ] Expected trees preserve branch semantics and completeness blockers: [A06–A08 and A20](../evaluation.md#required-scenarios).
- [ ] The changed-rule case is distinct from the BCBS pair whose clinical pages did not change: [A09–A11](../evaluation.md#required-scenarios).
- [ ] Evaluation cannot rewrite expectations silently. A held-out case used for tuning is recorded and replaced before release.

## Dependencies and references

Requires [WP-02](02-domain-contracts.md). Deliver `tests/fixtures/`, `evals/cases/`, and `evals/expected/` according to [case design](../evaluation.md#case-design), [source findings](../exploration.md), and [guideline provenance](../../examples/guidelines/README.md). Fixture coverage prepares later checks; this feature does not claim they have run.
