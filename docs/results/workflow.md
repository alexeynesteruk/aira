# WP-11 workflow verification

Verified October 18, 2026 against the working-tree workflow package. [WP-11](../work-breakdown.md#wp-11-workflow-and-recovery) owns implementation status and the integrating commit. This record covers controlled orchestration evidence: every test runs the real engine over real PDFs and a real `LocalStore` with a scripted `StageInterpreter`. It does not establish live-model accuracy, HTTP wiring, or a completed staff workflow.

## Implemented boundary

[`backend/app/assessment/workflow.py`](../../backend/app/assessment/workflow.py) runs one local worker over a bounded queue. `WorkflowEngine(store, interpreter, configuration, parser_config=..., limits=...)` verifies that the supplied `ConfigurationProvenance` names the actual pdfplumber parser version and a `workflow_parser_fingerprint(parser_config, limits)` covering extraction settings and workflow limits, so non-default limits cannot silently reuse another configuration's work.

| Operation | Interface and caller responsibility |
| --- | --- |
| Lifecycle | `await engine.start()` marks unfinished stored runs interrupted and starts the worker. `await engine.close()` stops admission, cancels the worker, and interrupts remaining active runs. A closed engine cannot restart. |
| Admission | `await engine.submit(CreateAssessmentRequest)` validates the document roles, creates a queued `RunRecord`, and raises `WorkflowAdmissionError` with `configuration_missing` before `start()` or after `close()`, and with retryable `queue_full` when `max_pending` runs are already waiting. |
| Observation | `await engine.wait(run_id)` is a test/CLI convenience returning the stopped record; HTTP consumers poll persisted state instead. |
| Stage interpreter | `StageInterpreter` is an async protocol: `scope(StageInputs)`, `policy(StageInputs)`, `evidence(StageInputs, Policy)`. An `InterpretationFailure` carries a safe `OperationalError` plus any measured `StageUsage`; no provider object crosses the boundary. |
| Guardrails | `WorkflowLimits(max_pending=4, max_context_characters=200_000, stage_timeout_seconds=90.0)` are provisional engineering guardrails on queue depth, rendered stage-input characters, and stage deadlines — not measured model capacity. |

Every interpreted stage is checked before consumption or cache publication: outputs are revalidated against their strict models, every `SourceSpan` resolves against the run's actual extractions, evidence findings are recomputed by `validate_findings`, and the final `EvaluationResult` is persisted as a validated artifact. Reused artifacts record zero-attempt usage entries, and unfinished work is marked `interrupted` rather than silently resumed.

## Rendered stage inputs and the corrected context guardrail

The guardrail previously measured the canonical JSON of the complete `DocumentRecord`/`ExtractionRecord` objects, geometry included: 148,461 characters for the supplied August 2025 policy and 61,345 for the supplied chart, about 209.8k characters against the 200,000 default. The supplied A01 pair therefore failed `unsupported_input` before applicability ran, although its native text is only about 48k characters.

[`backend/app/assessment/stages.py`](../../backend/app/assessment/stages.py) now renders the exact text a stage consumes, and the guardrail measures that instead. `render_stage_input(inputs, stage, policy=None)` emits compact JSON with page-ordered native block text, the selected request fields, and staff annotations — never hashes, block IDs, geometry, extraction revisions, or source spans. Scope reads both documents (policy first), the policy stage reads the policy document, and evidence reads the chart plus the interpreted criteria. Measured rendered lengths for the supplied pair: **scope 51,533; policy 40,776; evidence 10,992 characters** — all within the provisional 200,000 default.

## Observed verification

Commands run from the repository root:

| Command | Result |
| --- | --- |
| `uv run --project backend --locked pytest -c backend/pyproject.toml tests/unit/test_stages.py -q` | 9 passed. |
| `uv run --project backend --locked pytest -c backend/pyproject.toml tests/integration/test_workflow.py -q` | 15 passed in about 2 seconds. |
| `make check` | Ruff lint/format, strict mypy, 445 pytest checks, backend build, and frontend lint/typecheck/Vitest/build all pass. |

[`test_workflow.py`](../../tests/integration/test_workflow.py) uses `ControlledInterpreter`, a test `StageInterpreter` whose scripted quotes resolve through `CitationResolver` on the run's real extractions, so its domain records carry source-valid spans. Controlled coverage maps to the matrix as follows: the A01 shape — the supplied pair completes as `applicability_mismatch` with cited scope sources, no policy/facts/findings, and no policy or evidence calls; uncertain scope stops in `needs_input` with named unresolved fields; an applicable path completes all six phases with a usage entry per interpreted phase, a persisted `EvaluationResult`, and an outcome equal to `evaluate_policy` on the same validated inputs, including a missing-finding variant; a corrupted citation fails `citation_invalid` without publishing the stage artifact; an interpreter failure retains its error code and recorded usage; a scripted stage delay fails with a retryable `timeout`; an image-only chart fails `extraction_failed` during `extracting`; a tiny context limit fails `unsupported_input` before interpretation; a saturated queue rejects admission with retryable `queue_full`; submission before `start()` or after `close()` fails `configuration_missing`; and swapped document roles are rejected without creating a run. The A16/A17 lifecycle behaviors — a blocked run marked `interrupted` on close with its last phase and earlier snapshots retained, a clarification run linked by `parent_run_id` with a distinct input fingerprint, and an identical submission reusing stored extractions and stage artifacts with zero-attempt usage while a changed annotation misses the cache — are covered the same way.

## Limitations

- The interpreter is scripted: it returns pre-decided source-valid records. These tests exercise orchestration, validation, caching, and the failure lifecycle — never model quality or live accuracy.
- The production stage adapter is verified separately: `app.llm.interpreter.OpenAIStageInterpreter` wires the adapter, versioned prompts, and candidate conversion over mocked transport, and the engine runs through it in the same tests — see the [stage interpreter record](stage-interpreter.md). Its live run remains quota-blocked.
- HTTP admission, status, and source routes are implemented and verified separately; the application lifespan constructs and starts this engine — see the [HTTP API record](http-api.md).
- The `WorkflowLimits` defaults are provisional guardrails pending the WP-15 measured input envelope; the rendered lengths above verify the supplied A01 pair only.
