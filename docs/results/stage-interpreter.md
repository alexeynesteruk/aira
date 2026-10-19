# WP-07–WP-09 stage interpreter and M3 CLI verification

Verified October 18, 2026 against the working-tree model integration. [WP-07](../work-breakdown.md#wp-07-request-context-and-applicability)–[WP-09](../work-breakdown.md#wp-09-evidence-mapping) own the semantic stages and [WP-05](../work-breakdown.md#wp-05-model-experiment-and-adapter) owns provider status. This record covers controlled evidence: every check runs the real AsyncOpenAI SDK over `httpx.MockTransport` with scripted Responses bodies quoting the supplied PDFs — it is not model output and proves nothing about live semantic quality. No test contacts a provider.

## Implemented boundary

[`backend/app/llm/interpreter.py`](../../backend/app/llm/interpreter.py) supplies the production `StageInterpreter`. `OpenAIStageInterpreter(adapter)` renders each stage's input with the shared [`render_stage_input`](../../backend/app/assessment/stages.py), calls `OpenAIAdapter.interpret` with the versioned `PROMPTS` instructions and strict candidate schema, then converts the returned candidate through `app.policies.convert_scope`/`convert_policy`/`convert_chart`/`convert_findings` with a `CitationResolver` over the run's real extractions. Only typed, source-valid domain records cross into the workflow.

Dependency direction: `app.llm.interpreter` imports `app.assessment.stages`, `app.policies`, `app.evidence`, `app.documents.native` (for the pdfplumber version), and `app.schemas`. It never imports `app.assessment.workflow` or `app.storage`; configuration enters as a parser-fingerprint string so this module stays workflow-free.

## Prompt and configuration identity

`prompt_reference(stage)` returns `VersionReference(name=stage, version="<prompt version>+<digest>")` where the digest is the first 12 characters of the SHA-256 over the prompt instructions plus the canonical strict output schema. Any prompt-text or schema change invalidates run and cache identity even if the version label is forgotten. `openai_configuration(settings, parser_fingerprint)` builds the `ConfigurationProvenance` the engine verifies: the real pdfplumber version, the supplied workflow parser fingerprint, all three prompt references, the configured model, the SDK version, and the output-token budget — with no region (OpenAI does not use one).

## Failure mapping and the no-repair policy

- `ModelFailure` (transport, envelope, refusal, or structured-validation failures classified by the adapter) becomes `InterpretationFailure` carrying the adapter's safe `OperationalError` and a `StageUsage` built from the reported metrics, so failed stages still record attempts, latency, request/response IDs, and any reported tokens.
- `CandidateConversionError` (unresolvable citations, unknown criteria, structural violations, or a resolved scope with no remaining citation) becomes `InterpretationFailure` with that operational code — `citation_invalid` or `invalid_output` — and the usage of the successful call. Conversion failures are operational failures; they never become "missing" evidence. An uncited request value is dropped and named for staff. A cited mismatch still stands.
- No automatic repair attempt is implemented. The TRD allows at most one; the interpreter surfaces the first invalid candidate as an operational failure instead.

## CLI vertical slice

`backend/app/cli.py` exposes `uv run --project backend python -m app.cli assess --policy P.pdf --chart C.pdf [--data-dir DIR] [--output-dir DIR] [--env-file FILE]` plus staff-metadata flags (`--procedure`, `--procedure-code`, `--anatomical-target`, `--laterality`, `--payer`, `--plan`, `--service-date`, `--assessment-cutoff`) recorded as `staff-<field>` annotations. `run_assessment` ingests both PDFs under generated document IDs, runs a real `WorkflowEngine` to a stopped run, and `write_outputs` writes `run.json` always plus `export.json` and `checklist.md` for `completed`/`needs_input` runs. Missing `OPENAI_API_KEY`/`AIRA_MODEL` or an unusable PDF exits 2 without contacting the provider; a finished run exits 0, a failed or interrupted run 1. The command makes billable model calls and remains blocked until the deferred quota is restored.

## Observed verification

Commands run from the repository root:

| Command | Result |
| --- | --- |
| `uv run --project backend --locked pytest -c backend/pyproject.toml tests/integration/test_openai_interpreter.py -q` | 12 passed in about 4 seconds. |
| `uv run --project backend --locked pytest -c backend/pyproject.toml tests/integration/test_openai_interpreter.py tests/integration/test_workflow.py tests/unit/test_stages.py -q` | 36 passed. |
| `make check` | Ruff lint/format, strict mypy, all pytest checks, backend build, and frontend lint/typecheck/Vitest/build pass. |

[`test_openai_interpreter.py`](../../tests/integration/test_openai_interpreter.py) covers: the scope request sends the versioned instructions, the exact rendered input, a strict JSON-schema format, and `store: false`; a scripted mismatch candidate converts to cited `applicability_mismatch` with usage carrying tokens, model, and request/response IDs; policy and evidence candidates convert to resolved `Policy`/`Finding`/`ChartFact` records with a deterministic `policy_id`, and the evidence request contains the criteria and the chart document only; an invented quote fails `citation_invalid`, an uncited request field is dropped while a cited mismatch stands, and a 429 `insufficient_quota` body fails non-retryable `throttled` with recorded attempts; `prompt_reference` changes with the prompt text and `openai_configuration` is accepted by `WorkflowEngine`; end to end, the engine completes A01 `applicability_mismatch` with one HTTP request, the scripted applicable path completes an evaluated outcome with three requests, and an invented evidence quote fails `citation_invalid` at `mapping_evidence` with the policy artifact already persisted; the CLI writes `run.json`/`export.json`/`checklist.md` for a completed run, only `run.json` for a failed run, and `main` exits 2 on missing configuration before any provider client is built.

## Limitations

- All evidence is scripted transport data. Semantic quality, model comparison, and the M3 live-run exit check remain unverified until the deferred API quota is restored.
- The scripted candidates quote real text but do not demonstrate that a model produces source-valid candidates.
- The CLI is a development instrument for one pair; the HTTP admission path is implemented and verified separately in the [HTTP API record](http-api.md).
