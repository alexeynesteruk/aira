# Decision record

Consolidated architectural and technical decisions, including those taken during implementation. Each entry names its owner document; the owner remains authoritative. Status distinguishes **Accepted design, implementation pending**, **Accepted**, **Accepted, live-unverified** (behind the deferred OpenAI quota), and **Superseded**. A design decision does not establish that its working-tree implementation passes checks.

## Architecture

**AD-01 · Scope: one policy, one chart, one selected request**
Each assessment takes exactly one policy PDF, one chart PDF, and one selected procedure request. The output is documentation readiness, never a payer decision.
- Why: the brief's narrow reviewer workflow; a deterministic boundary keeps evidence and provenance traceable.
- Consequences: multi-procedure and multi-document cases are out of scope; they surface as clarification, not implicit selection.
- Owner: [BRD](requirements/business-requirements.md) BR-001/BR-002 · Status: Accepted.

**AD-02 · Explicit staged pipeline**
Prepare guideline rules and chart facts independently, then check applicability and map saved evidence before validation and deterministic evaluation. WP-19 extends guideline preparation with structural planning, section extraction, dependency reconciliation, coverage audit, and compilation. Applicability precedes necessity.
- Why: the supplied pair is a mismatch; applicability must gate necessity while document preparation remains independently reusable.
- Consequences: stage failures are typed and restartable; no free-form model exploration.
- Owner: [architecture](architecture.md) · Status: Accepted.

**AD-03 · Model interprets; code validates and decides**
Model output is an untrusted candidate. Citation resolution, graph validation, bounded numeric/date checks, three-valued aggregation, and readiness blockers are deterministic code.
- Why: interpretation is a language problem; decisions must be reproducible and inspectable.
- Consequences: a failed check is a run failure or review issue, never a wrong answer; model "correctness" is never trusted.
- Owner: [architecture](architecture.md), [contracts](contracts.md) · Status: Accepted.

**AD-04 · One local process and store**
FastAPI serves the API and the built React UI from one origin; one bounded asyncio worker (4 pending); SQLite plus content-addressed files in a local data directory. No queue service, cloud, retrieval, or agent framework.
- Why: the one-command local reviewer workflow and the smallest deployable footprint.
- Consequences: single-reviewer scale only; horizontal scaling is a documented extension, not built.
- Owner: [architecture](architecture.md), [TRD](requirements/technical-requirements.md) · Status: Accepted.

**AD-05 · Immutable, versioned artifacts and identity**
Original bytes are hashed; extraction revisions, run snapshots, and stage artifacts publish only after their files exist. Cache identity covers inputs, parser, prompt version+digest, model, SDK, inference settings, request/annotations, and upstream artifacts. Retries and clarifications create linked runs.
- Why: every displayed result must be attributable to exact inputs and configuration.
- Consequences: storage cost per revision; reproducibility and audit.
- Owner: [feature 06](features/06-versioned-storage.md) · Status: Accepted.

**AD-06 · Status, phase, and outcome are separate**
Operational failures never become clinical "missing"; unfinished runs become `interrupted` on restart.
- Why: a failed extraction must not read as absent documentation.
- Consequences: the UI and exports keep the three concepts distinct.
- Owner: [contracts](contracts.md) · Status: Accepted.

**AD-07 · Human boundary**
Staff edit request metadata only, as typed annotations with provenance; a conflict resolution needs a reason plus the original sources. There is no manual clinical "met" override.
- Why: staff assertions cannot silently become chart evidence.
- Consequences: clinical contradictions resolve by added documentation, not clicks.
- Owner: BR-007 · Status: Accepted.

**AD-08 · Provider: OpenAI Responses API**
A thin adapter calls Responses with the key server-side; `AIRA_MODEL` is explicit.
- Why: the user selected OpenAI as the initial inference provider.
- Consequences: provider abstraction stays behind the stage-interpreter seam.
- Owner: [feature 05](features/05-model-integration.md) · Status: Accepted, live-unverified (quota deferred).

**AD-09 · Full-context baseline**
The original experiment used page-ordered native text within explicit limits. This remains a measured small-input comparison baseline. AD-10/WP-19 supersede the whole-document-call assumption for long-guideline preparation; contextual source lookup supports complete section accounting.
- Why: the simplest correct-input baseline; a 200k-character guardrail is measurable.
- Consequences: very long charts hit the guardrail as `unsupported_input` rather than being truncated.
- Owner: [results/input-limits](results/input-limits.md), [WP-19 plan](plans/long-document-rule-compilation.md) · Status: Superseded for long-guideline processing; retained as a baseline.

## Technical

**TD-01 · Stack and tooling**
Python 3.13 / FastAPI / strict frozen Pydantic v2 (schema 0.1.0); React/TypeScript/Vite; uv + npm lockfiles; ruff, mypy strict, pytest, Vitest, Playwright. GitHub Actions runs the Python, TypeScript, and browser checks.
- Why: deterministic contract, typed boundary, reproducible builds and checks.
- Status: Accepted.

