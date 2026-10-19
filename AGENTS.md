# Aira repository instructions

Read the [BRD and TRD](docs/requirements/README.md), [implementation plan](docs/implementation-plan.md), [architecture](docs/architecture.md), and [evaluation](docs/evaluation.md) before changing application behavior. Use the relevant [feature specification](docs/features/README.md) for tasks and acceptance, and the [work breakdown](docs/work-breakdown.md) for dependencies, status, and completion evidence. Keep requirements, design, and actual implementation status consistent.

- Build the thin provider-facing evidence checklist. New uploaded policies and charts must drive results; never hard-code the supplied patient's facts or a procedure's coverage rules.
- OpenAI is the selected initial inference provider, using the assessment-supplied key through backend-only configuration. Preserve the one-command local reviewer workflow. Exact model and input support require the planned feasibility checks.
- Keep model interpretation separate from deterministic validation and rule evaluation. Retain missing, contrary, conflicting, and unsupported evidence states. Processing failures are separate.
- Preserve original documents, page references, exact source spans, and input/configuration versions. Valid JSON or an existing quote does not by itself prove a finding.
- Keep application logic independent of HTTP, storage, and provider adapters. Add retrieval, queues, or agent frameworks only for a demonstrated requirement.
- Implement acceptance checks alongside meaningful behavior changes. Use pure tests for policy logic and provenance, integration tests for adapters, and saved browser tests for user journeys. Record live-model evaluations separately from fixtures.
- Never silently change expected evaluation outcomes to match generated output. Review failures and explain any changed expectation.
- Inspect the diff and run the relevant actual checks before reporting completion: `make check` and `make browser-test`. Track implemented scope in the work breakdown; green shell tests do not establish live assessment accuracy.
- Keep credentials, runtime data, and private Obsidian/client material out of commits. Store only generic engineering lessons and public/source-provided assessment materials here.
- For parallel work, assign file ownership and one integration owner. Coordinate shared contracts and evaluate the merged result before calling a milestone complete.

- `make browser-test` runs two Playwright projects: `shell` (port 8000, the unconfigured app) and `journeys` (port 8001, `tests/e2e/fixture_server.py`). The fixture interpreter is test-only support and must never be wired into `backend/app`.
