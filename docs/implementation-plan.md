# Aira implementation plan

Build a provider-facing assistant that compares one selected procedure request with an uploaded insurer policy and returns a checklist of documented requirements, contrary evidence, and gaps. Staff must be able to open the supporting policy and chart passages for each finding. The product reports documentation readiness; it does not issue a payer decision.

The chosen direction is Python, FastAPI, React, TypeScript, Pydantic, and AWS Bedrock, with a local container launch for assessment reviewers. AWS is the preferred cloud platform. The assessment explicitly excludes infrastructure work, so an AWS deployment is an extension rather than a prerequisite for running the application. The exact Bedrock model and OCR release scope depend on the experiments below.

Status on October 17, 2026: requirements and research are complete enough to start the first experiment. Application code, model benchmarks, live AWS access checks, and the launch command have not been implemented or verified. [Architecture](architecture.md) defines the contracts; [evaluation](evaluation.md) defines the acceptance cases; [AWS research](aws.md) records service constraints.

## Product scope

The MVP handles one guideline PDF and one chart PDF per assessment, and one selected procedure request. A document may contain multiple clinical problems or procedure options; the user selects the request when extraction cannot resolve it unambiguously. Supporting multiple uploads, longitudinal patient folders, and automatic policy discovery can follow later.

The initial user journey is:

1. Upload the policy and chart. Enter or confirm the requested procedure, payer and plan, and service date when those are ambiguous or absent. Retain user corrections as annotations alongside the extracted source.
2. See extraction progress and any unreadable pages. Inspect the selected documents, policy revision, and request summary.
3. Review applicability. A confirmed payer or procedure mismatch stops assessment. An uncertain plan, date, or policy scope requires clarification; an upload does not prove the policy applies.
4. Inspect requirements grouped according to the policy's AND/OR structure. Each finding displays the requirement, its policy citation, chart evidence, and the reason for its status.
5. Open either source at the cited page. Review missing documentation, conflicts, and unsupported interpretation. Suggested next steps request clarification or documentation without inventing clinical facts or treatment advice.
6. Save or export the assessment as structured JSON and a readable checklist, including unresolved issues and the exact policy version. Re-running with a changed input creates a new result.

Include source inspection, meaningful processing states, and useful failure messages in the first vertical slice. Defer chat, autonomous agents in the application, automatic appeals or submission letters, payer portals, EHR/FHIR connections, policy web crawling, vector databases, and production infrastructure. Research agents help review the design; the application executes an explicit staged workflow.

## Decisions and remaining experiments

| Decision | Direction | Evidence or condition |
| --- | --- | --- |
| Core workflow | Applicability, policy requirements, evidence, deterministic aggregation, staff review. | Matches the assessment and recurring public implementation pattern. |
| Platform | Bedrock for model inference; portable local application runtime. | User preference for AWS plus the clean-checkout requirement. |
| Application stack | FastAPI, React and TypeScript, Pydantic, Python tests and saved browser tests. | Fits Aira's stated stack and the domain contracts. |
| Persistence | SQLite metadata and local document/artifact files in a mounted data directory. | A single local reviewer needs durable runs without extra services. |
| PDF extraction | Native text and layout extraction first; page-level quality checks. | Supplied documents have text but include layout and chronology traps. |
| OCR | Evaluate pagewise synchronous Textract on scanned and mixed PDFs; implement only if its setup and failure handling fit the assessment. | Byte input avoids a required S3/job-notification stack. M2 must choose verified OCR support or an explicit scan limitation. Never silently skip a page. |
| Context | Full page-tagged documents when within measured limits. | Establish an evidence-recall baseline before adding retrieval. Reject oversized input visibly until a tested section strategy exists. |
| Model | Configurable Bedrock model or inference profile; select one tested default. | M1 compares compatible candidates on quality, latency, access, and cost. No model quality claim yet. |
| Policy logic | Flat logical nodes referencing criteria; local structural validation and evaluation. | Avoid recursive wire schemas and preserve nested policy conditions. |
| Scope generality | Two policy families, new patient charts, and an unseen pair in the final evaluation. | Vein-only templates would not satisfy the assessment's generality requirement. |