**TD-02 · PDF boundary: native text only**
pdfplumber layout blocks, ruled tables, and geometry; a complete-input gate. Conservative rejection set: raster images (even decorative), annotations other than plain links, rotation, forms, vector-only pages. No OCR in the MVP. Provisional limits: 10 MiB / 100 pages / 50k chars per page / 500k per document.
- Why: every cited excerpt must map to exact native-text spans; OCR output would break quote resolution.
- Consequences: scans are rejected with an action, not partially processed.
- Owner: [feature 04](features/04-pdf-ingestion-extraction.md), [results/pdf-extraction](results/pdf-extraction.md) · Status: Accepted.

**TD-03 · Transport**
Strict JSON-schema structured output with flat candidate schemas; `store=false`; truncation disabled. SDK retries off — the adapter owns bounded retries (2 attempts, 30 s request, 65 s stage). Output budget 4,096 tokens by default, `AIRA_MAX_OUTPUT_TOKENS` configurable. Quota errors are never retried; no automatic repair attempt.
- Why: deterministic failure classification beats silent retries; the probe already hit `insufficient_quota`.
- Status: Accepted, live-unverified.

**TD-04 · Prompts**
Versioned per stage (`scope`, `policy`, `policy_index`, `policy_page`, `chart`, `evidence`); identity is version + sha256(instructions + schema)[:12]. Policy reuse keys include only the policy prompts. Chart reuse keys include only the chart prompt. Document text is untrusted data; the model has no tools.
- Why: a prompt change invalidates only the stage that uses it.
- Status: Accepted.

**TD-05 · Stage input**
Guideline and chart model inputs contain only that document. Assessment inputs contain the saved rule set, saved facts, selected request, and staff annotations. The engine still reads every guideline page after the index pass; it does not drop a page the index marks skip. The 200,000-character guardrail remains the per-call limit. A structural long-document compiler beyond that page loop is the WP-19 plan and is not this workflow.
- Why: independent reuse, and a section cannot disappear because an index call skipped it.
- Owner: [architecture](architecture.md). Status: Accepted for the page-wise extraction. WP-19 remains open.

**TD-06 · Citations**
`(document_id, page, exact quote)`; the quote must occur exactly once on the page inside one block; whitespace-only normalization → `SourceSpan` (document hash, extraction ID, page, block, code-point offsets). No fuzzy repair.
- Why: inspectable, falsifiable provenance.
- Status: Accepted.

**TD-07 · Policy representation**
Flat `all/any/criterion` nodes with a root for each evaluated path, structurally validated. The existing one-root policy contract needs a versioned WP-19 amendment for whole-guideline procedure scope; never invent an unguarded global AND/OR across unrelated procedures. Predicates are narrative (model judgment), numeric (gt/gte/lt/lte/eq, literal units, no conversion), or date (explicit ISO boundary, labelled roles). Unsupported semantics become blocking review issues.
- Why: a validated intermediate form the evaluator can check deterministically.
- Status: Accepted.

**TD-08 · Aggregation**
met→true, not_met→false, other states → unknown; Kleene AND/OR. The supporting path is exposed (`AssessmentResult.evaluation`); known blockers prevent a satisfied outcome. No scores or percentages.
- Why: honest three-valued logic over a misleading score.
- Status: Accepted.

**TD-09 · HTTP**
The TRD route table; strict body parsing; an `ErrorResponse` envelope with codes; `X-Request-ID`; typed OpenAPI. Readiness covers local prerequisites only and reports the persisted explicit preflight; it never runs inference.
- Why: a small contractable surface with explicit failure envelopes.
- Status: Accepted.

**TD-10 · Verification strategy**
Pure unit tests for rules/provenance; integration over real SQLite/parser and the real SDK on a mock transport; a controlled interpreter (`tests/support.py`) and a labelled fixture server (`tests/e2e/`) for workflow and browser journeys; live evaluations recorded separately; CI has no credentials.
- Why: deterministic evidence stays distinct from live semantic evidence.
- Status: Accepted.

**TD-11 · UI**
React SPA with `?run=` URL state and 1 s polling; renders persisted results only (traversal of evaluator traces, no rule evaluation). The source viewer uses extraction blocks with code-point highlighting plus an original-PDF page link.
- Why: the UI presents decided state; it never decides.
- Status: Accepted.

**AD-10 · Independent long-document compilation and reuse**
Build whole-guideline rules and chart facts in independent document-only flows. Long guidelines use structural planning, contextual section extraction, explicit reference/exception reconciliation, coverage auditing, and deterministic compilation. Save intermediates and immutable versioned results; assessment consumes exact saved artifacts. Preserve source-defined scope across procedures. Human approval is separate from technical reuse.
- Why: distant definitions/exceptions and output budgets make a single prompt or serial full-graph rewrite insufficient evidence of completeness. New patients must not rebuild the guideline.
- Owner: [BR-013/TR-019](requirements/technical-requirements.md#tr-019-long-document-rule-set-compilation), [WP-19 plan](plans/long-document-rule-compilation.md). Status: Accepted design, implementation pending.

**AD-11 · Direct OpenAI is a required reviewer path**
Accept a backend OpenAI API key and explicit model. Every model operation follows the chosen endpoint/transport, including repair, audit, and preflight. LiteLLM is optional and must not be an author-specific prerequisite or a silent fallback.
- Owner: [model provider contract](model-provider.md). Status: Accepted design; end-to-end live verification pending.
