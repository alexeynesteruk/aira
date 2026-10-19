# Aira project documentation

Build a small, working assistant that helps clinic staff assess prior authorization readiness using a patient chart PDF and an insurer guideline PDF. It must work on new documents supplied by reviewers. The implementation direction is a cited evidence checklist using FastAPI, React/TypeScript, and the OpenAI Responses API, with a local one-command launch.

Requirements, architecture, and task decomposition are documented. Earlier PDF intake, storage, workflow, API, exports, and review UI components have recorded deterministic/fixture evidence. The current independent-extraction refactor and new WP-19 long-document feature still need integrated verification; historical CI results do not establish that the present working tree passes. Live inference remains blocked by API project quota and was deferred by the user. Start with the [business and technical requirements](requirements/README.md), then use the [work breakdown](work-breakdown.md) to execute the plan.

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
| Stack | Any stack. Aira uses Python, FastAPI, React, TypeScript, and SQLite; these are not mandated. |
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
| BR-004 | Faithful, complete policy requirements (AND/OR, blockers) | deterministic foundations verified; source fidelity and long-document compilation remain open |
| BR-005 | Distinct evidence states, never conflated with failure | implemented and deterministically verified |
| BR-006 | Inspectable exact policy and chart citations | implemented and deterministically verified |
| BR-007 | Actionable gaps and provenance-preserving clarification | implemented and deterministically verified |
| BR-008 | Saved assessments and versioned exports | implemented and deterministically verified |
| BR-009 | Progress and useful failure recovery | implemented and deterministically verified |
| BR-010 | One-command live reviewer workflow | implemented, live-unverified (quota deferred) |
| BR-011 | Generality and independent evaluation | open — corpus built; live semantic evaluation not run |
| BR-012 | Submission and design discussion | open — [design-note draft](design-note.md) exists |
| BR-013 | Complete 100–200-page guideline preparation and durable independent reuse | specified in WP-19; implementation/live acceptance open |

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
| [Candidate conversion record](results/candidate-conversion.md) | Verified provider-candidate conversion, date-confirmation semantics, and conversion failure phases. |
| [Workflow record](results/workflow.md) | Controlled-interpreter evidence for the bounded execution engine. |
| [Stage interpreter record](results/stage-interpreter.md) | Production interpreter and CLI slice over mocked transport; no live calls. |
| [HTTP API record](results/http-api.md) | API routes, startup/readiness wiring, and export routes under controlled evidence. |
| [Input limits record](results/input-limits.md) | Declared native-text boundary, parser/API limit evidence, and the open token envelope. |
| [Review UI record](results/review-ui.md) | Saved staff journeys and unit checks over the fixture interpreter. |
| [Independent extraction record](results/independent-extraction.md) | Verified separation of guideline and chart document builds, artifact reuse, and saved-fact mapping. |
| [WP-03 fixture review](reviews/wp03-fixtures.md) | Independent review of the annotated fixture corpus. |
| [Implementation handoff](agent-handoff.md) | Entry point, current boundaries, and evidence rules. |
| [Project notes](project-notes.md) | Comprehensive orientation notes: architecture, module map, semantics, limits, status, and observed check results. |
| [Model provider decision](model-provider.md) | OpenAI integration, server-side configuration, and native PDF boundary. |
| [Model feasibility record](results/model-feasibility.md) | Implemented adapter/CLI, controlled checks, observed quota failure, and commands to resume live validation. |
| [Long-document feature](features/19-long-document-rule-compilation.md) | BR-013/TR-019/WP-19/A21, LD-01–LD-10 tasks, and LD-AC01–LD-AC12 acceptance. |
| [Long-document implementation plan](plans/long-document-rule-compilation.md) | Target contracts, structural extraction/reconciliation algorithm, failure/reuse semantics, execution slices, and delivery checks. |
| [WP-19 specification record](results/wp19-specification.md) | Documentation delivery and actual working-tree check results; runtime acceptance remains open. |
| [Long-document research log](research/long-document-rule-extraction.md) | Dated primary-source findings, Aira-specific decisions, limitations, and next experiments. |
| [Online implementation research](research.md) | Reddit workflow observations, public implementations, PDF tooling, and design tradeoffs. |
| [Document exploration](exploration.md) | Sample mismatch, source evidence, chronology conflicts, and extraction risks. |
| [Guideline provenance](../examples/guidelines/README.md) | Two exact policy snapshots, hashes, and observed differences. |

The Obsidian review informs engineering practices such as versioned prompts, independent test expectations, source verification, and honest failure reporting. Its detailed private source register stays in the vault. The active provider boundary is recorded in the model decision.

## Next implementation gate

Start the long-document work from [WP-19](features/19-long-document-rule-compilation.md) and its [implementation plan](plans/long-document-rule-compilation.md). Implement the LD-01–LD-10 slices and A21 checks before claiming complete long-guideline support. Independent policy/chart preparation and the page-fold prototype are present in the unfinished working tree, with coverage, reconciliation, scoped compilation, durable build/UI integration, and direct-OpenAI acceptance still requiring evidence.

Historical core [completion evidence](work-breakdown.md#implementation-evidence) identifies commits and result records. The [feature index](features/README.md) links each implementation brief. All deterministic construction-ledger tasks (including FT-07 runtime counterexamples, FT-13 long-chart distractor variants, and FT-14 multiple-procedure/conflicting-annotation cases) are completed and verified. Earlier live-dependent gates remain deferred under project quota exhaustion: WP-05 model selection, WP-07–WP-09 semantic acceptance, the WP-11 live CLI run, the WP-15 measured token envelope, WP-16's live evaluation report, and WP-17/WP-18's live launch and clean-checkout checks. Unsupported scans are explicitly rejected in the initial MVP. Infrastructure, EHR integration, and payer submission remain outside the take-home scope.