Revision date and effective date are different fields. Preserve both when present. The two BCBS snapshots demonstrate version changes, but their revision dates alone do not prove which version governs a service. Unsupported policy language remains a review item instead of being compiled into a guessed rule.

## Implementation sequence

Work in small changes with an executable exit check. A milestone is complete only when its artifact and check exist; this table records the planned work, not completed delivery.

| Milestone | Build and deliver | Exit check | Depends on |
| --- | --- | --- | --- |
| M0 Contracts and expectations | Finalize request scope, rule states, schemas, annotated policy passages, fictional chart fixtures, and expected outcomes. Select a second policy family. Record input provenance and separate development from held-out cases. | A reviewer can explain expected branches and cited evidence without running a model. No unresolved requirement is hidden in a fixture. | Current research |
| M1 Bedrock feasibility | Add the smallest provider adapter and a CLI experiment for policy and chart extraction. Compare two available candidates where access permits; otherwise document the single-model limitation. Pin the selected model/profile, region, prompt, schema, and inference settings. | A real call from a reviewer-like environment produces validated structured output and page citations. Missing access, unsupported schema, refusal, and timeout are visible errors. Record tokens, latency, and configuration. | M0 |
| M2 PDF feasibility | Implement document hashing, page/block extraction, coordinates, and native-text quality checks. Inspect columns and tables against rendered pages. Trial OCR for scans and mixed pages; make the OCR scope decision. | The supplied dates, units, negation, tables, and page-spanning passages survive extraction. Every page is accounted for; bad input produces an actionable state. | M0; OCR requires AWS access |
| M3 End-to-end workflow | Implement scope checking, policy and chart extraction, evidence matching, provenance validation, rule aggregation, and persisted run artifacts. Add bounded stage execution and explicit failure states. | CLI completes a matched synthetic case, blocks the supplied mismatch, and exposes missing/conflicting evidence. No invalid citation can produce a successful finding. | M1 and M2 |
| M4 Review interface | Build upload, request summary, applicability result, grouped checklist, source-page viewer, issue details, export, and retry of a failed run. | A saved browser test uploads documents, opens a citation, sees a gap, and exports a traceable result. A failed dependency is understandable without reading server logs. | M3 |
| M5 Evaluation and hardening | Run the [evaluation matrix](evaluation.md). Test changed policy, second policy family, OCR or explicit rejection, long input, malformed model output, retries, and process interruption. Fix errors and rerun affected cases. | Mandatory deterministic checks pass; semantic cases have reviewed outcomes; critical unsupported findings are zero on the release set. Publish counts and failures as well as successes. | M3 and M4 |
| M6 Reviewer delivery | Package the container, exact prerequisites, one-line command, known limits, example files, design note, and a short demonstration script. Test a fresh checkout and a separately held-out document pair. | A clean environment launches and processes live new inputs with documented credentials. Export identifies the model and source versions. Deliver the code at least one day before the call. | M5 |

M1 and M2 can proceed independently after M0. Assign ownership of shared schemas before parallel implementation. Integrate contracts first and run end-to-end checks after changes merge; individually passing branches do not prove a working combined product.

## Planned repository structure

Create these application directories with their first implementation changes, rather than filling the repository with empty packages now. The domain modules remain independent of HTTP and the model provider.

