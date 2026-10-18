# Aira implementation plan

Build a provider-facing assistant that compares one selected procedure request with an uploaded insurer policy and returns a checklist of documented requirements, contrary evidence, and gaps. Staff must be able to open the supporting policy and chart passages for each finding. The product reports documentation readiness; it does not issue a payer decision.

The chosen direction is Python, FastAPI, React, TypeScript, Pydantic, and a thin OpenAI Responses API adapter, with a local container launch for assessment reviewers. The user selected OpenAI for the initial MVP on October 18, superseding the earlier Bedrock proposal. No AWS credentials or deployment are required. The exact model configuration remains subject to M1 verification; native PDF text is the initial input path, with unsupported scans explicitly rejected. See the [provider decision](model-provider.md).

Status on October 18, 2026: the full non-live stack is implemented — contracts, PDF intake, storage, stage interpreter + adapter, workflow, HTTP source API, exports, and the staff review UI — with deterministic, controlled-interpreter, and fixture-interpreter evidence passing in GitHub Actions. The OpenAI access probe reached the provider but failed with insufficient quota; the user deferred quota resolution, so live semantic validation, the measured token envelope, and the live reviewer acceptance run remain open. The [BRD and TRD](requirements/README.md) define requirements and contracts; [architecture](architecture.md) defines the design; [evaluation](evaluation.md) defines the acceptance cases; [model provider decision](model-provider.md) records the active integration boundary; [AWS research](aws.md) preserves the earlier proposal and future options.

## Stable delivery baseline

Keep M0–M6, WP-01–WP-18, and the linked BR/TR/acceptance IDs stable. The scope remains one policy, one chart, one selected request, an inspectable evidence checklist, saved results, and export. The October 18 provider change selects OpenAI and removes AWS credentials from MVP prerequisites; it does not add cloud deployment or change the staff journey. The quota deferral changes the live-validation schedule only.

Record new evidence and package completion in the work breakdown. Change scope, contracts, supported input behavior, or acceptance expectations only with an explicit rationale and coordinated requirement/design/test updates. Do not rebuild the sequence around each test result or mark a milestone complete while a required live gate is open.

## Product scope

The MVP handles one guideline PDF and one chart PDF per assessment, and one selected procedure request. A document may contain multiple clinical problems or procedure options; the user selects the request when extraction cannot resolve it unambiguously. Supporting multiple uploads, longitudinal patient folders, and automatic policy discovery can follow later.

The initial user journey is:

1. Upload the policy and chart. Enter or confirm the requested procedure, payer and plan, and service date when those are ambiguous or absent. Retain user corrections as annotations alongside the extracted source.
2. See extraction progress and any unreadable pages. Inspect the selected documents, policy revision, and request summary.
3. Review applicability. A confirmed payer or procedure mismatch stops assessment. An uncertain plan, date, or policy scope requires clarification; an upload does not prove the policy applies.
4. Inspect requirements grouped according to the policy's AND/OR structure. Each finding displays the requirement, its policy citation, chart evidence, and the reason for its status.
5. Open either source at the cited page. Review missing documentation, conflicts, and unsupported interpretation. Suggested next steps request clarification or documentation without inventing clinical facts or treatment advice.
6. Save or export the assessment as structured JSON and a readable checklist, including unresolved issues and the exact policy version. Re-running with a changed input creates a new result.

Include source inspection, meaningful processing states, and useful failure messages in the first vertical slice. Defer chat, autonomous agents in the application, automatic appeals or submission letters, payer portals, EHR/FHIR connections, policy web crawling, vector databases, and production infrastructure. The application executes an explicit staged workflow.

## Decisions and remaining experiments

The [decision record](decisions.md) consolidates these decisions, including implementation-time ones, with rationale and status; the table below remains the planned direction.

| Decision | Direction | Evidence or condition |
| --- | --- | --- |
| Core workflow | Applicability, policy requirements, evidence, deterministic aggregation, staff review. | Matches the assessment and recurring public implementation pattern. |
| Platform | OpenAI Responses API for model inference; portable local application runtime. | Latest user provider selection plus the clean-checkout requirement. |
| Application stack | FastAPI, React and TypeScript, Pydantic, Python tests and saved browser tests. | Fits Aira's stated stack and the domain contracts. |
| Persistence | SQLite metadata and local document/artifact files in a mounted data directory. | A single local reviewer needs durable runs without extra services. |
| PDF extraction | Native text and layout extraction first; page-level quality checks. | Supplied documents have text but include layout and chronology traps. |
| OCR | Explicitly reject unsupported scans in the initial release; consider OCR later if representative inputs justify it. | M2 verifies native extraction, mixed-page accounting, and the supported input envelope. Never silently skip a page. |
| Context | Full page-tagged documents when within measured limits. | Establish an evidence-recall baseline before adding retrieval. Reject oversized input visibly until a tested section strategy exists. |
| Model | Explicit OpenAI model configuration; select a tested configuration in M1. | Compare accessible candidates on quality, latency, access, and usage, or record the single-model limitation. No model quality claim yet. |
| Policy logic | Flat logical nodes referencing criteria; local structural validation and evaluation. | Avoid recursive wire schemas and preserve nested policy conditions. |
| Scope generality | Two policy families, new patient charts, and an unseen pair in the final evaluation. | Vein-only templates would not satisfy the assessment's generality requirement. |

