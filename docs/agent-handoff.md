# Implementation handoff for coding agents

Continue the existing implementation from the current work package. The product, stack, requirement IDs, and milestone sequence are established. Use this page to find the right contract and next executable task; use the work breakdown for current status.

## Read before editing

1. Read repository `AGENTS.md`, then the [BRD](requirements/business-requirements.md), [TRD](requirements/technical-requirements.md), [TDD](architecture.md), and [evaluation contract](evaluation.md).
2. Find the package in the [work breakdown](work-breakdown.md#work-packages-and-dependencies); its dependency table supplies order between packages. Read the package's feature file for its task and acceptance checklists, and any existing result record.
3. Inspect the actual files and `git status --short`. A file present in an active working tree can still be unfinished. Check the recorded test result and implementing commit before treating it as a completed dependency.
4. Select one bounded execution step. Confirm file ownership with the integration owner when another agent is active. Shared schemas, manifests, lockfiles, HTTP contracts, and status records have one integration owner.
5. Implement the step and its behavioral checks. Run the feature-specific command, inspect the diff, then run the required merged checks before completing a package.

The feature files supply the task and acceptance checklists; the work-breakdown dependency table supplies order between packages. Choose one bounded change, name the feature-file tasks it satisfies, and do not introduce a second status ledger.

## Current boundaries

| Boundary | Existing contract to consume | Next integration responsibility |
| --- | --- | --- |
| PDF intake and extraction | `app.documents.inspect_pdf`, `extract_pdf`, `require_usable_extraction`, `source_span`; [verified limits](results/pdf-extraction.md). | Persist original bytes and extraction revisions. Call the complete-input gate before every interpretation path, including cache reuse. |
| Domain records | Public types in `app.schemas`; [contract notes and amendments](contracts.md). | Use strict JSON validation at wire boundaries. Create validated new snapshots instead of unchecked mutation. |
| Provider transport | `app.llm.OpenAIAdapter` implementation, versioned `PROMPTS`, preflight, experiment CLI; [feasibility record](results/model-feasibility.md). | Connect typed candidates to source validation and workflow stage results. Never treat transport success as semantic success. |
| Candidate conversion | `app.policies.convert_scope`, `convert_policy`, `convert_evidence` are implemented with 52 checks. | Consumers must surface `CandidateConversionError` as an operational stage failure. Chart request fields need individual sources or explicit staff annotations. |
| Mechanical validation | `app.evidence.CitationResolver`, `validate_findings`, `check_predicate`; [supported comparisons](results/rules.md#supported-comparisons). | Pass exactly one extraction revision per input and the selected request/cutoff. Convert errors into operational failure. |
| Rule evaluation | `app.assessment.evaluate_policy`; [aggregation semantics](results/rules.md#aggregation-and-independent-blockers). | Supply one validated finding per criterion, retain traces and independent blockers. |
| Persistence | `app.storage.LocalStore`, `assessment_fingerprint`; [storage API](results/storage.md#integration-api). | Publish validated stages after files exist; preserve stopped runs and original input identity. |
| Workflow | `app.assessment.workflow.StageInterpreter` and `WorkflowEngine` are implemented with controlled-interpreter checks; `app.llm.interpreter.OpenAIStageInterpreter` is the production implementation; the app lifespan starts the engine ([workflow record](results/workflow.md), [stage interpreter record](results/stage-interpreter.md), [HTTP API record](results/http-api.md)). | Live integrated evaluation remains open; the live run is quota-blocked. |
| HTTP and browser | `backend/app/api/` implements the [TRD endpoint table](requirements/technical-requirements.md#http-interface-contracts); the lifespan in `app.main.create_app` wires store/engine/readiness; [HTTP API record](results/http-api.md). | WP-13 consumes these routes; update backend, UI, CI health assertions, and browser tests together. |

Names for unfinished functions/files are agreed implementation targets, not a claim that their tests pass. Confirm the latest code before writing consumers.

## Stage integration contract

The interpreter boundary is asynchronous and contains domain records, never SDK response objects:

```python
scope(StageInputs) -> ScopeInterpretation
policy(StageInputs) -> PolicyInterpretation
evidence(StageInputs, Policy) -> EvidenceInterpretation
```

`StageInputs` carries both document/extraction pairs, selected request context, and typed annotations. Scope returns a sourced request and applicability. Policy returns a structurally and source-validated policy. Evidence returns facts, validated findings, and issues. Each stage may include `StageUsage`. `InterpretationFailure` carries a safe `OperationalError` and any measured usage. The workflow independently checks stage results before persistence and consumption.

`ScopeCandidate.field_sources` is required on the strict provider wire schema. Its default only keeps older Python examples readable. Non-null extracted request fields without their own chart sources are rejected during conversion. Metadata supplied by staff remains an annotation; it does not become chart evidence. An annotation that changes the request assessed by an earlier scope judgment requires reassessment.

## Work that can continue without live quota

Finish candidate conversion, workflow, API, source inspection, UI, exports, deterministic integration tests, and container packaging. Use controlled interpreter/HTTP fixtures explicitly in tests. Production execution must continue to use the configured OpenAI adapter and surface its real errors.

The supplied key failed inference with `insufficient_quota`; the user deferred resolution. Do not repeat paid probes automatically, seek a new provider, select a model as validated, or close live acceptance gates. WP-05 model comparison, WP-15 measured model envelope, WP-16 live semantic trials, and WP-18 live clean-checkout acceptance remain open until access is restored. This does not pause independent implementation.

## Required checks and evidence

From the repository root:

```sh
make check
make browser-test
git diff --check
```

During development, run the relevant test file named in the feature steps. A package is complete only after its actual dependent behavior is checked. A pure library package can finish before the application uses it; its report must state that boundary. Live quality and release gates cannot finish with controlled outputs.

For each completed package, record the implementing commit, requirement/acceptance IDs, exact command, observed result, and remaining limits in its result file and the work breakdown. Update task checkboxes only for tested behavior. Keep test counts attached to the revision/check they describe. Commit only the package's owned, reviewed files; inspect staged paths and ensure `.env`, runtime data, and private vault material are excluded. Push as the user requested, then inspect the actual GitHub Actions outcome.

## Stable decisions and change control

BR-001–BR-012, TR-001–TR-018, A01–A20, WP-01–WP-18, and M0–M6 are stable. OpenAI is the initial inference provider; AWS hosting is a possible later option. One policy, one chart, one request, source inspection, clarification, saved results, and export remain the MVP scope. No retrieval service, agent framework, distributed queue, OCR service, or cloud deployment is required.

When implementation reveals a necessary change, identify the concrete failure and update its owning requirement or contract, TDD, affected feature steps, and tests together. Preserve requirement IDs where meaning is only clarified. Record compatible contract amendments; version incompatible changes and migrate consumers deliberately. Never change independent expected patient findings merely to match an output. A failure in an unused OR alternative remains visible but does not make every alternative mandatory.
