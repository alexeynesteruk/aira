# Assessment execution and recovery

Staff receive a traceable outcome or a useful stopped state from the complete assessment pipeline. The integration owner connects validated stages in order and ensures that retries, clarification, and restarts preserve the original evidence.

**Work package:** [WP-11](../work-breakdown.md#wp-11-workflow-and-recovery). **Kind:** Feature. **Milestone:** M3. **Owner role:** Integration. **Status:** [Work breakdown](../work-breakdown.md#work-packages-and-dependencies).

## Business requirements

- [BR-009](../requirements/business-requirements.md#br-009-progress-and-useful-failure-recovery): show progress and actionable failures without claiming partial processing succeeded.
- [BR-003](../requirements/business-requirements.md#br-003-policy-applicability-gate): stop on mismatch or unresolved scope before necessity aggregation.
- [BR-005](../requirements/business-requirements.md#br-005-distinct-evidence-states) and [BR-007](../requirements/business-requirements.md#br-007-actionable-gaps-and-human-clarification): preserve uncertainty and support clarification without clinical overrides.

## Technical requirements

[TR-011](../requirements/technical-requirements.md#tr-011-bounded-execution-and-failure-lifecycle) requires separate status, phase, and outcome; bounded queue/concurrency/retries/deadlines; and interrupted-state recovery. [TR-016](../requirements/technical-requirements.md#tr-016-measurement-and-resource-budgets) requires timings, attempts, usage, and resource budgets. Reuse follows [TR-012](../requirements/technical-requirements.md#tr-012-storage-identity-and-cache-isolation). Validate each stage before downstream consumption.

## Implementation tasks

- [x] Connect extraction, scope, policy interpretation, evidence mapping, validation, and evaluation in `backend/app/assessment/`.
- [x] Persist phases separately from `queued`, `running`, `needs_input`, `completed`, `failed`, and `interrupted` status.
- [x] Implement bounded scheduling and provider failure handling without multiplying retry layers.
- [x] Mark unfinished work interrupted on restart; create a new `parent_run_id` attempt for retry/clarification using only compatible artifacts.

- [ ] Integrate standalone durable document builds, whole-build budgets, compatible section retry, and exact artifact pinning through [WP-19 LD-07–LD-08](19-long-document-rule-compilation.md); independent preparation precedes assessment scope/evidence mapping.

## Acceptance criteria

- [ ] A01 completes with cited `applicability_mismatch` and no necessity aggregate; uncertain scope stops in `needs_input`.
- [ ] A02–A05 preserve satisfied, missing, contrary, and conflicting findings. `completed` may still mean `review_required`.
- [ ] A16/A17 retain failure/restart history and enforce finite attempts. Metadata clarification preserves source conflicts; clinical changes require a new source.
- [ ] A20 blocks favorable readiness when governing conditions remain unresolved, even if extracted logic is true.

Checks use the [evaluation matrix](../evaluation.md#required-scenarios), including a live CLI vertical slice before UI completion. Controlled-interpreter evidence is in [results/workflow.md](../results/workflow.md); acceptance requires the live CLI vertical slice, which the deferred API quota blocks.

## Dependencies and references

Completion dependencies: [WP-06](../work-breakdown.md#wp-06-storage-and-identity), [WP-07](../work-breakdown.md#wp-07-request-context-and-applicability), [WP-08](../work-breakdown.md#wp-08-policy-interpretation-and-completeness), [WP-09](../work-breakdown.md#wp-09-evidence-mapping), [WP-10](../work-breakdown.md#wp-10-validation-and-evaluation-core), [WP-15](../work-breakdown.md#wp-15-ocr-and-input-envelope).

Design references: [run lifecycle](../architecture.md#request-and-run-lifecycle), [status/error contract](../requirements/technical-requirements.md#status-and-error-contracts), and [provider reliability](../model-provider.md#reliability-and-measurement).
