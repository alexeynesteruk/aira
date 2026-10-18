# WP-19 specification and research record

October 18, 2026. This record covers the documentation task requested by the user: log research findings, create a dedicated feature, amend business/technical requirements, break the feature into implementation tasks, and provide an implementable plan. It does not mark the runtime feature complete.

## Delivered specification

- [Research log](../research/long-document-rule-extraction.md): inspected primary sources, dated observations, project inferences, limitations, and experiments still needed.
- [WP-19 feature](../features/19-long-document-rule-compilation.md): scope, staff behavior, LD-01–LD-10 tasks, dependencies, and LD-AC01–LD-AC12 acceptance checks.
- [Implementation plan](../plans/long-document-rule-compilation.md): target contracts, source/section planning, contextual extraction, dependency reconciliation, coverage audit, compilation, persistence/invalidation, budgets, UI/provider integration, and delivery sequence.
- BR-013, TR-019, and A21 added without renumbering earlier requirements; related architecture, provider, decision, feature, index, handoff, and backlog documents updated.

Direct OpenAI using a reviewer-provided backend key/model is a required path. LiteLLM is optional. Independent guideline/chart preparation and immutable reuse are prerequisites to assessment; unsupported semantics and incomplete operational work retain distinct states. The 100/200-page envelope remains an acceptance target until measured.

## Observed checks

Checks ran against an unfinished working tree, not an isolated release candidate. HEAD observed after the checks was `433bb1c`; other uncommitted application changes were present. No application code or test expectations were changed as part of this documentation task.

| Check | Observed result |
| --- | --- |
| Local Markdown link validation | Final pass: 715 local file links across 49 Markdown files resolved. New-document anchor targets, 10 task rows, 12 acceptance rows, and unique BR/TR/AD/TD/A identifiers passed validation. |
| `make check` | Failed at the initial backend Ruff step with 18 errors, including import ordering, long lines, and a duplicate `chart` method in test support. Later aggregate checks did not execute. |
| `make browser-test` | Frontend build passed. Saved browser execution: 11 passed, 1 failed. The extraction-failure journey expected native-text rejection/`extraction_failed`; it received `citation_invalid` during policy interpretation. |
| `git diff --check` | Passed after documentation edits. |

These failures belong to the current application integration boundary and must be resolved by implementation work. Do not change expected outcomes merely to make them green. Historical CI/component counts do not certify the new feature or the current working tree.

No new live model evaluation, direct-OpenAI smoke test, 100/200-page build, clinical accuracy result, or clean-checkout release verification was performed by this task. Preserve the existing quota deferral and record later controlled versus live evidence separately. The [work breakdown](../work-breakdown.md#wp-19-long-document-rule-set-compilation) remains the status authority.
