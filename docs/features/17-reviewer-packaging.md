# Reviewer setup

Let an assessor start the application and process new PDFs with a documented command and explicit provider configuration prerequisites, using a fresh checkout on their machine.

Work package: [WP-17](../work-breakdown.md#wp-17-packaging-and-reviewer-setup). Kind: delivery enabler. Milestone: M6. Owner role: Integration. Implementation status and ownership are tracked in the [work breakdown](../work-breakdown.md#work-packages-and-dependencies).

## Business requirements

- [BR-010](../requirements/business-requirements.md#br-010-one-command-live-reviewer-workflow): provide the real local workflow without the author's private services or registry.
- [BR-001](../requirements/business-requirements.md#br-001-new-guideline-and-chart-uploads): preserve live processing of unfamiliar documents rather than a canned demonstration.
- [BR-012](../requirements/business-requirements.md#br-012-submission-and-design-discussion): supply truthful run instructions and setup limitations for the handoff.

## Technical requirements

- [TR-010](../requirements/technical-requirements.md#tr-010-model-contract-and-configuration): read a documented server-only `OPENAI_API_KEY` and explicit `AIRA_MODEL`; verify the configured model/API combination without exposing the key to the browser.
- [TR-018](../requirements/technical-requirements.md#tr-018-packaging-and-reviewer-delivery): package built React assets, FastAPI, and locked dependencies behind one launch command, with a persistent local data directory and a documented port.

## Implementation tasks

- [x] Add `.env.example` without secrets.
- [x] Implement the target one-line launch (`./scripts/launch.sh`) and persistent data directory.
- [x] Document OpenAI model access, server-side key/model configuration, scan limitations, input limits, and first-run behavior.
- [ ] Verify credentials with the documented preflight command and ensure setup failures remain understandable in the UI.
- [ ] Exercise a new upload, source inspection, and export through live inference.

- [ ] Demonstrate direct OpenAI with reviewer-supplied backend key/model and no running proxy service; all preparation, reconciliation, audit, repair, and assessment calls must follow the selected configuration ([WP-19](19-long-document-rule-compilation.md)).

## Acceptance criteria

- [x] The packaged application boots with only documented prerequisites and dependencies.
- [x] Missing configuration leaves the UI available to explain the problem; periodic health checks incur no model inference.
- [ ] [A19](../evaluation.md#required-scenarios) completes the live upload-to-export path; fixture mode remains explicitly labeled.
- [ ] The command is called working only after this verification. WP-18 repeats it independently from a fresh checkout before release.

## Dependencies and references

Requires [WP-05](05-model-integration.md), [WP-12](12-http-source-api.md), [WP-13](13-staff-review-interface.md), [WP-14](14-assessment-exports.md), and [WP-15](15-ocr-input-limits.md). Follow the [reviewer launch contract](../implementation-plan.md#reviewer-launch-contract), [reviewer configuration](../model-provider.md#reviewer-configuration), and [local deployment boundary](../architecture.md#system-context-and-deployment-boundary). Hosted deployment is outside this package.
