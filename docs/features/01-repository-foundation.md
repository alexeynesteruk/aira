# Repository foundation and executable checks

Give contributors a runnable Python/TypeScript shell and repeatable checks so later feature changes can be integrated and reviewed without author-specific tooling.

Work package: [WP-01](../work-breakdown.md#wp-01-repository-foundation). Kind: engineering enabler. Milestone: M0. Owner role: Integration. Implementation status and ownership are tracked in the [work breakdown](../work-breakdown.md#work-packages-and-dependencies).

## Business requirements

- [BR-010](../requirements/business-requirements.md#br-010-one-command-live-reviewer-workflow): establish a portable project foundation for the later clean-checkout reviewer workflow.
- [BR-011](../requirements/business-requirements.md#br-011-generality-and-independent-evaluation): provide executable checks that can verify behavior as features arrive.
- [BR-012](../requirements/business-requirements.md#br-012-submission-and-design-discussion): keep documented commands and deliverable status truthful.

## Technical requirements

- [TR-017](../requirements/technical-requirements.md#tr-017-evaluation-and-release-gates): configure actual lint, type, test, and build entry points; ordinary CI must run without AWS credentials.
- [TR-018](../requirements/technical-requirements.md#tr-018-packaging-and-reviewer-delivery): create the application/toolchain baseline and lock dependencies. Final Docker packaging and live launch evidence belong to WP-17 and WP-18.

## Implementation tasks

- [ ] Create the minimal FastAPI entry point and React/TypeScript shell in the planned folders.
- [ ] Add Python/JavaScript dependency manifests, lockfiles, and configuration examples without credentials.
- [ ] Document real installation, development, and verification commands.
- [ ] Configure CI to execute the checks that exist and fail on a broken build/type check.
- [ ] Record supported local prerequisites and the first successful shell build.

## Acceptance criteria

- [ ] A fresh checkout can install dependencies and start the shell using documented prerequisites.
- [ ] Frontend and backend build/type/lint checks execute successfully; a deliberately broken check produces failure rather than a placeholder success.
- [ ] The shell and deterministic checks do not require a live AWS account. This contributes setup evidence to [A19](../evaluation.md#required-scenarios); it does not satisfy the live-assessment release test.
- [ ] No uploaded-document workflow, model accuracy, or working final launch command is claimed before those features exist.

## Dependencies and references

No implementation prerequisite; use the current requirements/design baseline. WP-02 consumes this foundation. Follow the [planned repository structure](../implementation-plan.md#planned-repository-structure), [component boundaries](../architecture.md#components-and-dependency-direction), and [repository instructions](../../AGENTS.md).
