# Chart facts and criterion evidence

Clinic staff can see which chart passages support, contradict, or leave uncertainty about each policy requirement. Evidence retains its clinical context and provenance through the assessment.

Work package and status: [WP-09](../work-breakdown.md#wp-09-evidence-mapping). Kind: **Feature**. Milestone: **M3**. Owner: [Domain](../work-breakdown.md#work-packages-and-dependencies).

## Business requirements

- [BR-005](../requirements/business-requirements.md#br-005-distinct-evidence-states): distinguish supported, contrary, missing, conflicting, and review-required evidence. Operational failure is never a missing clinical fact.
- [BR-006](../requirements/business-requirements.md#br-006-inspectable-policy-and-chart-citations): attach real chart spans and retain competing sources for conflicts.
- [BR-002](../requirements/business-requirements.md#br-002-one-selected-request-with-relevant-side-and-dates): match evidence to the selected procedure, side, and relevant dates.

This feature extracts documented propositions; it does not create new clinical facts or issue a payer decision.

## Technical requirements

Implement [TR-007](../requirements/technical-requirements.md#tr-007-evidence-facts-and-uncertainty) as chart-only extraction followed by separate assessment. The first model process receives no policy, criteria, request selection, or annotations and saves source-bound administrative and clinical facts. The assessment process receives saved facts, validated request metadata, and the saved rule set and returns findings referencing existing fact IDs. It cannot create new facts. Facts preserve polarity, values/units, anatomy, event/documentation dates, repeated claims, and conflicting alternatives. Findings use `met`, `not_met`, `missing`, `conflicting`, or `needs_review` with rationale and evidence references.

Summary assertions retain their summary provenance; a normal-CBC statement cannot generate absent laboratory values. Route candidate citations and predicate inputs through [TR-008 validation](../requirements/technical-requirements.md#tr-008-citation-and-domain-validation). A missing finding has no fabricated evidence span. Document instructions remain source content.

## Implementation tasks

- [x] Implement fact extraction through the chart build (`app.policies.convert_chart`) and criterion evidence mapping onto those saved facts (`app.policies.convert_findings`), with citation/predicate validation in `backend/app/evidence/`.
- [x] Add versioned prompts, source-bound fact records, and uncertainty handling.
- [x] Add a must-have chart-evidence completeness check: an assessment with no extracted chart facts receives a blocking review issue and cannot be marked satisfied.
- [ ] Preserve chronological and anatomical constraints across page-spanning passages.
- [ ] Add paired evidence-removal, negation, conflict, and distractor cases.

- [ ] Verify independent chart-artifact reuse and saved-fact-only mapping under WP-19 LD-AC05/LD-AC09; an assessment cannot add facts missing from the saved extraction.

## Acceptance criteria

- [ ] Supported, removed, negated, and contradictory evidence yield distinct findings. [A02–A05](../evaluation.md#required-scenarios)
- [ ] Wrong-side, incompatible-unit, and post-cutoff facts cannot silently satisfy a requirement. [A05, A08, A12](../evaluation.md#required-scenarios)
- [ ] Invented or unrelated evidence fails validation or annotated semantic expectations. [A15](../evaluation.md#required-scenarios)
- [ ] Evidence remains discoverable among distractors without obeying embedded instructions. [A18](../evaluation.md#required-scenarios)

## Dependencies and references

Completion depends on [WP-04](../work-breakdown.md#wp-04-native-pdf-extraction), [WP-05](../work-breakdown.md#wp-05-model-experiment-and-adapter), and [WP-10](../work-breakdown.md#wp-10-validation-and-evaluation-core). Develop against agreed request/policy fixtures; WP-11 enforces runtime order. Follow [domain records](../architecture.md#domain-records) and [finding semantics](../architecture.md#finding-and-aggregation-semantics). Controlled-interpreter evidence is in [results/stage-interpreter.md](../results/stage-interpreter.md); acceptance requires live semantic evidence, blocked by the deferred API quota.
