# Container packaging and reviewer setup

Let an assessor start the application and process new PDFs with a documented command and explicit AWS prerequisites, using a fresh checkout on their machine.

Work package: [WP-17](../work-breakdown.md#wp-17-packaging-and-reviewer-setup). Kind: delivery enabler. Milestone: M6. Owner role: Integration. Implementation status and ownership are tracked in the [work breakdown](../work-breakdown.md#work-packages-and-dependencies).

## Business requirements

- [BR-010](../requirements/business-requirements.md#br-010-one-command-live-reviewer-workflow): provide the real local workflow without the author's private services or registry.
- [BR-001](../requirements/business-requirements.md#br-001-new-guideline-and-chart-uploads): preserve live processing of unfamiliar documents rather than a canned demonstration.
- [BR-012](../requirements/business-requirements.md#br-012-submission-and-design-discussion): supply truthful run instructions and setup limitations for the handoff.

## Technical requirements

- [TR-010](../requirements/technical-requirements.md#tr-010-bedrock-contract-and-configuration): forward documented credentials, including temporary session tokens, and validate model/region configuration without subscription changes.
- [TR-018](../requirements/technical-requirements.md#tr-018-packaging-and-reviewer-delivery): package built React assets, FastAPI, locked dependencies, and parser tools in one application image with a persistent volume and documented port.

## Implementation tasks

- [ ] Add `Dockerfile`, `compose.yaml`, and `.env.example` without secrets.
- [ ] Implement the target `docker compose up --build` launch and persistent data directory.
- [ ] Document Docker, AWS model access, credentials, region/model, OCR choice, input limits, and first-run behavior.
- [ ] Verify credentials inside the container and ensure setup failures remain understandable in the UI.
- [ ] Exercise a new upload, source inspection, and export through live inference.

## Acceptance criteria

- [ ] The packaged application boots with only documented prerequisites and dependencies.
- [ ] Missing configuration leaves the UI available to explain the problem; periodic health checks incur no model inference.
- [ ] [A19](../evaluation.md#required-scenarios) completes the live upload-to-export path; fixture mode remains explicitly labeled.
- [ ] The command is called working only after this verification. WP-18 repeats it independently from a fresh checkout before release.

## Dependencies and references

Requires [WP-05](05-bedrock-integration.md), [WP-12](12-http-source-api.md), [WP-13](13-staff-review-interface.md), [WP-14](14-assessment-exports.md), and [WP-15](15-ocr-input-limits.md). Follow the [reviewer launch contract](../implementation-plan.md#reviewer-launch-contract), [AWS credential guidance](../aws.md#reviewer-credentials-and-configuration), and [local deployment boundary](../architecture.md#system-context-and-deployment-boundary). Hosted deployment is outside this package.
