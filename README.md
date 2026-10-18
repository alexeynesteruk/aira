# Aira prior authorization assistant

Take-home project for Aira's Forward Deployed Engineer assessment. The intended product helps clinic staff compare patient chart evidence with an uploaded insurer guideline and identify gaps before submitting a prior authorization request.

The FastAPI/React workspace, strict domain contracts, independently reviewed fixtures, and GitHub Actions container delivery are implemented. Native PDF extraction, versioned local storage, pure provenance/rule evaluation, provider-candidate conversion, the assessment workflow engine, the OpenAI stage interpreter, the HTTP source API, exports, and the staff review UI are implemented and tested, tracked in the [work breakdown](docs/work-breakdown.md). Live inference is currently blocked by API project quota; the user deferred quota resolution.

## Development

Prerequisites: Python 3.13 (uv can install it), uv 0.12.19, Node 24, and npm. From the repository root:

```sh
make install
make check
```

Start `make dev-api` and `make dev-ui` in separate terminals, then open http://localhost:5173. Alternatively, `npm --prefix frontend run build` followed by `make dev-api` serves the built UI at http://localhost:8000. `/health/live` returns 200; `/health/ready` returns 503 until `OPENAI_API_KEY` and `AIRA_MODEL` are configured (see `.env.example`), since the app then starts the real workflow engine. The application stores its data under `AIRA_DATA_DIR`, defaulting to `data/app`; the `/api` routes accept document uploads, assessment submissions, status polling, source pages, and exports. Submitting an assessment makes billable model calls and remains blocked until quota is restored.

Run the saved Chromium tests after installing the browser:

```sh
cd frontend && npx playwright install chromium && cd ..
make browser-test
```

`make check` runs Python lint/format/type checks, pytest, wheel/sdist builds, frontend lint/type checks, Vitest, and a production UI build. Tests must pass before each implementation package is marked complete. Store `OPENAI_API_KEY` and an explicit `AIRA_MODEL` in an ignored `.env` file using `.env.example`; never commit credentials.

## Reviewer quick start

Prerequisite: Docker. No OpenAI key is needed to boot the application, but real assessment work requires it.

1. `cp .env.example .env` and set `OPENAI_API_KEY` and `AIRA_MODEL` (server-side only — the key never reaches the browser).
2. `docker compose up --build` and open http://localhost:8000.
3. Optionally verify model access once: `docker compose run --rm aira python -m app.llm.preflight` — it writes the verification record into the shared `aira-data` volume, so readiness reports it.
4. Upload a policy PDF and a chart PDF, fill optional request metadata, and start the assessment. Runs poll, show the saved outcome with source-level citations, and export JSON or Markdown.

Synthetic fictional PDFs for development cases live in [examples/synthetic](examples/synthetic/README.md).

Application data persists in the `aira-data` volume (`/app/data`, overridable with `AIRA_DATA_DIR`). Inputs must be native-text PDFs (10 MiB / 100 pages maximum); raster, password-protected, annotated, rotated, or fillable-form pages are rejected with an explicit message rather than silently degraded — OCR is a possible future adapter, not part of the MVP. On first run without credentials the UI explains the missing configuration and stays usable for uploads; readiness never claims verified model access, and live assessment calls remain blocked until the deferred API quota is restored.

To exercise the review journeys without credentials, `npm --prefix frontend run build` then `make browser-test` starts the local app plus a labeled fixture server and replays the nine saved staff journeys.

## Model experiment

Prepare an isolated development-text experiment without API calls:

```sh
uv run --project backend python -m app.llm.experiment --case venous_matched --stage scope
```

The output under ignored `data/model-experiments/` contains the prompt, schema, page-tagged inputs, and source hashes. After quota is restored, `python -m app.llm.preflight` (through `uv run --project backend`) explicitly tests access; add `--live` to the experiment command to make a billable stage call. No health endpoint or CI job invokes inference. See the [feasibility record](docs/results/model-feasibility.md) for observed failures, comparison commands, and validation limits.

The workflow CLI runs a full assessment over real PDFs through the production interpreter:

```bash
uv run --project backend python -m app.cli assess \
  --policy examples/guidelines/bcbs_fl_02-33000-31_2025-08-15.pdf \
  --chart examples/charts/robert_mitchell_chart_final.pdf \
  --data-dir data/cli
```

It makes billable model calls and remains blocked until quota is restored; run it with a development key only. `run.json`, `export.json`, and `checklist.md` land under `data/cli/exports/` (see the [stage interpreter record](docs/results/stage-interpreter.md)).

## CI and delivery

[GitHub Actions](https://github.com/alexeynesteruk/aira/actions/workflows/ci.yml) runs on pull requests and pushes to `main`. Python and TypeScript checks gate a Docker build and browser tests against that exact image. Successful `main` runs deliver a checksummed Linux/amd64 image archive as an Actions artifact. Its included README explains how to load and run it. Workflow jobs have no model credentials and make no live inference calls.

The local container command is `docker compose up --build`. Docker is required. The container serves the full review UI and API and starts processing once `OPENAI_API_KEY`/`AIRA_MODEL` are configured; the live A19 upload-to-export workflow remains unverified under the deferred quota. Container build verification is performed in GitHub Actions because Docker is not installed on the current development machine.

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
- [Historical AWS research and future options](docs/aws.md)
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
  app/storage/               SQLite metadata, immutable objects, artifact reuse
frontend/                    React/TypeScript UI, unit tests, and saved browser tests
tests/                       Backend unit/integration tests and fixture contracts
evals/                       Development/reserved case inputs and expected outcomes
.github/workflows/ci.yml      Required checks and tested container delivery
Dockerfile, compose.yaml     Single-origin API/UI container
docs/
  README.md                  Requirements and documentation guide
  requirements/
    README.md                Document ownership and traceability
    business-requirements.md Staff outcomes, scope, and business rules
    technical-requirements.md System and interface requirements
  implementation-plan.md     Scope, milestones, repository structure, delivery
  work-breakdown.md          Packages, dependencies, and completion evidence
  features/
    README.md                Feature index and start order
    01-*.md ... 18-*.md       Individual requirements, tasks, and acceptance
  architecture.md            TDD, implemented boundaries, lifecycle, evidence logic
  contracts.md               Schema contract record and amendment history
  evaluation.md              Acceptance scenarios and release gates
  model-provider.md          OpenAI selection and validation status
  results/                   Verification records for implemented packages
  reviews/                   Independent reviews of shared inputs
  agent-handoff.md           Coding-agent entry point and current boundaries
  aws.md                     Historical AWS research and future options
  exploration.md             Findings from the supplied documents
  research.md                Online research and proposed implementation
  sources/                   Original assessment materials
examples/
  charts/                    Supplied fictional chart and future synthetic inputs
  guidelines/                Versioned BCBS Florida policy snapshots
```

The [work breakdown](docs/work-breakdown.md) tracks completion evidence. WP-01–WP-04, WP-06, WP-10, and WP-12–WP-14 are complete; WP-07–WP-09/WP-11/WP-15–WP-17 are in progress behind the live-quota boundary; WP-18 is in progress with its design-note draft. Submission requires the working live product, a one-line launch command verified on a clean checkout, and the design note. Code must reach the reviewers one day before the call.
