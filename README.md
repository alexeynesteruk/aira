# Aira prior authorization assistant

Take-home project for Aira's Forward Deployed Engineer assessment. The intended product helps clinic staff compare patient chart evidence with an uploaded insurer guideline and identify gaps before submitting a prior authorization request.

The FastAPI/React workspace, strict domain contracts, independently reviewed fixtures, and a local verification suite are implemented. Native PDF extraction, versioned local storage, pure provenance/rule evaluation, provider-candidate conversion, the assessment workflow engine, the OpenAI stage interpreter, the HTTP source API, exports, and the staff review UI are implemented and tested, tracked in the [work breakdown](docs/work-breakdown.md). One live run of the supplied pair completed as an applicability mismatch during development (on an earlier extraction revision); there is no live accuracy benchmark yet, and the 98-page path has not been run live.

## Development

Prerequisites: Python 3.13 (uv can install it), uv 0.12.19, Node 24, and npm. From the repository root:

```sh
make install
make check
```

Start `make dev-api` and `make dev-ui` in separate terminals, then open http://localhost:5173. Alternatively, `npm --prefix frontend run build` followed by `make dev-api` serves the built UI at http://localhost:8000. `/health` and `/health/live` return 200; `/health/ready` returns 503 until `OPENAI_API_KEY` and `AIRA_MODEL` are configured (see `.env.example`), since the app then starts the real workflow engine. The application stores its data under `AIRA_DATA_DIR`, defaulting to `data/app`; the `/api` routes accept document uploads, standalone document preparation (build, retry, rebuild, approve, reject), assessment submissions, status polling, source pages, and exports. Submitting an assessment makes billable model calls.

Run the saved Chromium tests after installing the browser:

```sh
cd frontend && npx playwright install chromium && cd ..
make browser-test
```

`make check` runs Python lint/format/type checks, pytest, wheel/sdist builds, frontend lint/type checks, Vitest, and a production UI build. Store `OPENAI_API_KEY` and an explicit `AIRA_MODEL` in an ignored `.env` file using `.env.example`; never commit credentials.

## Reviewer quick start

Prerequisites: uv and Node 24/npm. No OpenAI key is needed to boot the application, but real assessment work requires it.