Revision date and effective date are different fields. Preserve both when present. The two BCBS snapshots demonstrate version changes, but their revision dates alone do not prove which version governs a service. Unsupported policy language remains a review item instead of being compiled into a guessed rule.

## Implementation sequence

Work in small changes with an executable exit check. A milestone is complete only when its artifact and check exist; this table records the planned work, not completed delivery. The [work breakdown](work-breakdown.md) is the detailed dependency and implementation-status record. These milestones group that work rather than maintaining a second completion ledger.

| Milestone | Build and deliver | Exit check | Depends on |
| --- | --- | --- | --- |
| M0 Contracts and expectations | Establish the minimal project foundation, request scope, rule states, initial schema baseline, annotated policy passages, fictional chart fixtures, and expected outcomes. Select a second policy family. Record input provenance and separate development from held-out cases. | A reviewer can explain expected branches and cited evidence without running a model. No unresolved requirement is hidden in a fixture. Feasibility findings can amend versioned schemas before integration. | Current research |
| M1 Model feasibility | Add the smallest OpenAI Responses API adapter and a CLI experiment for policy and chart extraction. Compare two available candidates where access permits; otherwise document the single-model limitation. Pin the selected provider/model, SDK, prompt, schema, and inference settings. | A real call from a reviewer-like environment produces validated structured output and page citations. Missing access, unsupported schema, refusal, and timeout are visible errors. Record tokens, latency, and configuration. | M0 |
| M2 PDF feasibility | Implement document hashing, page/block extraction, coordinates, and native-text quality checks. Inspect columns and tables against rendered pages. Identify unsupported scans and mixed-page failures explicitly; finalize the native-text support boundary and measured input envelope. | The supplied dates, units, negation, tables, and page-spanning passages survive extraction. Every page is accounted for; bad input produces an actionable state. | M0; final combined input limits use M1 results |
| M3 End-to-end workflow | Implement scope checking, policy and chart extraction, evidence matching, provenance validation, rule aggregation, and persisted run artifacts. Add bounded stage execution and explicit failure states. | CLI completes a matched synthetic case, blocks the supplied mismatch, and exposes missing/conflicting evidence. No invalid citation can produce a successful finding. | M1 and M2 |
| M4 Review interface | Build upload, request summary, applicability result, grouped checklist, source-page viewer, issue details, export, and retry of a failed run. | A saved browser test uploads documents, opens a citation, sees a gap, and exports a traceable result. A failed dependency is understandable without reading server logs. | M3 |
| M5 Evaluation and hardening | Run the [evaluation matrix](evaluation.md). Test changed policy, second policy family, explicit scan rejection, long input, malformed model output, retries, and process interruption. Fix errors and rerun affected cases. | Mandatory deterministic checks pass; semantic cases have reviewed outcomes; critical unsupported findings are zero on the release set. Publish counts and failures as well as successes. | M3 and M4 |
| M6 Reviewer delivery | Package the container, exact prerequisites, one-line command, known limits, example files, design note, and a short demonstration script. Test a fresh checkout and a separately held-out document pair. | A clean environment launches and processes live new inputs with documented credentials. Export identifies the model and source versions. Deliver the code at least one day before the call. | M5 |

M1 and the native PDF experiments in M2 can proceed in parallel after M0. Final input limits combine parser and model findings before M3 completion. Assign ownership of shared schemas before parallel implementation. Integrate contracts first and run end-to-end checks after changes merge; individually passing branches do not prove a working combined product.

## Planned repository structure

Create these application directories with their first implementation changes, rather than filling the repository with empty packages now. The domain modules remain independent of HTTP and the model provider.

```text
backend/
  pyproject.toml
  app/
    api/                 Upload, assessment, source, and export endpoints
    schemas/             Request, document, policy, evidence, and run contracts
    documents/           Native parser, quality checks, explicit input limits
    policies/            Scope, criteria, and logical node validation
    evidence/            Chart facts, negation, dates, and source matching
    assessment/          Workflow, rule evaluator, issue and result aggregation
    llm/                 OpenAI adapter and versioned prompts
    storage/             SQLite metadata and artifact storage adapters
    observability/       Stage timings, token usage, and failure records
frontend/
  e2e/                   Saved browser journeys
  src/
    features/upload/
    features/review/
    features/sources/
    components/
tests/
  unit/                  Rule semantics, provenance, and state transitions
  integration/           Parsing, persistence, APIs, and provider contracts
  fixtures/              Fictional inputs and recorded provider responses
evals/
  cases/                 Development and held-out manifests
  expected/              Reviewed criteria, evidence, and findings
  results/               Versioned aggregate reports without credentials
scripts/                 Launch and evaluation entry points
docs/                    Requirements, decisions, research, and design note
examples/                Supplied and clearly labeled fictional documents
Dockerfile
compose.yaml
.env.example
```

