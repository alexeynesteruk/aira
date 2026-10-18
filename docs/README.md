# Aira project documentation

Build a small, working assistant that helps clinic staff assess prior authorization readiness using a patient chart PDF and an insurer guideline PDF. It must work on new documents supplied by reviewers. The implementation direction is a cited evidence checklist using FastAPI, React/TypeScript, and the OpenAI Responses API, with a local one-command launch.

Requirements, architecture, and task decomposition are documented. The full non-live stack — PDF intake, storage, stage interpreter, workflow, HTTP API, exports, and the review UI — is implemented and passes deterministic, controlled-interpreter, and fixture-interpreter checks in CI. Live inference remains blocked by API project quota and was deferred by the user. Start with the [business and technical requirements](requirements/README.md), then use the [work breakdown](work-breakdown.md) to execute the plan.

## Confirmed requirements

Source: [build case, page 1](sources/Aira_FDE_Build_Case.pdf). The delivery logistics also come from the accompanying assessment email.

| Area | Requirement |
| --- | --- |
| Problem | Reduce staff effort preparing requests and reduce denials caused by missed medical necessity requirements. |
| Setting | A Florida vascular surgery practice; more than half of patients have BCBS Florida coverage. |
| Guideline input | Accept new guidelines as PDF uploads. The example is not a fixed boundary. |
| Patient input | Accept patient chart PDFs, including patients not seen during development. Synthetic examples are allowed. |
| Product | A working, narrow MVP that runs end to end on real inputs. Scope is ours to define. |
| Runtime | A one-line command on the reviewers' machine, tested from a clean checkout. |
| Stack | Any stack. Aira uses Python, FastAPI, React, TypeScript, and Postgres; these are not mandated. |
| Submission | Code as a repository or zip, sent one day before the call. |
| Design note | Explain where judgment lives, what is data versus code, and what breaks first with guideline changes or messy charts. |
| Discussion | A 45-minute call about the reviewers' findings, assumptions, tradeoffs, failures, and how to extend the MVP. |
| Explicit exclusions | Do not spend time on compliance, security, infrastructure, HIPAA, or PHI handling. |

## Chosen MVP

Assess one selected procedure request against one uploaded policy version. Extract scope, retain the policy's logical relationships, match chart evidence, and show a checklist with source-page navigation and unresolved documentation needs. Stop on a known policy mismatch and request clarification when scope is uncertain.

Missing documentation, contrary evidence, conflicting facts, unsupported interpretation, and processing failures remain distinct. A satisfied subset of extracted rules cannot override a known omitted governing condition. Staff resolve uncertainty; the product does not issue an insurer approval or denial.

The supplied chart is a UHC pacemaker request, while the example guideline concerns BCBS Florida vein treatment. That pair is an applicability test. Matched fictional cases and a second policy family are necessary to test the full workflow.

## Business requirements at a glance

Statuses derive from the [work breakdown](work-breakdown.md): **implemented and deterministically verified** (unit/integration/fixture checks), **implemented, live-unverified** (awaiting restored OpenAI quota), or **open**.

| BR | Requirement | Status |
| --- | --- | --- |
| BR-001 | New guideline and chart uploads drive results | implemented and deterministically verified |
| BR-002 | One selected request with relevant side and dates | implemented and deterministically verified |
| BR-003 | Policy applicability gate stops/clarifies mismatches | implemented and deterministically verified |
| BR-004 | Faithful, complete policy requirements (AND/OR, blockers) | implemented and deterministically verified |
| BR-005 | Distinct evidence states, never conflated with failure | implemented and deterministically verified |
| BR-006 | Inspectable exact policy and chart citations | implemented and deterministically verified |
| BR-007 | Actionable gaps and provenance-preserving clarification | implemented and deterministically verified |
| BR-008 | Saved assessments and versioned exports | implemented and deterministically verified |
| BR-009 | Progress and useful failure recovery | implemented and deterministically verified |
| BR-010 | One-command live reviewer workflow | implemented, live-unverified (quota deferred) |
| BR-011 | Generality and independent evaluation | open — corpus built; live semantic evaluation not run |
| BR-012 | Submission and design discussion | open — [design-note draft](design-note.md) exists |

