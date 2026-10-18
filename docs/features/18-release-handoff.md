# Release verification and design note

Give assessors a runnable, accurately described submission and enough evidence to discuss the implementation's judgments, failures, and extension path.

Work package: [WP-18](../work-breakdown.md#wp-18-release-evidence-and-handoff). Kind: delivery enabler. Milestone: M6. Owner role: Integration. Implementation status and ownership are tracked in the [work breakdown](../work-breakdown.md#work-packages-and-dependencies).

## Business requirements

- [BR-010](../requirements/business-requirements.md#br-010-one-command-live-reviewer-workflow): prove the advertised command in a fresh environment.
- [BR-011](../requirements/business-requirements.md#br-011-generality-and-independent-evaluation): use a separately held-out pair and report observed limits.
- [BR-012](../requirements/business-requirements.md#br-012-submission-and-design-discussion): prepare code, run instructions, and the short design note at least one day before the 45-minute call.

## Technical requirements

- [TR-017](../requirements/technical-requirements.md#tr-017-evaluation-and-release-gates): require release evidence for the implemented revision and retain every material failure/limitation.
- [TR-018](../requirements/technical-requirements.md#tr-018-packaging-and-reviewer-delivery): verify the packaged workflow and document where judgment lives, data versus code, messy-input failure boundaries, and a future hosting extension.

## Implementation tasks

- [ ] Check out the release candidate into a fresh directory and follow only the documented setup/launch instructions.
- [ ] Process the held-out pair with live inference; inspect source citations and exports.
- [ ] Record actual build/type/lint/test results, environment, command, input/configuration identity, and remaining limits.
- [ ] Write the design note from the shipped behavior and observed tradeoffs. (A draft exists at [docs/design-note.md](../design-note.md) with live observations pending.)
- [ ] Prepare the repository or zip and a short demonstration of one successful case and one useful failure.
- [ ] Confirm the call date and submission deadline; prepare handoff materials without sending messages to assessors.

- [ ] Include [WP-19/A21](19-long-document-rule-compilation.md) long-document build/reuse/recovery and direct-OpenAI source/export checks in the release verification record.

## Acceptance criteria

- [ ] [A11 and A19](../evaluation.md#required-scenarios) pass on the identified release revision with documented OpenAI model access and no author-specific dependency.
- [ ] No critical release blocker remains; previous results and input versions remain inspectable.
- [ ] The [verification record](../evaluation.md#final-verification-record) contains observed results rather than expected successes.
- [ ] Code, prerequisites, launch command, known limits, and design note are ready for the agreed delivery deadline. Actual external submission requires user authorization.

## Dependencies and references

Requires [WP-16](16-evaluation-regression.md) and [WP-17](17-reviewer-packaging.md). Follow the [release gates](../evaluation.md#metrics-and-release-gates), [interview preparation](../implementation-plan.md#interview-preparation), and [assessment obligations](../requirements/business-requirements.md#br-012-submission-and-design-discussion). This package verifies and describes the product; it does not add production infrastructure.
