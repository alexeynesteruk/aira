# Long-document rule-set compilation

Build a durable, inspectable rule set from an entire insurer guideline using bounded section extraction and cross-section reconciliation. Staff can prepare the guideline once and reuse it for subsequent patient assessments.

**Work package:** WP-19. **Kind:** Product feature and processing enabler. **Milestones:** M2, M3, M5, M6. **Owner:** Integration, coordinating document, domain, storage, model, UI, and evaluation changes. **Status:** [Work breakdown](../work-breakdown.md#work-packages-and-dependencies).

## Requirements and scope

- [BR-013](../requirements/business-requirements.md#br-013-long-guideline-preparation-and-reuse): complete guideline preparation with visible coverage, durable reuse, and useful recovery.
- [TR-019](../requirements/technical-requirements.md#tr-019-long-document-rule-set-compilation): bounded structure-aware extraction, dependency resolution, coverage audit, and compilation.
- BR-001/BR-004/BR-006/BR-008/BR-009 and TR-002/TR-006/TR-008/TR-009/TR-011/TR-012/TR-014/TR-016/TR-017 govern sources, semantics, storage, failure handling, UI, and evaluation.
- TR-007 preserves independent chart facts; TR-010/TR-018 require direct OpenAI configuration and a portable reviewer workflow.

The target includes 100- and 200-page native-text guideline cases. Controlled real-PDF builds cover this envelope; live model semantic acceptance remains open. OCR has its own declared boundary. Prepare a guideline without requiring a chart; prepare chart facts independently; combine saved artifacts only during assessment.

Exclude automatic external-policy discovery, payer submission, new infrastructure services, a universal policy language, and unbounded autonomous processing. Referenced material absent from the upload becomes a visible dependency gap rather than an invented rule or an automatic web lookup.

## Staff behavior

1. Upload a guideline, start preparation, and see extraction/build progress by real stages and completed sections.
2. Inspect the guideline inventory, source-linked rules, unresolved dependencies, and coverage report. A technically validated draft is distinct from a human-approved artifact.
3. Assess patients using that saved rule-set version. New patients, request metadata, and annotations do not rebuild it.
4. Inspect a failed build, retry in a new linked attempt using compatible completed section artifacts, or explicitly rebuild a new version. Earlier results remain unchanged.
5. Use a backend OpenAI API key and explicit model directly; optionally configure a LiteLLM endpoint. Display active backend/model and configuration errors without revealing secrets.

## Task breakdown

The [implementation record](../results/wp19-implementation.md) maps delivered runtime, the controlled corpus, and open release work. Task exit evidence still governs completion. Their execution order and proposed contracts are in the [implementation plan](../plans/long-document-rule-compilation.md).

| Task | Deliverable | Depends on | Exit evidence |
| --- | --- | --- | --- |
| LD-01 | Freeze independent source annotations and 100/200-page fixture construction manifests; record baseline limits and prototype gaps. | WP-03, WP-04 | Hash-pinned section/rule/dependency expectations and meaningful failing controls. |
| LD-02 | Versioned block/section, build, coverage, and rule-set contracts; API/CLI and schema compatibility amendments. | LD-01, WP-02 | Strict contract tests, migration/rejection behavior, approved endpoint definitions. |
| LD-03 | Layout-aware section planner with token/output budgets, complete source ledger, and stable source identities. | LD-02, WP-04 | No lost text, split list, detached table header, or uncovered section; oversized atomic units fail explicitly. |
| LD-04 | Guideline-only inventory and bounded contextual section extractor with validated immutable local outputs. | LD-03, WP-05 | Controlled transport assertions prove isolated inputs, bounded fan-out, valid spans, and complete output handling. |
| LD-05 | Explicit definition/reference resolution and hierarchical record reconciliation without rewriting the whole rule set per page. | LD-04, WP-10 | Remote exceptions/definitions bind correctly; ambiguity, cycles, conflicts, and missing material remain visible. |
| LD-06 | Coverage audit and deterministic compiler for scoped rule paths, with review blockers and source-to-rule mapping. | LD-05 | Known omissions block satisfaction; JSON/graph validity is tested separately from annotated source fidelity. |
| LD-07 | Atomic intermediate/final storage, stage-specific reuse keys, build budgets, single-flight execution, and linked retry/rebuild. | LD-02, LD-04, LD-06, WP-06 | Restart, simultaneous builds, corruption, rejection, configuration changes, and dependency invalidation are verified. |
| LD-08 | Standalone preparation, progress/review/retry UI, exact artifact pinning in assessments/exports, and complete provider routing. | LD-07, WP-12, WP-13, WP-14 | Saved browser journeys and controlled direct-OpenAI/LiteLLM adapter checks. |
| LD-09 | Integrated deterministic and live evaluation over the reviewed long-document corpus and two policy families. | LD-08, WP-15 | A21 evidence with counts/errors, rule and edge recall, timings, attempts, tokens, and limitations. |
| LD-10 | Clean-checkout direct-OpenAI demonstration, input-limit publication, design note, and completion record. | LD-09, WP-17 | Live upload/build/reuse/assessment/source/export evidence; no local gateway dependency. |

## Acceptance checks

All checks map to [A21 and existing scenarios](../evaluation.md). Record actual results by revision; live-dependent checks remain open until executed.

| Check | Required observation |
| --- | --- |
| LD-AC01 | Both 100- and 200-page native-text guidelines pass intake and produce complete, bounded builds on the declared configuration. Each page/section is accounted for; overruns never truncate content. |
| LD-AC02 | A compound condition split across pages retains its grouping, introductory scope, and citations. A distant definition, footnote, and exception retain their governing relationships. |
| LD-AC03 | Every source section maps to requirements, definitions/context, explicitly non-normative content, or unresolved interpretation with rationale. A short excerpt or relevance score alone cannot authorize skipping the section. |
| LD-AC04 | Two procedures with different requirements cannot satisfy each other. Unsupported conditionals, unresolved references, and incompatible versions block the affected path. |
| LD-AC05 | Second-patient, changed-request, duplicate-upload, restart, and changed-guideline scenarios reuse the appropriate policy/chart artifacts and retain correct original-source citations. |
| LD-AC06 | Changing a global definition invalidates dependent reconciliation/compiled artifacts; changing an assessment prompt does not rebuild guideline extraction. Each reused artifact retains its actual generation configuration. |
| LD-AC07 | Failed/refused/truncated/invalid section work, process interruption, and budget exhaustion preserve diagnostics and completed intermediate work. No incomplete final rule set is published as ready or approved. |
| LD-AC08 | Concurrent identical requests coalesce into one active build. Retry/rebuild preserves lineage and immutable prior outputs; exactly-once remote billing is not promised. |
| LD-AC09 | Controlled negative tests reject fabricated source spans, logical-edge mutations, injected document instructions, lost mandatory conditions, and assessment attempts to introduce facts. |
| LD-AC10 | The reviewer can prepare the guideline with no chart, inspect real progress/coverage/issues, select a saved version, retry a failed build, and inspect matching UI/export source identities. |
| LD-AC11 | Every inference operation uses the selected backend, including inventory, extraction, reference repair, audit, assessment, and explicit preflight. Direct OpenAI works with backend-only key/model configuration and no running LiteLLM service. |
| LD-AC12 | Independent live evaluation reports source fidelity and repeatability separately from deterministic test success. No expected outcome is rewritten to agree with generated rules. |

## Evidence and dependencies

Completion depends on WP-03/WP-04/WP-05/WP-06/WP-10/WP-15 and integration with WP-11–WP-14/WP-17. WP-16/WP-18 must include this feature's release evidence. The work breakdown is authoritative; avoid a circular dependency by treating existing package artifacts as inputs and their expanded long-document acceptance as follow-up integration.

Use the [research log](../research/long-document-rule-extraction.md) for observed source claims and the [implementation plan](../plans/long-document-rule-compilation.md) for contracts, execution, failure semantics, and verification. Do not treat the page-fold prototype or planning documents as proof of completion.

The [specification/check record](../results/wp19-specification.md) records documentation delivery and current baseline failures. Current runtime/check evidence is in the [October 19 implementation record](../results/wp19-implementation.md).
