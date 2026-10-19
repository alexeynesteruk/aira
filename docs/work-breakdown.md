# Aira implementation work breakdown

This backlog decomposes the [implementation milestones](implementation-plan.md#implementation-sequence) into assignable changes. The [business requirements](requirements/business-requirements.md) define the staff outcome, the [technical requirements](requirements/technical-requirements.md) define testable system behavior, and the [architecture](architecture.md) defines component boundaries. Acceptance IDs refer to the existing [evaluation matrix](evaluation.md#required-scenarios).

The table below owns implementation status, dependencies, and responsibility. Individual [feature specifications](features/README.md) contain business/technical requirements, task checklists, deliverables, and acceptance details. As of October 18, 2026, WP-01–WP-04, WP-06, WP-10, WP-12, WP-13, and WP-14 are complete, and WP-07–WP-09, WP-11, and WP-15–WP-18 are in progress. WP-05 live model evaluation remains blocked by API project quota, deferred at the user’s request; every live-model or live-delivery acceptance gate stays open. An owner role indicates responsibility, not an assigned person. WP-19 runtime and controlled integration are implemented; live semantic/reviewer-release acceptance remains open. No delivery date or effort estimate is implied before the first feasibility results.

## Work packages and dependencies

Dependencies mean the evidence needed to finish a package. Exploratory implementation can start earlier against agreed fixtures, but cannot be marked complete on mocked integration alone. Shared schemas are versioned: WP-02 establishes the initial baseline; WP-04, WP-05, and WP-15 may require reviewed amendments before downstream integration.

| ID | Work package | Milestone | Owner role | Depends on | Technical requirements | Status |
| --- | --- | --- | --- | --- | --- | --- |
| WP-01 | [Repository foundation and executable checks](features/01-repository-foundation.md) | M0 | Integration | Current documentation | TR-017, TR-018 | Complete |
| WP-02 | [Domain and interface contract baseline](features/02-domain-contracts.md) | M0 | Backend/integration | WP-01 | TR-001–TR-015 | Complete |
| WP-03 | [Annotated fixtures and expected outcomes](features/03-evaluation-fixtures.md) | M0 | Evaluation | WP-02 | TR-017 | Complete |
| WP-04 | [Native PDF extraction experiment](features/04-pdf-ingestion-extraction.md) | M2 | Documents | WP-02, WP-03 | TR-001, TR-002 | Complete |
| WP-05 | [Model feasibility and OpenAI adapter](features/05-model-integration.md) | M1 | Model integration | WP-02, WP-03 | TR-010, TR-016 | Blocked |
| WP-06 | [Local storage and artifact identity](features/06-versioned-storage.md) | M3 | Backend | WP-02 | TR-012 | Complete |
| WP-07 | [Request context and applicability](features/07-request-applicability.md) | M3 | Domain | WP-04, WP-05, WP-10 | TR-004, TR-005 | In progress |
| WP-08 | [Policy requirements and completeness](features/08-policy-interpretation.md) | M3 | Domain | WP-04, WP-05, WP-10 | TR-006 | In progress |
| WP-09 | [Chart facts and criterion evidence](features/09-chart-evidence.md) | M3 | Domain | WP-04, WP-05, WP-10 | TR-007 | In progress |
| WP-10 | [Provenance validation and rule evaluator](features/10-rule-validation.md) | M3 | Domain | WP-02, WP-03 | TR-008, TR-009 | Complete |
| WP-11 | [Assessment workflow and recovery](features/11-assessment-workflow.md) | M3 | Integration | WP-06, WP-07, WP-08, WP-09, WP-10, WP-15 | TR-011, TR-016 | In progress |
| WP-12 | [HTTP and source inspection API](features/12-http-source-api.md) | M3–M4 | Backend | WP-04, WP-06, WP-11 | TR-013 | Complete |
| WP-13 | [Staff upload and review interface](features/13-staff-review-interface.md) | M4 | Frontend | WP-12 | TR-014 | Complete |
| WP-14 | [Traceable assessment exports](features/14-assessment-exports.md) | M4 | Backend/frontend | WP-11, WP-12 | TR-015 | Complete |
| WP-15 | [OCR decision and supported input limits](features/15-ocr-input-limits.md) | M2 | Documents/model integration | WP-03, WP-04, WP-05 | TR-003, TR-016 | In progress |
| WP-16 | [Integrated evaluation and regression checks](features/16-evaluation-regression.md) | M5 | Evaluation/integration | WP-13, WP-14, WP-15, WP-19 | TR-017 | In progress |
| WP-17 | [Reviewer setup](features/17-reviewer-packaging.md) | M6 | Integration | WP-05, WP-12, WP-13, WP-14, WP-15 | TR-010, TR-018 | In progress |
| WP-18 | [Release verification and design note](features/18-release-handoff.md) | M6 | Integration | WP-16, WP-17 | TR-017, TR-018 | In progress |
| WP-19 | [Long-document rule-set compilation](features/19-long-document-rule-compilation.md) | M2–M6 | Integration | WP-03, WP-04, WP-05, WP-06, WP-10, WP-15 | TR-006, TR-007, TR-010–TR-019 | In progress |

WP-07, WP-08, and WP-09 can be developed independently using the request, policy, and evidence contracts from WP-02 and annotated examples from WP-03. Their runtime order is enforced by WP-11: save the whole-guideline rule set and the chart facts independently, then check applicability, then map evidence onto the saved fact IDs. A guideline extraction does not receive the chart, and a chart extraction does not receive the guideline. Changing the request or an annotation repeats only the assessment.

```mermaid
flowchart LR
    W1[WP-01 Foundation] --> W2[WP-02 Contracts]
    W2 --> W3[WP-03 Fixtures]
    W2 --> W6[WP-06 Storage]
    W3 --> W4[WP-04 Native PDF]
    W3 --> W5[WP-05 Model]
    W3 --> W10[WP-10 Validation and rules]
    W4 --> D[WP-07 to WP-09 Domain stages]
    W5 --> D
    W10 --> D
    W6 --> W11[WP-11 Workflow]
    D --> W11
    W11 --> W12[WP-12 API]
    W12 --> W13[WP-13 UI]
    W12 --> W14[WP-14 Exports]
    W4 --> W15[WP-15 OCR and input limits]
    W5 --> W15
    W15 --> W11
    W13 --> W16[WP-16 Evaluation]
    W14 --> W16
    W15 --> W16
    W13 --> W17[WP-17 Packaging]
    W14 --> W17
    W15 --> W17
    W16 --> W18[WP-18 Release evidence]
    W17 --> W18
    W3 --> W19[WP-19 Long-document compilation]
    W4 --> W19
    W5 --> W19
    W6 --> W19
    W10 --> W19
    W15 --> W19
    W19 --> W16
```

The diagram summarizes the flow; the dependency table is authoritative. The principal integration path is contracts and fixtures → validated parser/provider/domain stages → workflow/API → staff review → release evidence. Storage, pure rules, and the native-text input-limit decision can progress alongside that path. Final delivery requires both evaluated behavior and a clean packaged launch.

## Package definitions

The detailed scope and execution checklists live in the linked feature files. These anchors preserve package references from requirements and design documents.

### WP-01 Repository foundation

[Feature specification and implementation checklist](features/01-repository-foundation.md).

### WP-02 Domain and interface contracts

[Feature specification and implementation checklist](features/02-domain-contracts.md).

### WP-03 Annotated fixtures and evaluation expectations

[Feature specification and implementation checklist](features/03-evaluation-fixtures.md).

### WP-04 Native PDF extraction

[Feature specification and implementation checklist](features/04-pdf-ingestion-extraction.md).

### WP-05 Model experiment and adapter

[Feature specification and implementation checklist](features/05-model-integration.md).

### WP-06 Storage and identity

[Feature specification and implementation checklist](features/06-versioned-storage.md).

### WP-07 Request context and applicability

[Feature specification and implementation checklist](features/07-request-applicability.md).

### WP-08 Policy interpretation and completeness

[Feature specification and implementation checklist](features/08-policy-interpretation.md).

### WP-09 Evidence mapping

[Feature specification and implementation checklist](features/09-chart-evidence.md).

### WP-10 Validation and evaluation core

[Feature specification and implementation checklist](features/10-rule-validation.md).

### WP-11 Workflow and recovery

[Feature specification and implementation checklist](features/11-assessment-workflow.md).

### WP-12 HTTP and source API

[Feature specification and implementation checklist](features/12-http-source-api.md).

### WP-13 Staff interface

[Feature specification and implementation checklist](features/13-staff-review-interface.md).

### WP-14 Exports

[Feature specification and implementation checklist](features/14-assessment-exports.md).

### WP-15 OCR and input envelope

[Feature specification and implementation checklist](features/15-ocr-input-limits.md).

### WP-16 Integrated regression and evaluation

[Feature specification and implementation checklist](features/16-evaluation-regression.md).

### WP-17 Packaging and reviewer setup

[Feature specification and implementation checklist](features/17-reviewer-packaging.md).

### WP-18 Release evidence and handoff

Design-note draft (`docs/design-note.md`); live release checks remain open.

[Feature specification and implementation checklist](features/18-release-handoff.md).

### WP-19 Long-document rule-set compilation

[Feature/acceptance](features/19-long-document-rule-compilation.md), [execution plan](plans/long-document-rule-compilation.md), and [implementation evidence](results/wp19-implementation.md). The independent build service, full-source section interpretation, bounded group/scope reconciliation, coverage audit/compiler, durable checkpoints, exact assessment pins, API/CLI, preparation/review/retry UI, and explicit backend routing are implemented and controlled-tested.

| Tasks | Evidence/status |
| --- | --- |
| LD-01 | 100/200-page fictional PDFs and independent rule/path gold manifests. Held-out insurer/table/footnote semantic annotation remains open. |
| LD-02–LD-08 | Runtime delivered with source/graph negative controls, controlled SDK routing, persistence/recovery, independent reuse, API and saved browser journeys. See result record for commands and conservative exception handling. |
| LD-09 | Deterministic integration recorded; live rule/edge/exception recall, entailment, repeatability, and calibrated limits remain open under deferred quota. |
| LD-10 | CLI/local launch preserved and limits documented; clean-checkout live direct-OpenAI demonstration remains open. |

WP-19 stays **in progress** until live/release evidence closes LD-09/LD-10. Scripted outcomes and mechanical coverage cannot establish assessment accuracy. WP-08/WP-09/WP-11–WP-14 foundations are integrated; WP-16/WP-18 release checks still require A21.

## Integration and completion rules

Use `Not started`, `In progress`, `Blocked`, or `Complete` in the status column, with a concrete reason for blocked work. Each package should fit a focused change or a small series of reviewable changes. Its completion record identifies the owner, implementing commit, requirements covered, checks run, observed results, and remaining limitations. Use actual evidence before changing status; the records below distinguish completed packages from unfinished integration and live validation.

Assign one owner to shared schemas and API examples. Document/provider/storage work can proceed in parallel after the contract baseline. Policy, evidence, and applicability work must use the same versions. Run integration checks after merging; branch-level green checks do not prove a working product.

Start with WP-01–WP-03, then run WP-04 and WP-05 alongside the pure validation/storage work. Resolve native-text input limits and explicit scan rejection in parallel. Demonstrate the CLI vertical slice before expanding the review UI. Keep hosting, policy discovery, queues, retrieval infrastructure, and payer submission out of these packages unless a documented requirement changes.

## Implementation evidence

| Package | Implementing commit and verification | Remaining boundary |
| --- | --- | --- |
| WP-01 | `f42b670`. FastAPI/React shell, pinned toolchains, lint/type/tests/build, and browser checks. A deliberate TypeScript error was rejected locally. | The one-line launcher serves the full UI/API; the live upload-to-export check is WP-17's remaining gate. |
| WP-02 | `28da09e`. Versioned records, 45 contract checks, [contract documentation](contracts.md). Integration owner maintains shared schemas. | Provider schema compatibility and domain interpretation need live verification. |
| WP-03 | `eff3124`, extended by `433bb1c`. 23 corpus checks and [independent source review](reviews/wp03-fixtures.md). The follow-up adds the rendered development PDFs (`examples/synthetic/`), manifest, integrity checks, and the FT-01 construction-ledger update. | These are text fixtures and reviewed expectations, not a semantic benchmark. The reserved pair is not claimed blind; final release inputs still need independent curation. |
| WP-04 | `16363a7`; [extraction record](results/pdf-extraction.md), 34 integration checks on the supplied chart and both guideline snapshots. | Persistence/workflow use is in WP-06/WP-11; the measured model envelope is in WP-15. |
| WP-05 | Blocked: the adapter and isolated-stage CLI are implemented (`829f330`) and the [provider experiment record](results/model-feasibility.md) separates controlled checks from the observed quota failure, but live structured output, model comparison, and timing need API project quota, which the user deferred on October 18. | No tested model selection or live stage output exists. |
| WP-06 | `be4450b`; [storage record](results/storage.md), 30 integration checks on real SQLite/filesystem state. | Workflow integration is in WP-11. |
| WP-07–WP-09 | Candidate conversion in `app.policies` with 62 checks (`e73056b`, extended with multi-procedure and conflict-resolution checks) and the production `app.llm.interpreter.OpenAIStageInterpreter` wiring adapter/prompts to conversion with 12 mocked-transport checks (`879dbde`; [stage interpreter record](results/stage-interpreter.md)). The long-document path routes section candidates through the same conversion. | Live semantic checks remain blocked by the deferred quota; the annotated fixture and comparison tasks are open. |
| WP-10 | `f461391`; [rules record](results/rules.md), 140 pure validation/evaluation checks. | Semantic evaluation is in WP-16. |
| WP-11 | Engine and rendered-input checks in `e73056b` and `b549e88`; the production stage interpreter landed in `879dbde`; application startup wiring landed in `aa1dcb5`. | [workflow record](results/workflow.md); the live run remains quota-blocked. |
| WP-12 | `aa1dcb5`, extended by `a628439` for typed OpenAPI and persisted provider verification; [HTTP API record](results/http-api.md), 19 API checks plus 3 health checks over the real lifespan, store, and engine. | The staff review UI in WP-13 is the consumer. |
| WP-13 | `e397e31`, extended by `a628439` for contrary/satisfied journeys plus the OR-path, failed-page, and verification-state work; [review UI record](results/review-ui.md), 9 saved fixture journeys plus 26 frontend checks. | WP-16 live parity remains open. |
| WP-14 | Markdown export renderer in `app.assessment.export` with 5 checks (`e73056b`); export routes in `app.api` proven for JSON/Markdown, state conflicts, and cross-run stability (`aa1dcb5`); UI downloads verified against filenames and persisted content (`e397e31`); evaluation-path lines added in `a628439`. | WP-16 UI parity against live runs remains the open boundary. |
| WP-15 | Declared boundary and limit evidence in [input limits record](results/input-limits.md); parser byte/page/character limits and intake rejection classes verified at API level in [results/http-api.md](results/http-api.md) and [results/pdf-extraction.md](results/pdf-extraction.md). | The parser-plus-model token envelope needs live calls and stays open under the deferred quota. |
| WP-16 | Deterministic checks are the local `make check` and `make browser-test` targets; controlled-interpreter and fixture-interpreter checks exercise failure, interruption, annotation conflict, cache invalidation, source navigation, and export parity. Tasks FT-07 (runtime SourceSpan counterexamples and semantic irrelevance), FT-13 (long-chart distractor recall, prompt-injection resistance, and explicit input limits), and FT-14 (multiple-procedure conflict resolution and parent-run linkage) are closed with dedicated unit and integration tests. A follow-up commit (`433bb1c`) renders the development corpus to native-text PDFs (FT-01) and updates the construction ledger. | The live semantic evaluation report, release-corpus expectations, and the live A19 run remain open under deferred provider quota. |
| WP-17 | Reviewer setup is the one-line launcher. `scripts/launch.sh` was verified on a clean checkout on October 18: it installed locked dependencies, built the UI, served liveness/readiness and the app on port 8000, and ran a real upload-to-provider run against the supplied BCBS guideline and chart (all 21 pages extracted; the run failed `throttled` at `checking_applicability`). Persisted preflight verification plus `AIRA_MAX_OUTPUT_TOKENS` landed in `a628439`. | The live upload-to-export check (A19) remains open until quota is restored. |

Repository history was rewritten with `filter-branch` after the original package commits; every hash above is verified reachable from `main`. Earlier `actions/runs` links were removed because they pointed at orphaned pre-rewrite commits. Verification is now the local `make check` and `make browser-test` targets; there is no hosted CI.

[WP-19 specification record](results/wp19-specification.md) preserves the earlier documentation/baseline check findings. The [October 19 implementation record](results/wp19-implementation.md) records the delivered runtime and green integrated checks; live release acceptance stays open.

## Independent extraction follow-up (October 18)

Guideline and chart preparation are separate document builds. Assessment reads those saved artifacts plus the selected request and staff annotations, checks applicability first, and maps requirements only to saved fact IDs. Re-checked on this working tree at 2026-10-19: `make check` exited 0 (517 pytest, including 9 document-build tests, and 26 Vitest) and `make browser-test` exited 0 (14 passed). Details are in [independent extraction](results/independent-extraction.md). WP-08, WP-09, and WP-11 stay in progress because live semantic acceptance is still quota-deferred. These fixture results are not live-model validation.