```text
backend/
  pyproject.toml
  app/
    api/                 Upload, assessment, source, and export endpoints
    schemas/             Request, document, policy, evidence, and run contracts
    documents/           Native parser, quality checks, optional OCR adapter
    policies/            Scope, criteria, and logical node validation
    evidence/            Chart facts, negation, dates, and source matching
    assessment/          Workflow, rule evaluator, issue and result aggregation
    llm/                 Bedrock adapter and versioned prompts
    storage/             SQLite metadata and artifact storage adapters
    observability/       Stage timings, token usage, and failure records
frontend/
  src/
    features/upload/
    features/review/
    features/sources/
    components/
tests/
  unit/                  Rule semantics, provenance, and state transitions
  integration/           Parsing, persistence, APIs, and provider contracts
  e2e/                   Saved user journeys
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

## Reviewer launch contract

The target command is `docker compose up --build`, after the documented prerequisite setup. It is a delivery target, not a working command in the current repository. Build the React assets into the application image, serve them from FastAPI on one documented port, and persist local data through a volume. Keep parser dependencies in the image and lock Python and JavaScript dependencies.

Live inference requires an AWS account with access to the selected Bedrock model/profile and configured credentials. Use the SDK credential chain with a documented profile or short-lived environment credentials; support session tokens. Verify the chosen path inside the container, including any required profile/config mounts. Document region, model identifier, and OCR configuration in `.env.example` without secrets. Do not depend on the author's laptop services, private registry, local LLM gateway, or personal browser session.

A credential-free fixture mode may support deterministic tests. It must be labeled as fixture execution and must not stand in for the required live upload workflow. The application should start far enough to explain missing configuration; live assessment must not silently fall back to canned answers.

## Engineering practices

Use one small set of repository instructions, typed contracts, and explicit acceptance cases. The vault's engineering notes consistently favor observable results over claims of completion: run the build, inspect the diff, verify the evidence, and test behavior rather than implementation details. Independent agent review supplements those checks.

For this project that means:

- Preserve original input bytes and page identity. Resolve citations against actual extracted spans; schema-valid text is not proof of evidence.
- Keep extraction failures and model failures separate from missing clinical documentation. Carry unresolved reasons through aggregation.
- Version prompts, schemas, model configuration, parser configuration, and input hashes. A changed dependency creates a new run and triggers relevant evaluations.
- Test pure logic directly, exercise storage/provider boundaries with controlled responses, and verify user workflows with saved browser tests. Do not use a coverage percentage as the product acceptance criterion.
- Log stage durations, retries, token usage, failure category, and a run identifier. Measure actual bottlenecks before introducing workers, retrieval, or caching.
- Use bounded calls and explicit timeouts. Persist useful completed artifacts and present interruption honestly. Do not report success from partial extraction.
- Inspect changes and generated test expectations. A failed case cannot be fixed by silently changing its expected answer.

The Obsidian review contained useful engineering experience, some older proposals, and a PDF testing stub. Its private source register remains in the vault. Project decisions use the transferable practices, while current service behavior is verified against [AWS documentation](aws.md). Historical thresholds, costs, and infrastructure details are not defaults for Aira.

## Risks and decision gates

| Risk | Detection | Response |
| --- | --- | --- |
| Policy interpretation loses an exception or branch. | Compare annotated requirements and rule edges with source pages; test branch-specific counterexamples. | Keep unresolved language visible; narrow the supported operation set instead of guessing. |
| Evidence looks plausible but does not support the finding. | Exact-span checks plus reviewed semantic expectations and unrelated-evidence controls. | Reject invalid citations; mark unsupported interpretation for review. |
| AWS access blocks the reviewers. | Run M1 from the documented credential path before building the rest of the app. | Resolve model access and onboarding before delivery; do not hide it with fixtures. |
| OCR produces correct words in the wrong order. | Rendered-page checks and labeled table/column cases. | Preserve layout; route uncertain pages to review; disclose the tested document envelope. |
| Context or cost grows with long charts. | Record page/token counts and per-stage usage; test length limits. | Reject unsupported size clearly, then evaluate section retrieval with evidence-recall checks. |
| Infrastructure work displaces the product. | Compare each task against assessment acceptance cases. | Keep deployment, managed queues, and policy search out of the critical path. |
| Shared work changes a decision without integration checks. | Review architecture changes and merged tests against this plan. | Record the reason for changed decisions and rerun dependent scenarios. |

Before release, resolve the exact model/region, credential onboarding, tested document limits, OCR inclusion, and the held-out case outcome. These are bounded implementation questions, not reasons to postpone the initial extraction experiment.

## Interview preparation

The final short design note should be written from the implementation and measured outcomes. Explain why the scope is one request against one policy, why applicability precedes evaluation, how policy data differs from code, where model and staff judgment remain, what the sample mismatch revealed, and what failed during evaluation. Demonstrate a successful case and a useful failure. Describe the next AWS deployment step and the evidence that would justify adding retrieval or a more complex workflow.
