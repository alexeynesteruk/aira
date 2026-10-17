# Aira prior authorization assistant

Take-home project for Aira's Forward Deployed Engineer assessment. The intended product helps clinic staff compare patient chart evidence with an uploaded insurer guideline and identify gaps before submitting a prior authorization request.

Implementation has started with a FastAPI/React application shell, locked dependencies, automated checks, and GitHub Actions container delivery. Assessment processing is not implemented yet. OpenAI is the selected initial inference provider; the supplied API key and a verified model configuration are required for the upcoming live integration.

## Development

Prerequisites: Python 3.13 (uv can install it), uv 0.12.19, Node 24, and npm. From the repository root:

```sh
make install
make check
```

Start `make dev-api` and `make dev-ui` in separate terminals, then open http://localhost:5173. Alternatively, `npm --prefix frontend run build` followed by `make dev-api` serves the built UI at http://localhost:8000. Neither path requires credentials for the shell. `/health/live` returns 200; `/health/ready` returns 503 because assessment processing is not yet available.

Run the saved Chromium tests after installing the browser:

```sh
cd frontend && npx playwright install chromium && cd ..
make browser-test
```

`make check` runs Python lint/format/type checks, pytest, wheel/sdist builds, frontend lint/type checks, Vitest, and a production UI build. Tests must pass before each implementation package is marked complete. Store the future `OPENAI_API_KEY` and `AIRA_MODEL` in an ignored `.env` file using `.env.example`; never commit credentials.

## CI and delivery

[GitHub Actions](https://github.com/alexeynesteruk/aira/actions/workflows/ci.yml) runs on pull requests and pushes to `main`. Python and TypeScript checks gate a Docker build and browser tests against that exact image. Successful `main` runs deliver a checksummed Linux/amd64 image archive as an Actions artifact. Its included README explains how to load and run it. Workflow jobs have no model credentials and make no live inference calls.

The local container command is `docker compose up --build`. Docker is required. The container currently serves the shell; this is not yet the live A19 upload-to-export workflow. Container build verification is performed in GitHub Actions because Docker is not installed on the current development machine.

## Project documentation

- [Project documentation](docs/README.md)
- [Business requirements document](docs/requirements/business-requirements.md)
- [Technical requirements document](docs/requirements/technical-requirements.md)
- [Implementation plan and milestones](docs/implementation-plan.md)
- [Work breakdown and dependencies](docs/work-breakdown.md)
- [Feature list and individual specifications](docs/features/README.md)
- [Architecture and evidence semantics](docs/architecture.md)
- [Evaluation and release checks](docs/evaluation.md)
- [AWS service choices and verified constraints](docs/aws.md)
- [Initial document exploration](docs/exploration.md)
- [Implementation research and recommendation](docs/research.md)
- [Assessment brief](docs/sources/Aira_FDE_Build_Case.pdf)
- [Supplied fictional patient chart](examples/charts/robert_mitchell_chart_final.pdf)
- [Guideline snapshots and provenance](examples/guidelines/README.md)

## Current structure

```text
backend/                     FastAPI application and locked Python dependencies
frontend/                    React/TypeScript UI, unit tests, and saved browser tests
tests/                       Backend unit/integration tests and fixture contracts
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
  architecture.md            Context, components, lifecycle, and evidence logic
  evaluation.md              Acceptance scenarios and release gates
  aws.md                     AWS decisions and current service constraints
  exploration.md             Findings from the supplied documents
  research.md                Online research and proposed implementation
  sources/                   Original assessment materials
examples/
  charts/                    Supplied fictional chart and future synthetic inputs
  guidelines/                Versioned BCBS Florida policy snapshots
```

The [work breakdown](docs/work-breakdown.md) tracks completion evidence. WP-01–WP-03 establish the foundation, contracts, and expectations, followed by model/PDF experiments. Submission requires the working live product, a one-line launch command verified on a clean checkout, and a short design note. Code must reach the reviewers one day before the call.
