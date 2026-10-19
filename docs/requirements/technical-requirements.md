# Aira technical requirements

Implement a local application that assesses one selected procedure request against one uploaded policy and one chart PDF. The system must preserve source evidence, expose uncertainty, and produce a documentation checklist without issuing an insurer decision. These requirements translate the [business requirements](business-requirements.md) into implementation and acceptance contracts.

Updated October 18, 2026. This technical requirements document (TRD) retains TR-001–TR-018 identifiers and adds TR-019 for the user-authorized long-document compilation feature. M0–M6 in the [implementation plan](../implementation-plan.md) group delivery, and the [work breakdown](../work-breakdown.md) records actual dependencies and completion evidence. The [technical design document (TDD)](../architecture.md) defines architecture, domain semantics, and the current implementation snapshot. The [model provider decision](../model-provider.md) defines the OpenAI boundary, and the [evaluation matrix](../evaluation.md) identifies acceptance scenarios A01–A20. A deferred quota issue blocks live validation, not the requirements themselves.

## Implementation boundaries

| Area | Required direction |
| --- | --- |
| Backend | Python, FastAPI, strict Pydantic contracts, and domain modules independent of HTTP, storage, and provider adapters. |
| Frontend | React and TypeScript, with built assets served by the application. |
| Inference | A thin OpenAI Responses API adapter using an explicit model and structured-output mechanism verified in M1. |
| Documents | Native page-aware text/layout extraction; scans and unusable image-only pages receive an explicit unsupported-input response in the initial MVP. |
| Persistence | SQLite metadata and immutable input/stage artifacts in a local data directory. |
| Execution | One application process with a bounded executor and persisted run state. No distributed queue is assumed. |
| Delivery | A one-line local launch with documented OpenAI key/model prerequisites and no author-specific services. |

All numbered requirements are product obligations; TR-019 is the October 18 long-document extension and its release gates remain open. TR-003 requires a verified native-text input boundary and explicit scan rejection; adding OCR requires a justified scope change and its own verification. Hosted object storage, a shared database, queues, managed retrieval, EHR connections, and payer submission are possible extensions. Production compliance and infrastructure work remain outside the assessment scope.

## Technical requirements

### TR-001 PDF intake and page inventory

**Business mapping:** BR-001, BR-009.

Accept one PDF upload at a time with an explicit `policy` or `chart` role. Validate the actual document format, readability, encryption restrictions, byte limit, and page limit before assessment. Assign an application document ID and inventory every one-based PDF page, including blank or suspect pages. An assessment references exactly one document of each role. Reject unsupported input with a specific reason; a filename extension alone is insufficient validation.

**Acceptance:** A14 verifies valid, malformed, encrypted, blank, oversized, and mixed-page inputs. Every accepted PDF has a complete page inventory. Invalid files and incorrect document-role combinations cannot start inference; limit failures identify the applicable limit.

### TR-002 Immutable sources and layout extraction

**Business mapping:** BR-001, BR-006, BR-008.

Preserve original bytes and SHA-256, then store versioned page/block extraction separately. Retain text, source page, reading order, table associations, extraction method, quality issues, and coordinates where available. A source span identifies its document, extraction revision, page, block or offsets, and excerpt. Cross-page evidence consists of multiple explicit spans. Changes to extraction must not replace artifacts used by an existing run.

**Acceptance:** A05, A13, and A17 preserve the supplied chart's dates, negation, table labels/values, and page-spanning sections. Source inspection opens the original page associated with each span. Reprocessing creates a distinct extraction revision and leaves prior run citations resolvable.

### TR-003 OCR support and input limits

**Business mapping:** BR-001, BR-009.

M2 must establish native extraction quality and measured input limits. The initial MVP rejects scanned, image-only, or otherwise unusable pages explicitly rather than treating missing extracted text as absent clinical evidence. Inventory every page of mixed documents before assessment. OCR may be added later only when representative inputs justify it and its extraction, page mapping, provenance, resource limits, and failure behavior are verified. Any future OCR output must remain distinguishable from native extraction.