Actual deviations from this plan: there is no separate `app/observability/` module — usage lives on `RunRecord.usage`/`StageUsage`; the frontend organizes review views under `src/components/` rather than `src/features/*`; and shared test/fixture support lives in `tests/support.py` and `tests/e2e/` rather than the sketched layout.

## Reviewer launch contract

The target command is `docker compose up --build`, after the documented prerequisite setup. The container now serves the full UI and API and starts processing once `OPENAI_API_KEY`/`AIRA_MODEL` are configured; the live path remains unverified under the deferred quota. Build the React assets into the application image, serve them from FastAPI on one documented port, and persist local data through a volume. Keep parser dependencies in the image and lock Python and JavaScript dependencies.

Live inference requires a server-side `OPENAI_API_KEY` with access to the explicitly configured `AIRA_MODEL`. Verify this configuration inside the backend container. Document nonsecret settings and input limitations in `.env.example`; do not put keys in the repository, frontend build variables, prompts, exports, or logs. Model access and configuration remain M1 verification outcomes. Do not depend on the author's laptop services, private registry, local LLM gateway, or personal browser session.

A credential-free fixture mode may support deterministic tests. It must be labeled as fixture execution and must not stand in for the required live upload workflow. The application should start far enough to explain missing configuration; live assessment must not silently fall back to canned answers.

## Engineering practices

Use one small set of repository instructions, typed contracts, and explicit acceptance cases. The vault's engineering notes consistently favor observable results over claims of completion: run the build, inspect the diff, verify the evidence, and test behavior rather than implementation details.

For this project that means:

- Preserve original input bytes and page identity. Resolve citations against actual extracted spans; schema-valid text is not proof of evidence.
- Keep extraction failures and model failures separate from missing clinical documentation. Carry unresolved reasons through aggregation.
- Version prompts, schemas, model configuration, parser configuration, and input hashes. A changed dependency creates a new run and triggers relevant evaluations.
- Test pure logic directly, exercise storage/provider boundaries with controlled responses, and verify user workflows with saved browser tests. Do not use a coverage percentage as the product acceptance criterion.
- Log stage durations, retries, token usage, failure category, and a run identifier. Measure actual bottlenecks before introducing workers, retrieval, or caching.
- Use bounded calls and explicit timeouts. Persist useful completed artifacts and present interruption honestly. Do not report success from partial extraction.
- Inspect changes and generated test expectations. A failed case cannot be fixed by silently changing its expected answer.

The Obsidian review contained useful engineering experience, some older proposals, and a PDF testing stub. Its private source register remains in the vault. Project decisions use the transferable practices. The [model provider decision](model-provider.md) defines the active integration and required API verification; [AWS research](aws.md) retains dated findings for possible future use. Historical thresholds, costs, and infrastructure details are not defaults for Aira.

## Risks and decision gates

| Risk | Detection | Response |
| --- | --- | --- |
| Policy interpretation loses an exception or branch. | Compare annotated requirements and rule edges with source pages; test branch-specific counterexamples. | Keep unresolved language visible; narrow the supported operation set instead of guessing. |
| Evidence looks plausible but does not support the finding. | Exact-span checks plus reviewed semantic expectations and unrelated-evidence controls. | Reject invalid citations; mark unsupported interpretation for review. |
| Model access blocks the reviewers. | Run M1 from the documented credential path before accepting live integration or release. | Continue independent implementation/tests while quota is deferred; resolve access before delivery without substituting fixtures. |
| Native extraction loses layout or encounters an unsupported scan. | Rendered-page checks and labeled table/column/mixed-page cases. | Preserve layout, explicitly reject unusable pages, and disclose the tested document envelope. |
| Context or cost grows with long charts. | Record page/token counts and per-stage usage; test length limits. | Reject unsupported size clearly, then evaluate section retrieval with evidence-recall checks. |
| Infrastructure work displaces the product. | Compare each task against assessment acceptance cases. | Keep deployment, managed queues, and policy search out of the critical path. |
| Shared work changes a decision without integration checks. | Review architecture changes and merged tests against this plan. | Record the reason for changed decisions and rerun dependent scenarios. |

Before release, resolve the exact model/API configuration, credential onboarding, tested document limits, scan rejection behavior, and the held-out case outcome. These are bounded implementation questions, not reasons to postpone the initial extraction experiment.

## Interview preparation

The final short design note should be written from the implementation and measured outcomes. Explain why the scope is one request against one policy, why applicability precedes evaluation, how policy data differs from code, where model and staff judgment remain, what the sample mismatch revealed, and what failed during evaluation. Demonstrate a successful case and a useful failure. Describe a later hosting option and the evidence that would justify adding retrieval or a more complex workflow.