1. `cp .env.example .env` and set `OPENAI_API_KEY`. `AIRA_MODEL` is prefilled with `gpt-4o`; any OpenAI model with structured outputs works. Settings are read from `.env` on the server only; the key never reaches the browser. For Gemini, see [Model providers](#model-providers).
2. `./scripts/launch.sh` installs locked dependencies, builds the UI, and serves everything at http://localhost:8000.
3. Optionally verify model access once: `uv run --project backend python -m app.llm.preflight`. It writes the verification record into the data directory, so readiness reports it.
4. Upload a policy and use **Prepare document** to build its reusable rule set without a chart. Inspect coverage, extraction steps, issues, and saved versions. Prepare a chart independently, or let **Start assessment** prepare both automatically. Select saved versions, fill optional request metadata, and assess. Results retain their exact build IDs and export JSON or Markdown.

The first assessment of the sample pair makes about 75 model calls (about 2-6 minutes); later runs against the same guideline reuse the saved rule set. The sample pair is [the supplied chart](examples/charts/robert_mitchell_chart_final.pdf) (pacemaker request) and [the BCBS guideline](examples/guidelines/bcbs_fl_02-33000-31_2025-08-15.pdf) (vein procedures), so it stops at an applicability mismatch.

Synthetic fictional PDFs for development cases live in [examples/synthetic](examples/synthetic/README.md).

Application data persists under `data/app` (overridable with `AIRA_DATA_DIR`). Intake accepts native-text PDFs up to 10 MiB / 250 pages and 2,000,000 extracted characters; each call/build also has explicit budgets. Controlled tests complete 100/200-page fictional guidelines; this does not establish live model quality on arbitrary documents. Image-only pages fail explicitly by default. OCR is an opt-in parser configuration requiring Tesseract. Password-protected, unsupported annotated, rotated, or fillable-form inputs fail rather than silently lose content. On first run without credentials the UI explains the missing configuration and stays usable for uploads; readiness shows model access as unverified until the optional preflight above succeeds.

To exercise the review journeys without credentials, `npm --prefix frontend run build` then `make browser-test` starts the local app plus a labeled fixture server and replays the saved staff journeys, including independent preparation and recovery.

## Model experiment

Prepare an isolated development-text experiment without API calls:

```sh
uv run --project backend python -m app.llm.experiment --case venous_matched --stage scope
```

The output under ignored `data/model-experiments/` contains the prompt, schema, page-tagged inputs, and source hashes. `python -m app.llm.preflight` (through `uv run --project backend`) explicitly tests access; add `--live` to the experiment command to make a billable stage call. No health endpoint or CI job invokes inference. See the [feasibility record](docs/results/model-feasibility.md) for observed failures, comparison commands, and validation limits.

The workflow CLI runs a full assessment over real PDFs through the production interpreter:

```bash
uv run --project backend python -m app.cli assess \
  --policy examples/guidelines/bcbs_fl_02-33000-31_2025-08-15.pdf \
  --chart examples/charts/robert_mitchell_chart_final.pdf \
  --data-dir data/cli
```

It makes billable model calls; run it with a development key only. `run.json`, `export.json`, and `checklist.md` land under `data/cli/exports/` (see the [stage interpreter record](docs/results/stage-interpreter.md)).

## Verification

Verification is local. There is no hosted CI.

```sh
make check         # ruff, format, mypy, pytest, wheel/sdist, frontend lint/type/Vitest/build
make browser-test  # saved Playwright journeys against the built UI
```

Both targets run with no model credentials and make no live inference calls.

The local command is `./scripts/launch.sh`. It serves the review UI and API and starts processing once `OPENAI_API_KEY`/`AIRA_MODEL` are configured. One live run of the supplied pair completed as an applicability mismatch during development (on an earlier extraction revision); there is no live accuracy benchmark yet, and the 98-page path has not been run live.

## Long-document preparation

Guideline preparation ([implementation record](docs/results/wp19-implementation.md)) uses full-source structural chunks, immutable section outputs, bounded group reconciliation, a final scope merge when needed, source-coverage audits, and deterministic graph compilation. Saved guideline rules and chart facts are independent. A new patient or changed request reuses the policy build; a changed policy reuses chart facts. Failed builds retain completed checkpoints for linked retry. Rebuild creates a new version; it does not replace a saved assessment.

The chart is read in one model call under the per-call budget `AIRA_BUILD_INPUT_TOKENS` (default 60000 UTF-8 bytes, roughly 25-30 dense chart pages). A larger chart is rejected, never truncated; raise the budget only if your model's context allows.

## Model providers

Direct OpenAI uses backend-only `OPENAI_API_KEY`, explicit `AIRA_MODEL`, and the official Responses API when `.env` does not set an endpoint. A base URL or transport that exists only in the shell is ignored. To use any OpenAI-compatible `/v1` API (e.g. local Ollama, vLLM, Groq, DeepSeek, Together, OpenRouter, or LiteLLM), set `OPENAI_BASE_URL` and `AIRA_MODEL` in `.env` (and optionally `AIRA_LLM_BACKEND=openai_compatible`). For local endpoints without authentication (such as Ollama or vLLM), `OPENAI_API_KEY` can be omitted. The adapter automatically handles chat completions transport, adaptive fallback between `max_completion_tokens` and `max_tokens`, `json_schema` and `json_object` structured outputs, and strips markdown code fences from model outputs. `AIRA_LLM_BACKEND=litellm` is only needed to take the URL from the process environment instead of the file. Health displays the active connection and model and never makes inference calls. No API key is sent to the browser.

Google Gemini works through its OpenAI-compatible endpoint. Put these lines in `.env` (not the shell; the commented Gemini block in `.env.example` has them):

```sh
OPENAI_API_KEY=<Gemini API key>
OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
AIRA_LLM_BACKEND=openai_compatible
AIRA_MODEL=gemini-2.5-flash
```

`openai_compatible` uses chat completions with `json_schema` output and sends no gateway-only request fields. `.env.example` also sets recommended deadlines (`AIRA_REQUEST_TIMEOUT_SECONDS=120`, `AIRA_STAGE_TIMEOUT_SECONDS=300`, `AIRA_WORKFLOW_STAGE_TIMEOUT_SECONDS=300`) and `AIRA_MAX_OUTPUT_TOKENS=8192` for slower models and Gemini thinking tokens.

Standalone CLI preparation uses the same service and adapter:

```sh
uv run --project backend python -m app.cli prepare --role policy --document path/to/guideline.pdf --data-dir data/cli
```

Use `--role chart` for chart facts. These are billable operations. The [feature](docs/features/19-long-document-rule-compilation.md), [implementation plan](docs/plans/long-document-rule-compilation.md), and [research log](docs/research/long-document-rule-extraction.md) describe the design and its open live checks. Unsupported exceptions, unresolved references, and audit discrepancies block readiness; approval does not remove those blockers. A build's source coverage is a processing ledger, not a semantic-completeness certificate.

## Project documentation

- [Project documentation](docs/README.md)
- [Business requirements document](docs/requirements/business-requirements.md)
- [Technical requirements document](docs/requirements/technical-requirements.md)
- [Implementation plan and milestones](docs/implementation-plan.md)
- [Work breakdown and dependencies](docs/work-breakdown.md)
- [Feature list and individual specifications](docs/features/README.md)
- [Technical design document (TDD) and architecture](docs/architecture.md)
- [Evaluation and release checks](docs/evaluation.md)
- [Decision record](docs/decisions.md)
- [Design note](docs/design-note.md)
- [HTTP API, stage interpreter, workflow, and input-limit records](docs/README.md#documentation-guide)
- [Review UI journeys record](docs/results/review-ui.md)
- [OpenAI integration and feasibility record](docs/results/model-feasibility.md)
- [Initial document exploration](docs/exploration.md)
- [Implementation research and recommendation](docs/research.md)
- [Assessment brief](docs/sources/Aira_FDE_Build_Case.pdf)
- [Supplied fictional patient chart](examples/charts/robert_mitchell_chart_final.pdf)
- [Guideline snapshots and provenance](examples/guidelines/README.md)

## Current structure

```text
backend/                     FastAPI application and locked Python dependencies
  app/api/                   HTTP routes, error envelopes, request IDs, readiness
  app/assessment/            Workflow engine, stage-input renderer, rules, Markdown export
  app/documents/             Native PDF intake, extraction, and source spans
  app/evidence/              Citation validation, bounded predicates, finding checks
  app/llm/                   OpenAI adapter, stage interpreter, prompts, preflight, experiment CLI
  app/policies/              Provider-candidate conversion to validated domain records
  app/schemas/               Versioned domain, request, provider, and API contracts
  app/storage/               SQLite metadata, immutable objects, artifact reuse, policy rule sets
frontend/                    React/TypeScript UI, unit tests, and saved browser tests
tests/                       Backend unit/integration tests and fixture contracts
evals/                       Development/reserved case inputs and expected outcomes
scripts/                     One-line launch script and development entry points
.github/workflows/ci.yml     Workflow definition for the same checks; verification is run locally
docs/
  README.md                  Requirements and documentation guide
  requirements/
    README.md                Document ownership and traceability
    business-requirements.md Staff outcomes, scope, and business rules
    technical-requirements.md System and interface requirements
  implementation-plan.md     Scope, milestones, repository structure, delivery
  work-breakdown.md          Historical planning record (not maintained)
  features/
    README.md                Feature index and start order
    01-*.md ... 19-*.md       Individual requirements, tasks, and acceptance
  architecture.md            TDD, implemented boundaries, lifecycle, evidence logic
  contracts.md               Schema contract record and amendment history
  evaluation.md              Acceptance scenarios and release gates
  model-provider.md          OpenAI selection and validation status
  decisions.md               Architectural and technical decision record
  design-note.md             Submission note
  agent-handoff.md           Implementation handoff and current boundaries
  exploration.md             Findings from the supplied documents
  research.md                Online research and proposed implementation
  plans/                     Long-document execution plan
  research/                  Dated long-document research log
  results/                   Verification records for implemented packages
  reviews/                   Independent reviews of shared inputs
  sources/                   Original assessment materials
examples/
  charts/                    Supplied fictional chart and future synthetic inputs
  guidelines/                Versioned BCBS Florida policy snapshots
```