## Documentation guide

| Document | Purpose |
| --- | --- |
| [Business requirements](requirements/business-requirements.md) | Staff outcomes, stakeholders, scope, business rules, and BR-001–BR-012. |
| [Technical requirements](requirements/technical-requirements.md) | Testable system requirements, API/error contracts, and BR/TR/acceptance traceability. |
| [Implementation plan](implementation-plan.md) | Product scope, decisions, M0–M6 milestones, planned folders, reviewer launch, risks, and delivery. |
| [Work breakdown](work-breakdown.md) | Assignable packages, dependencies, deliverables, owner roles, and completion evidence. |
| [Feature specifications](features/README.md) | One file per package, with business/technical requirements, implementation tasks, acceptance checks, and source references. |
| [Technical design document (TDD)](architecture.md) | Current implementation snapshot, system architecture, component boundaries, runtime diagrams, data model, evidence logic, and storage. |
| [Evaluation](evaluation.md) | Acceptance scenarios, independent expectations, test layers, metrics, and release blockers. |
| [Contract record](contracts.md) | Schema version baseline, contract examples, and verified amendment history. |
| [Decision record](decisions.md) | Architectural and technical decisions (AD/TD), rationale, and status. |
| [Design note](design-note.md) | Submission note: where judgment lives, data vs code, and what breaks first. |
| [Extraction record](results/pdf-extraction.md) | Verified native-PDF intake/extraction behavior, limits, and failures. |
| [Storage record](results/storage.md) | Verified SQLite/immutable-object storage boundary and cache identity. |
| [Rules record](results/rules.md) | Verified pure provenance validation, bounded predicates, and aggregation. |
| [Workflow record](results/workflow.md) | Controlled-interpreter evidence for the bounded execution engine. |
| [Stage interpreter record](results/stage-interpreter.md) | Production interpreter and CLI slice over mocked transport; no live calls. |
| [HTTP API record](results/http-api.md) | API routes, startup/readiness wiring, and export routes under controlled evidence. |
| [Input limits record](results/input-limits.md) | Declared native-text boundary, parser/API limit evidence, and the open token envelope. |
| [Review UI record](results/review-ui.md) | Saved staff journeys and unit checks over the fixture interpreter. |
| [WP-03 fixture review](reviews/wp03-fixtures.md) | Independent review of the annotated fixture corpus. |
| [Implementation handoff](agent-handoff.md) | Entry point, current boundaries, and evidence rules. |
| [Model provider decision](model-provider.md) | OpenAI integration, server-side configuration, and native PDF boundary. |
| [Model feasibility record](results/model-feasibility.md) | Implemented adapter/CLI, controlled checks, observed quota failure, and commands to resume live validation. |
| [AWS research](aws.md) | Dated service findings and the superseded Bedrock proposal, retained as future options. |
| [Online implementation research](research.md) | Reddit workflow observations, public implementations, PDF tooling, and design tradeoffs. |
| [Document exploration](exploration.md) | Sample mismatch, source evidence, chronology conflicts, and extraction risks. |
| [Guideline provenance](../examples/guidelines/README.md) | Two exact policy snapshots, hashes, and observed differences. |

The Obsidian review informs engineering practices such as versioned prompts, independent test expectations, source verification, and honest failure reporting. Its detailed private source register stays in the vault. The active provider boundary is recorded in the model decision; the AWS research retains the dates and sources of its earlier verification.

## Next implementation gate

WP-01–WP-15's non-live work and WP-16/WP-17's deterministic halves are done; their [completion evidence](work-breakdown.md#implementation-evidence) identifies commits and result records. The [feature index](features/README.md) links each implementation brief. The remaining work is live-gated: WP-05 model selection, WP-07–WP-09 semantic acceptance, the WP-11 live CLI run, the WP-15 measured token envelope, WP-16's live evaluation report, and WP-17/WP-18's live container and clean-checkout checks. Unsupported scans are explicitly rejected in the initial MVP; no AWS credentials or deployment are needed. Infrastructure, EHR integration, and payer submission remain outside the take-home scope.
