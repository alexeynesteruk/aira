# Integrated evaluation and regression checks

Give assessors and contributors evidence of what the combined application can do, where it fails, and whether a change regresses a required behavior.

Work package: [WP-16](../work-breakdown.md#wp-16-integrated-regression-and-evaluation). Kind: engineering enabler. Milestone: M5. Owner role: Evaluation/integration. Implementation status and ownership are tracked in the [work breakdown](../work-breakdown.md#work-packages-and-dependencies).

## Business requirements

- [BR-011](../requirements/business-requirements.md#br-011-generality-and-independent-evaluation): exercise two policy families, unfamiliar inputs, uncertainty, and useful failures against independent expectations.
- Report observed capability and limitations; a small case suite does not establish a reduction in denials or general clinical accuracy.

## Technical requirements

- [TR-017](../requirements/technical-requirements.md#tr-017-evaluation-and-release-gates): combine unit/integration checks, saved browser journeys, and separately tagged live semantic evaluations. Keep ordinary CI independent of live provider credentials.
- Apply the [release gates](../evaluation.md#metrics-and-release-gates); tests accompany earlier implementation packages, while this package verifies their integration.

## Implementation tasks

- [ ] Run the applicable A01–A20 scenarios with the integrated parser, provider, storage, API, and UI.
- [x] Add CI for the real deterministic checks and build/type/lint commands.
- [ ] Run the second-family and changed-policy cases and selected repeated model trials; record disagreements.
- [x] Test failure, interruption, annotation conflict, cache invalidation, and source-navigation behavior.
- [x] Download both export formats through the real UI and compare findings, citations, unresolved issues, and input/version identities with the displayed and saved assessment (fixture interpreter).
- [ ] Publish a versioned evaluation report with input/configuration/commit identities, case counts, outcomes, timings, and usage.

## Acceptance criteria

- [x] Mandatory deterministic checks pass and meaningful negative controls fail as expected.
- [ ] The release corpus has no known accepted mismatch, fabricated citation, unsupported satisfied finding, omitted mandatory condition/edge, or incorrect mandatory branch.
- [ ] Unsupported and ambiguous cases retain the intended input/review/failure state rather than a favorable result.
- [ ] Expected outputs remain independent; fixes or scope changes are explained and retested. Counts and failures appear alongside successes.
- [ ] [A19](../evaluation.md#required-scenarios) receives integrated browser evidence, including real downloads and UI/export/saved-record parity; independent clean-checkout/live delivery evidence remains WP-18.

## Dependencies and references

Requires [WP-13](13-staff-review-interface.md), [WP-14](14-assessment-exports.md), and [WP-15](15-ocr-input-limits.md). Use [test layers](../evaluation.md#test-layers), [metrics and release gates](../evaluation.md#metrics-and-release-gates), and [artifact identity](../architecture.md#execution-and-persistence). Findings feed WP-18; evaluator agreement alone is not ground truth. Controlled/fixture evidence is in [results/review-ui.md](../results/review-ui.md) and the earlier records; the live semantic evaluation report remains open.
