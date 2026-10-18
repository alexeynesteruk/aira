# Aira implementation work breakdown

This backlog decomposes the [implementation milestones](implementation-plan.md#implementation-sequence) into assignable changes. The [business requirements](requirements/business-requirements.md) define the staff outcome, the [technical requirements](requirements/technical-requirements.md) define testable system behavior, and the [architecture](architecture.md) defines component boundaries. Acceptance IDs refer to the existing [evaluation matrix](evaluation.md#required-scenarios).

The table below owns implementation status, dependencies, and responsibility. Individual [feature specifications](features/README.md) contain business/technical requirements, task checklists, deliverables, and acceptance details. As of October 18, 2026, WP-01–WP-04, WP-06, and WP-10 are implemented; WP-01–WP-03 have implementing commits with successful GitHub Actions runs, and WP-04/WP-06/WP-10 await their integrating commits. Candidate conversion for WP-07–WP-09, the WP-11 workflow engine, the WP-14 export renderer, and WP-17 packaging are in progress. WP-05 live model evaluation is blocked by API project quota and deferred at the user’s request. An owner role indicates responsibility, not an assigned person. No delivery date or effort estimate is implied before the first feasibility results.

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
| WP-12 | [HTTP and source inspection API](features/12-http-source-api.md) | M3–M4 | Backend | WP-04, WP-06, WP-11 | TR-013 | Not started |
| WP-13 | [Staff upload and review interface](features/13-staff-review-interface.md) | M4 | Frontend | WP-12 | TR-014 | Not started |
| WP-14 | [Traceable assessment exports](features/14-assessment-exports.md) | M4 | Backend/frontend | WP-11, WP-12 | TR-015 | In progress |
| WP-15 | [OCR decision and supported input limits](features/15-ocr-input-limits.md) | M2 | Documents/model integration | WP-03, WP-04, WP-05 | TR-003, TR-016 | Not started |
| WP-16 | [Integrated evaluation and regression checks](features/16-evaluation-regression.md) | M5 | Evaluation/integration | WP-13, WP-14, WP-15 | TR-017 | Not started |
| WP-17 | [Container packaging and reviewer setup](features/17-reviewer-packaging.md) | M6 | Integration | WP-05, WP-12, WP-13, WP-14, WP-15 | TR-010, TR-018 | In progress |
| WP-18 | [Release verification and design note](features/18-release-handoff.md) | M6 | Integration | WP-16, WP-17 | TR-017, TR-018 | Not started |

WP-07, WP-08, and WP-09 can be developed independently using the request, policy, and evidence contracts from WP-02 and annotated examples from WP-03. Their runtime order is enforced by WP-11: scope first, then policy interpretation, then evidence mapping. A chart-only extraction test can inspect the supplied chronology even though its end-to-end pair stops at mismatch.

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

[Feature specification and implementation checklist](features/18-release-handoff.md).

## Integration and completion rules

Use `Not started`, `In progress`, `Blocked`, or `Complete` in the status column, with a concrete reason for blocked work. Each package should fit a focused change or a small series of reviewable changes. Its completion record identifies the owner, implementing commit, requirements covered, checks run, observed results, and remaining limitations. Use actual evidence before changing status; the records below distinguish completed packages from unfinished integration and live validation.

Assign one owner to shared schemas and API examples. Document/provider/storage work can proceed in parallel after the contract baseline. Policy, evidence, and applicability work must use the same versions. Run integration checks after merging; branch-level green checks do not prove a working product.

Start with WP-01–WP-03, then run WP-04 and WP-05 alongside the pure validation/storage work. Resolve native-text input limits and explicit scan rejection in parallel. Demonstrate the CLI vertical slice before expanding the review UI. Keep hosting, policy discovery, queues, retrieval infrastructure, and payer submission out of these packages unless a documented requirement changes.

## Implementation evidence

| Package | Implementing commit and verification | Remaining boundary |
| --- | --- | --- |
| WP-01 | `f42b670`; [successful Actions run](https://github.com/alexeynesteruk/aira/actions/runs/39071755373). FastAPI/React shell, pinned toolchains, lint/type/tests/build, Docker and browser gates, checksummed image delivery. A deliberate TypeScript error was rejected locally. | The delivered image serves the shell; it does not yet process assessments. |
| WP-02 | `28da09e`; [successful Actions run](https://github.com/alexeynesteruk/aira/actions/runs/39072343066). Versioned records, 45 contract checks, [contract documentation](contracts.md). Integration owner maintains shared schemas. | Provider schema compatibility and domain interpretation need live verification. |
| WP-03 | `eff3124`; [successful Actions run](https://github.com/alexeynesteruk/aira/actions/runs/39072616016). 23 corpus checks and [independent source review](reviews/wp03-fixtures.md). | These are text fixtures and reviewed expectations, not a semantic benchmark. The reserved pair is not claimed blind; final release inputs still need independent curation. |
| WP-04 | Implementing commit pending; [extraction record](results/pdf-extraction.md), 34 integration checks on the supplied chart and both guideline snapshots. | Persistence/workflow use in WP-06/WP-11 and the measured model envelope in WP-15. |
| WP-05 | Blocked: the adapter and isolated-stage CLI are implemented and the [provider experiment record](results/model-feasibility.md) separates controlled checks from the observed quota failure, but live structured output, model comparison, and timing need API project quota, which the user deferred on October 18. | No tested model selection or live stage output exists. |
| WP-06 | Implementing commit pending; [storage record](results/storage.md), 30 integration checks on real SQLite/filesystem state. | Workflow integration in WP-11. |
| WP-07–WP-09 | Implementing commit pending; candidate conversion in `app.policies` with 52 checks in `tests/unit/test_candidate_conversion.py`. | The runtime interpreter behind the stage boundary and live semantic checks remain open. |
| WP-10 | Implementing commit pending; [rules record](results/rules.md), 140 pure validation/evaluation checks. | Semantic evaluation in WP-16. |
| WP-11 | Implementing commit pending; [workflow record](results/workflow.md), 15 controlled-interpreter integration checks plus 9 rendered-input checks over the real engine, parser, and store. | The OpenAI stage interpreter, application startup wiring, HTTP admission, and the live CLI vertical slice remain open. |
| WP-14 | Implementing commit pending; Markdown export renderer in `app.assessment.export` with 4 checks in `tests/unit/test_exports.py`. | Export routes and UI parity remain open. |
| WP-17 | Early container build/delivery checks are part of WP-01 and run on every main push. | Full reviewer upload-to-export workflow and live container access remain unimplemented/unverified. |