The initial parser is conservative: any embedded raster image, including a decorative image on a text page, is unsupported because its relevance cannot be established without image interpretation. Rotated pages, interactive forms, and vector-only nontext pages are also outside the current native path. This boundary must be visible before an ordinary assessment can complete. Parser byte/page/character budgets are provisional until WP-15 combines extraction results with live model limits; the existence of parser limits does not establish an end-to-end supported envelope.

TR-019 adds a 100/200-page native-guideline target. Measure and amend intake/parser limits and total model budgets together before claiming support; preserving an earlier 100-page limit cannot satisfy the 200-page acceptance case.

**Acceptance:** A14 covers a full scan, a mixed PDF, and unusable extraction. Every page is either successfully represented, explicitly identified as blank, or reported unusable. An unusable page blocks ordinary assessment completion, and unsupported scans receive a clear response. Cross-page reconstruction is checked under A13. Any later OCR scope must add failure tests before claiming scan support. See the [PDF support boundary](../model-provider.md#pdf-support-and-future-options).

### TR-004 Request context and user annotations

**Business mapping:** BR-002, BR-007.

Represent one selected procedure, available code, anatomical target/laterality, payer, plan, proposed service date, and optional assessment cutoff. Preserve unresolved values and their source references. Do not infer a service date from today's date or submission date. Store staff corrections as typed annotations with field, value, origin, and creation time; they must remain distinguishable from chart-derived facts. A clarification starts a new run linked through `parent_run_id`. Editable fields are request metadata. Resolving conflicting metadata requires an explicit selected value and reason while retaining the original source and conflict; clinical evidence changes require a new source document rather than a manual `met` override.

**Acceptance:** A12 requires request selection or clarification for multiple procedures, missing context, and wrong-side evidence. A17 verifies that a changed annotation produces a new assessment identity without modifying the original extraction or prior result. A conflicting annotation preserves source disagreement and its explicit resolution provenance; it cannot silently turn contrary/conflicting clinical evidence into `met` or be attributed to a PDF passage.

### TR-005 Applicability gate

**Business mapping:** BR-003.

Check payer/plan, procedure scope, relevant dates, and applicable restrictions before necessity evaluation. Preserve the policy's revision and effective period as separate fields. A confirmed mismatch ends execution with `completed` status and `applicability_mismatch` outcome; it must not run necessity aggregation. Uncertain request or policy scope ends the attempt in `needs_input`, with the unresolved fields and the clarification needed. Never silently substitute another policy.

**Acceptance:** A01 returns payer/procedure mismatch citations for the supplied chart/policy pair and no coverage conclusion. A10 and A12 verify that revision dates are not invented effective dates and missing plan/date information is not silently treated as a match.

### TR-006 Policy requirements and logical structure

**Business mapping:** BR-004.

Process the complete guideline independently of charts, selected requests, and staff annotations. Extract policy metadata, criteria, governing passages, exclusions, and flat logical nodes of kind `all`, `any`, or `criterion`, with child/criterion IDs and one root per evaluated scope path. Version the existing single-root contract deliberately for whole-guideline paths. Inventory every section as requirements, context, or unresolved interpretation; do not exclude sections because of a particular patient or request. Preserve procedure-specific scope conditions in their branches. Validate unique IDs, references, root, acyclicity, reachability, nonempty groups, and allowed operator arity. Unsupported predicates or conditional exceptions become review issues, not guessed executable rules. Persist the validated rule set by guideline content and policy-extraction version and reuse it across patients, requests, duplicate uploads, and restarts. Human approval records review status separately from technical reuse. For long guidelines, use TR-019's section planning, dependency reconciliation, coverage audit, and compilation. Page excerpts may guide routing but cannot authorize omission. Multiple procedures require source-supported scoped paths; an unrelated satisfied branch cannot establish readiness.

**Acceptance:** A06 preserves branch-specific compression language; A20 blocks favorable readiness when a governing condition is unresolved. Invalid node graphs fail domain validation. A11 handles a second policy family without procedure-specific production code. Annotated evaluation separately checks omitted criteria and incorrect logical edges that structural validation cannot discover.

### TR-007 Evidence facts and uncertainty

**Business mapping:** BR-005.

Extract chart facts in a separate model process receiving only the complete chart, without a guideline, selected request, or staff annotations. Preserve administrative/request facts, proposition, polarity, value/unit, event date, documentation date, anatomical context, and conflicting alternatives. Persist the sourced fact artifact by chart content and chart-extraction version. A later assessment maps only saved facts to the saved rule set; it cannot introduce or rewrite facts. Distinguish a clinician's summary from underlying measurements. Findings use `met`, `not_met`, `missing`, `conflicting`, or `needs_review`, with rationale and references to saved fact IDs. `missing` means relevant documentation was not found in successfully processed input; it must not represent parser or provider failure.

**Acceptance:** A03–A05 and A08 distinguish missing facts, explicit negatives, temporal conflicts, and incompatible units. The chart's normal-CBC summary does not generate absent laboratory values. Opposite-side or post-cutoff evidence cannot silently satisfy the selected requirement. A18 tests evidence among distractors without converting document instructions into application instructions.

### TR-008 Citation and domain validation

**Business mapping:** BR-006.

Validate model output before it becomes an assessment artifact: schema/type checks, reference integrity, page bounds, span membership, and excerpt resolution against the preserved extraction. Allow only documented whitespace normalization; do not fuzzy-match fabricated quotes. Verify values and units used by deterministic predicates against cited evidence. Model output remains a candidate interpretation even after mechanical checks pass.

**Acceptance:** A15 rejects nonexistent pages, invented excerpts, and wrong-document citations. A real but irrelevant quote fails annotated semantic expectations rather than passing merely because it exists. Invalid outputs receive at most one application repair attempt under the stage deadline; persistent failure remains operationally invalid and cannot produce a favorable result.

### TR-009 Deterministic aggregation and blockers

**Business mapping:** BR-004, BR-005.

Map `met` to true, `not_met` to false, and the other finding states to unknown. Evaluate AND/OR using the [defined three-valued semantics](../architecture.md#finding-and-aggregation-semantics). Preserve child findings and unresolved reasons when a group's value is known. Show the supporting path for a satisfied OR group. Unresolved applicability, governing conditions, exclusions, or completeness issues independently block favorable readiness. A source-supported exclusion is required before omitting a branch as inapplicable.

**Acceptance:** A07 covers true/false/unknown combinations, including `false AND unknown` and `true OR unknown`. A06 does not require documentation for every unused OR alternative. A20 prevents a satisfied extracted tree from overriding known unresolved governing prose. No weighted score, criterion percentage, or model confidence controls aggregation.

### TR-010 Model contract and configuration

**Business mapping:** BR-001, BR-010.

Use a thin OpenAI Responses API adapter with versioned prompts, transport schemas, explicit provider/model, inference settings, and SDK dependencies. M1 must verify the actual model/API/schema combination and select a tested configuration; no automatic model choice is considered validated before this experiment. Keep transport/schema checks separate from local domain validation, and use application source fields for citations. Read `OPENAI_API_KEY` only on the server and configure `AIRA_MODEL` explicitly. Never embed the key in frontend assets, prompts, exports, logs, or repository files. Direct OpenAI access using the reviewer's key is required and must work with no running local proxy when the env file does not set `OPENAI_BASE_URL`. An OpenAI-compatible `/v1` endpoint is an explicit env-file setting; a shell-only base URL is not a silent fallback. Inventory, section extraction, reconciliation, audit, repair/retry, assessment, and explicit preflight all follow the selected backend configuration.

**Acceptance:** A16 exercises unsupported schema/model configuration, missing/invalid credentials, access denial, refusal, and incomplete output. A19 includes a real call from the documented server configuration path. Record candidate comparison or the single-model limitation. A fixture provider is labeled test execution and never silently replaces a failed live call. See the [model and configuration contracts](../model-provider.md).

### TR-011 Bounded execution and failure lifecycle

**Business mapping:** BR-009.

Persist status separately from phase using the contracts below. Bound queue size, concurrent runs, call attempts, and stage duration. Retry transient provider errors through one bounded policy; disable overlapping SDK retries when the adapter owns attempts and the total deadline. `needs_input` stops the current attempt. On restart, mark unfinished queued/running work `interrupted`. A user retry or clarification creates a new run with `parent_run_id`; reuse only compatible validated artifacts. TR-019 build execution additionally bounds section fan-out, total calls/tokens/duration, repair/audit iterations, and waiters; failed sections remain operational failures and prevent complete final publication. Persist completed intermediate work for an explicitly linked retry after interruption.

**Acceptance:** A16 verifies bounded timeout/throttling behavior, visible failure category and action, and interruption recovery. No failure is relabeled a clinical finding. A17 verifies that a retry retains the previous run and its diagnostics. Queue saturation is reported immediately, and an accepted job returns its run ID before long processing begins.

### TR-012 Storage identity and cache isolation

**Business mapping:** BR-008.

Store documents, extractions, policies, annotations, runs, and stage artifacts with explicit relationships. A reusable artifact fingerprint includes its source bytes plus relevant parser, prompt, schema, provider/model, SDK, and inference settings; assessment identity also includes request context and annotations. Cache only completed validated artifacts. TR-019 adds immutable section/reconciliation/audit/build artifacts with stage-specific dependencies. Policy keys exclude chart/request/annotations and assessment-only settings; chart keys exclude policy/request/annotations and assessment-only settings. Changed definitions invalidate dependent artifacts. Preserve each reused artifact's actual generation provenance. Keep policy and chart roles scoped to the run, and store actual outputs rather than assuming a fixed temperature reproduces them.

**Acceptance:** A09, A10, and A17 show correct reuse on identical inputs and invalidation after a relevant change. New policy versions never overwrite old results. Duplicate uploads may share immutable bytes while retaining correct document metadata and role relationships. Interrupted writes cannot make an incomplete artifact appear reusable.

### TR-013 HTTP and health contracts

**Business mapping:** BR-001, BR-008, BR-009.

Implement the endpoint and error contracts below with typed request/response schemas exposed through FastAPI's API description. Resolve IDs and document roles before queuing work. Keep liveness independent of the model provider; readiness checks local prerequisites and configuration without billable inference. Explicit live provider preflight is separate from periodic health checks and must expose whether model access was actually verified.

**Acceptance:** Contract tests cover accepted uploads/jobs, wrong roles, unknown IDs, invalid fields, queue saturation, missing configuration, and premature export. A healthy UI remains reachable when model setup is missing. Repeated health checks produce no model calls; a real preflight outcome is labeled with its check time/configuration and cannot be mistaken for a permanent availability guarantee.

Standalone preparation uses these versioned contracts (`schema_version: 0.1.0`, build contract `document-build-v1`):

| Route | Contract |
| --- | --- |
| `POST /api/documents/{document_id}/builds` | Optional `BuildRequest {parent_build_id?, rebuild?}`; 202 `BuildRecord` and `Location`. Queue full: 429; unavailable: 503; wrong parent: 422; unknown document/parent: 404. |
| `GET /api/documents/{document_id}/builds` | `BuildList {builds}` for saved versions; unknown document: 404. |
| `GET /api/builds/{build_id}` | Exact persisted manifest, result, coverage, receipts, configuration/budgets, usage, and diagnostics; unknown: 404. |
| `GET /api/builds/{build_id}/steps/{checkpoint_key}` | This manifest's source-checked intermediate output and generation receipt; unrelated/unknown key: 404. |
| `POST /api/builds/{build_id}/{action}` | `retry`/`rebuild`: 202 linked new attempt; `approve`/`reject`: 200 explicit review of a completed build. Active parent or invalid review state: 409; unknown action/ID: 404. |

`BuildRecord` states are queued → running → completed/failed/interrupted. Failed/interrupted builds have an operational error and no final policy/chart result. A completed policy requires extraction, completed sections, and audited block coverage; technical completion remains distinct from draft/approved/rejected human review. Approval does not clear interpretation blockers. Source pages, rule IDs, named paths, unresolved dependencies, and checkpoint generation settings remain inspectable. Interrupted work requires an explicit linked retry; rebuild bypasses old generation checkpoints. Originals and prior artifacts remain immutable.

Assessment requests accept optional `policy_build_id`/`chart_build_id` pinned to completed, non-rejected versions of those exact uploads. Submitted pins participate in input identity. Auto-prepared versions are recorded on the run; clarification inherits matching parent pins. Exports include selected IDs/path and actual generation configurations. Build reads and health checks make no inference calls.

### TR-014 Review and clarification interface

**Business mapping:** BR-002, BR-003, BR-005, BR-006, BR-007, BR-009.

Provide upload, request confirmation, progress, applicability, grouped findings, source inspection, issue details, and clarification/retry flows. Show workflow status separately from documentation readiness. Each finding links to policy and available chart spans; a missing finding shows the requirement and documentation needed without inventing a chart citation. Source navigation uses original page numbering. Staff annotations and unresolved conflicts remain visible after rerun. TR-019 adds standalone guideline/chart preparation, real stage/section progress, source coverage and dependency review, explicit version selection, and linked retry/rebuild; preparation cannot require the other document.

**Acceptance:** Saved browser tests cover a matched review, mismatch, missing evidence, `needs_input` followed by a linked new run, and actionable processing failure. A reviewer can inspect both source documents at cited pages and reopen a persisted run through its URL after restart. Conflicting metadata clarification shows the source, selected value, and resolution reason. A completed `review_required` outcome is never presented as satisfied merely because processing finished.

### TR-015 Traceable exports

**Business mapping:** BR-008.

Provide JSON and a readable Markdown checklist for completed and `needs_input` runs. Both identify run and parent IDs, export time, workflow/outcome, source names/hashes, policy version fields, request/annotations, criteria, findings, source references, unresolved issues, and relevant model/parser/prompt/schema configuration. They must reflect the saved result rather than rerunning inference. A clarification export states that assessment stopped for input and contains no invented necessity conclusion.

**Acceptance:** A19 exports a result whose identity, citations, findings, and unresolved issues match the UI and stored run. A09 verifies that an old result exports unchanged after a new policy is uploaded. In-progress, failed, and interrupted runs retain diagnostics through the status API and cannot be downloaded as completed checklists.

### TR-016 Measurement and resource budgets

**Business mapping:** BR-009, BR-011.

Record run/stage IDs, durations, attempts, provider request IDs when available, input/output tokens, OCR pages if later supported, and failure categories. Enforce measured upload/page/token limits and finite call/concurrency budgets before work exceeds them. Record cold and warm model behavior, including any observed provider setup overhead. Keep operational records separate from clinical evidence. Cost estimates, when included, must use a dated price source and identify provider/model/OCR assumptions; usage must not be presented as an exact bill.

**Acceptance:** A16–A19 account for failed/retried work and report actual measurements with denominators. Budget exhaustion yields a specific operational state instead of truncated input or output accepted as complete. M1–M2 set the numeric limits listed below; no unmeasured latency, cost, or throughput promise is a release claim.

### TR-017 Evaluation and release gates

**Business mapping:** BR-011.

Implement unit checks for rules/provenance/state, integration checks for parser/storage/API/provider boundaries, saved browser journeys, and separately tagged live semantic evaluation. Freeze reviewed expectations before evaluating a case. Maintain development and held-out cases across two policy families; if a held-out failure becomes tuning data, replace it. Use all A01–A21 scenarios within the declared support scope and retain repeated-run disagreements.

**Acceptance:** All mandatory deterministic checks pass. The release set has no known accepted mismatch, fabricated citation, unsupported satisfied finding, omitted mandatory condition/edge, or incorrect mandatory branch. Ambiguity appears as the intended review/input state. Publish configuration, inputs, counts, failures, and limitations. Fix or explicitly narrow/retest scope; do not silently change expectations to match output.

### TR-018 Packaging and reviewer delivery

**Business mapping:** BR-010, BR-012.

Package locked application/parser dependencies and built UI assets for the target one-line launch (`./scripts/launch.sh`), with one documented application port and a persistent local data directory. Document the server-only OpenAI key, explicit model configuration, input limits, scan limitations, and first-run behavior. Supply examples, the verification record, and a short design note explaining judgment, data versus code, failure boundaries, and a future hosting extension.

**Acceptance:** M6/A19 starts from a fresh checkout and completes a live unseen-input workflow, citation inspection, and export using only documented prerequisites. Record actual build/type/lint/test commands and results. The run command is not declared working before this check. Prepare the repo or zip for delivery at least one day before the 45-minute discussion; actual submission remains a separate user-authorized action.

### TR-019 Long-document rule-set compilation

**Business mapping:** BR-001, BR-004, BR-006, BR-008, BR-009, BR-010, BR-013.

Compile the complete guideline through a durable staged process: layout/source inventory; token- and output-budgeted structural chunks with parent/table/reference context; source-validated local extraction; explicit definition/exception/reference reconciliation; coverage and omission audit; deterministic compilation; and immutable rule-set publication. Keep this entire flow independent of patient data and selected requests. Every source section needs a source-linked disposition. Retrieval and summaries can help context selection but cannot replace complete source accounting or the original passages behind rules.

Persist intermediate contracts and dependency edges, not just a repeatedly rewritten global graph. Keep procedure/plan/time scope and source-defined AND/OR grouping. Validate the executable representation locally; unsupported operations and unresolved semantics remain explicit review blockers. Failed/unprocessed extraction or required audit work cannot be published as a completed reusable rule set. Technically complete drafts with unresolved interpretation retain their blockers; reuse does not imply human approval or semantic certainty.

Handle dependency invalidation, identical concurrent builds, interruption, corruption/rejection, and explicit versioned rebuild without overwriting earlier artifacts. Separate per-call limits from whole-build limits and account for every inference operation. Prepare guidelines and charts independently through documented interfaces; pin exact completed versions in assessments and exports. The TR-013 standalone contracts freeze the LD-02 route/schema amendments; implementation evidence is recorded separately.

**Acceptance:** A21 and [WP-19 LD-AC01–LD-AC12](../features/19-long-document-rule-compilation.md#acceptance-checks) verify 100/200-page native-text builds, remote definitions/exceptions, cross-page tables/lists, multiple procedures, omissions/injection, independent reuse, restart/concurrency/budget failures, useful UI/export behavior, and every-call direct-OpenAI routing. Record fixture and live evidence separately. No page count, token budget, correctness score, or completion claim is inferred from this specification.

Design and task sequence: [WP-19 implementation plan](../plans/long-document-rule-compilation.md). Public rationale: [research log](../research/long-document-rule-extraction.md).

## HTTP interface contracts

The following routes are the MVP contract. M0 establishes the initial JSON schema baseline; M1–M2 feasibility findings may require reviewed amendments before the contracts are integrated with the UI. Documents and runs use server-generated IDs; endpoints never accept arbitrary local file paths.

| Method and route | Input | Successful response |
| --- | --- | --- |
| `POST /api/documents` | Multipart `file` and `role` (`policy` or `chart`). | `201`: document ID, role, filename, SHA-256, page count, page inventory, and extraction availability. Intake does not imply completed extraction. |
| `GET /api/documents/{document_id}` | Document ID. | `200`: metadata and current extraction revisions/page issues. |
| `GET /api/documents/{document_id}/file` | Document ID. | `200 application/pdf`: preserved original bytes for the source viewer. |
| `GET /api/documents/{document_id}/pages/{page}` | One-based page and an explicit `extraction_id`. | `200`: blocks/spans, geometry when available, extraction method, and page issues from that revision. |
| `POST /api/assessments` | `policy_document_id`, `chart_document_id`, request context/annotations, optional `parent_run_id`. | `202`: `run_id`, `status`, `phase`, and status URL; a `Location` header points to that URL. |
| `GET /api/assessments/{run_id}` | Run ID. | `200`: identity/configuration, status/phase, progress, issues/errors, and available validated outcome. |
| `GET /api/assessments/{run_id}/export` | `format=json` or `format=markdown`. | `200`: saved checklist for `completed` or `needs_input`; content type and download filename match the format. |
| `GET /api/policy-rule-sets` | Optional `document_id`. | `200`: policy graphs previously generated for that document hash, with status (`draft`, `approved`, or `rejected`), configuration fingerprint, and review metadata. |
| `POST /api/policy-rule-sets/{rule_set_id}/approve` | Rule set ID. | `200`: marks the reviewed policy graph approved for reuse on later assessments of the same document hash/configuration. |
| `GET /health` and `GET /health/live` | None. | `200` when the application process can serve requests; no dependency inference call. |
| `GET /v1/models` | None. | `200` OpenAI-style list containing only the configured model id, or an empty list when the server is not configured. No provider call and no API key. |
| `GET /health/ready` | None. | `200` when local store, parser dependencies, and required configuration/credential resolution permit attempting live work; otherwise `503` with missing prerequisites. |

Readiness is not proof of remote model access or future provider availability. Return the last explicit provider verification state separately, including `unverified` when none exists. A live preflight is an explicit CLI/diagnostic action in M1 and delivery verification, not a periodic health side effect. Static UI and liveness remain available while readiness fails so the reviewer can understand setup problems.

## Status and error contracts

`status` is one of `queued`, `running`, `needs_input`, `completed`, `failed`, or `interrupted`. While running, `phase` is one of `extracting`, `interpreting_policy`, `extracting_chart`, `checking_applicability`, `mapping_evidence`, `validating`, or `evaluating`. Guideline interpretation and chart-fact extraction finish before applicability. Retain the last phase on a stopped run for diagnosis. Progress names completed stages/pages; it must not invent a percentage of remaining model work.

`needs_input` is a stopped attempt with named unresolved scope/request fields. A correction creates a new run using `parent_run_id` and annotations. `completed` means a validated outcome was reached, which may be `applicability_mismatch`, `documented_requirements_satisfied`, `documentation_gaps_or_contrary_evidence`, or `review_required`. Only an applicable, validated evaluation with no governing blocker may produce the satisfied outcome. `failed` and `interrupted` carry operational diagnostics rather than a readiness conclusion.

Errors use `error.code`, `error.message`, `error.retryable`, `error.stage` where relevant, and a suggested corrective `error.action`, plus a request ID and optional run/document/page references. Do not include credentials in errors. A job accepted with `202` reports later provider errors through its persisted run; polling a known failed run still returns `200` with `status=failed`.

| Condition | HTTP response before job acceptance | Required distinction |
| --- | --- | --- |
| Invalid syntax or schema/role/context fields | `400` for malformed syntax; `422` for contract validation. | Identify the field and correction needed. |
| Unsupported file type | `415`. | Separate from a PDF that is malformed or unreadable (`422`). |
| Upload or document limit exceeded | `413`. | State the configured byte/page limit without silently truncating. |
| Unknown document/run/page/revision | `404`. | Do not resolve a different input or extraction revision. |
| Requested artifact/export unavailable in this state | `409`. | Explain which workflow state prevents the action. |
| Local work queue full | `429`. | Report retry guidance; do not accept an untracked job. |
| Required local/provider configuration unavailable | `503`. | Keep setup failure separate from clinical uncertainty. |

Provider failures preserve an application category such as `access_denied`, `throttled`, `timeout`, `refused`, `invalid_output`, `citation_invalid`, or `extraction_failed`, with the provider code retained diagnostically when available. Retry classification follows service error codes; it must not assume every throttle has HTTP status 429.

## Measured limits and open feasibility decisions

| Decision | Required evidence and owner milestone |
| --- | --- |
| OpenAI model, API/SDK and inference configuration | M1 live contract and annotated semantic results; record candidate comparisons or access limitations. |
| Parser configuration and supported native PDF forms | M2 rendered-page checks against native, scanned, mixed, and malformed fixtures; unsupported scans are explicitly rejected. |
| Maximum upload bytes, pages, and input/output tokens | M1–M2 resource and evidence-quality measurements; deterministic limit tests before M3 completion. Any later OCR scope adds its own limits. |
| Maximum concurrent/queued runs, call attempts, and stage duration | M1–M3 observed latency and failure handling; finite settings must exist before live workflow release. |
| Latency and cost targets | M5 measured counts/distributions and dated pricing when estimating currency. No target is fabricated from vendor or vault anecdotes. |
| Supported numeric/date predicates and policy language | M0 annotated cases, M3 implementation, and A08/A20 release checks; unsupported semantics stay visible. |

These decisions must resolve before their dependent release gates. They do not permit omitted pages, silent input truncation, unlimited retries, or unvalidated favorable findings while feasibility work proceeds.
