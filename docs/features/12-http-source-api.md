# HTTP assessment and source API

The frontend and reviewers receive a stable interface for uploads, run progress, results, and original evidence. The backend owner exposes domain behavior without making an HTTP request wait for full extraction or model execution.

**Work package:** [WP-12](../work-breakdown.md#wp-12-http-and-source-api). **Kind:** Enabler. **Milestone:** M3–M4. **Owner role:** Backend. **Status:** [Work breakdown](../work-breakdown.md#work-packages-and-dependencies).

## Business requirements

- [BR-001](../requirements/business-requirements.md#br-001-new-guideline-and-chart-uploads): accept policy/chart inputs through the application.
- [BR-006](../requirements/business-requirements.md#br-006-inspectable-policy-and-chart-citations) and [BR-008](../requirements/business-requirements.md#br-008-saved-assessments-and-versioned-exports): expose saved runs and their exact source pages.
- [BR-009](../requirements/business-requirements.md#br-009-progress-and-useful-failure-recovery): report usable errors, progress, and operational failures separately from findings.

## Technical requirements

[TR-013](../requirements/technical-requirements.md#tr-013-http-and-health-contracts) and the [HTTP contract](../requirements/technical-requirements.md#http-interface-contracts) define typed routes, status codes, source revision selection, and health behavior. [TR-001](../requirements/technical-requirements.md#tr-001-pdf-intake-and-page-inventory) permits bounded local format/page-count checks at intake. Full extraction and model work run asynchronously after assessment creation. Liveness checks the process; readiness checks local dependencies/configuration without paid inference or a promise of verified model access.

## Implementation tasks

- [ ] Implement upload, document metadata/original/page, assessment creation/status, and health routes in `backend/app/api/`.
- [ ] Validate document roles, IDs, revisions, request context, and optional `parent_run_id` before queuing.
- [ ] Return `202` with run ID/status URL promptly; expose persisted failures through status polling.
- [ ] Generate API documentation and boundary tests. Export generation/routes are implemented by WP-14 against the same contract.

## Acceptance criteria

- [ ] A14 distinguishes unsupported type, malformed PDF, and configured limits without silent truncation.
- [ ] A12/A15 reject wrong roles/IDs/revisions; one-based page access returns the original run's evidence.
- [ ] A16 returns specified queue/configuration errors; a known failed run still polls successfully with `status=failed`.
- [ ] A19 source inspection works, and repeated health checks make no model calls. The UI remains available to explain missing configuration.

Checks follow the [evaluation matrix](../evaluation.md#required-scenarios) and [error envelope](../requirements/technical-requirements.md#status-and-error-contracts).

## Dependencies and references

Completion dependencies: [WP-04](../work-breakdown.md#wp-04-native-pdf-extraction), [WP-06](../work-breakdown.md#wp-06-storage-and-identity), [WP-11](../work-breakdown.md#wp-11-workflow-and-recovery).

Design references: [component boundaries](../architecture.md#components-and-dependency-direction), [request lifecycle](../architecture.md#request-and-run-lifecycle), and [reviewer configuration](../model-provider.md#reviewer-configuration).
