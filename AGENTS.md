# Aira repository instructions

Read [requirements](docs/README.md), [implementation plan](docs/implementation-plan.md), [architecture](docs/architecture.md), and [evaluation](docs/evaluation.md) before changing application behavior. Keep the plan and actual implementation status consistent.

- Build the thin provider-facing evidence checklist. New uploaded policies and charts must drive results; never hard-code the supplied patient's facts or a procedure's coverage rules.
- AWS Bedrock is the selected inference platform. Preserve the one-command local reviewer workflow. Exact model/region and OCR support require the planned feasibility checks.
- Keep model interpretation separate from deterministic validation and rule evaluation. Retain missing, contrary, conflicting, and unsupported evidence states. Processing failures are separate.
- Preserve original documents, page references, exact source spans, and input/configuration versions. Valid JSON or an existing quote does not by itself prove a finding.
- Keep application logic independent of HTTP, storage, and provider adapters. Add retrieval, queues, or agent frameworks only for a demonstrated requirement.
- Implement acceptance checks alongside meaningful behavior changes. Use pure tests for policy logic and provenance, integration tests for adapters, and saved browser tests for user journeys. Record live-model evaluations separately from fixtures.
- Never silently change expected evaluation outcomes to match generated output. Review failures and explain any changed expectation.
- Inspect the diff and run the relevant actual build/type/lint/test commands before reporting completion. This repository is documentation-only today; add executable commands with their implementation, not invented success claims.
- Keep credentials, runtime data, and private Obsidian/client material out of commits. Store only generic engineering lessons and public/source-provided assessment materials here.
- For parallel work, assign file ownership and one integration owner. Coordinate shared contracts and evaluate the merged result before calling a milestone complete.
