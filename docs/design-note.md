# Design note - where judgment lives, and what breaks first

*Evidence basis: deterministic tests, controlled/fixture interpreters, and the documented contract. One live run of the supplied pair completed as an applicability mismatch during development (on an earlier extraction revision); there is no live accuracy benchmark yet, and the 98-page path has not been run live.*

## What it does

Aira is a narrow prior-authorization evidence workspace. Staff upload one insurer guideline PDF and one patient chart PDF, select one procedure request, and the system extracts native text, compiles the guideline into a validated, reusable rule set, extracts chart facts, gates policy applicability, maps chart evidence to each requirement, and produces a deterministic documentation-readiness checklist with exact page/span citations - saved, versioned, and exportable. It never claims approval or denial.

## Where judgment lives

- **Model:** policy text -> criteria, connectives, sections, and predicate kinds; candidate applicability; chart facts and narrative finding statuses. Every claim must be backed by exact quotes, and the model's output is treated as an untrusted candidate.
- **Code:** page accounting and input rejection; exact-quote citation resolution; source-coverage checks; graph validation and compilation; recomputing numeric and date findings from cited quantities; three-valued AND/OR; readiness blockers; the status/outcome lifecycle. Nothing payer- or procedure-specific.
- **Staff:** select/clarify request metadata; resolve metadata conflicts with a reason; resolve clinical contradictions by adding documentation (no override); the final submission decision.

## Data vs code

- **Data:** original PDFs, extraction revisions, saved guideline builds (rule set, coverage ledger, checkpoints), chart-fact builds, facts/findings, staff annotations, configuration (model, limits), and the reviewed evaluation expectations.
- **Code:** prompts (versioned + hashed), schemas, validators, the compiler, the evaluator, the workflow.

Consequence: a new guideline needs no code change - it is data. A new kind of rule semantics (calendar-month durations, unit conversion) needs code, and until then surfaces as a blocking review issue rather than a guess. The BCBS vein policy appears only in tests and examples.

## Guideline preparation

Every guideline is split into structural sections of whole source blocks (nothing is truncated). Each section is interpreted in its own model call, one call reconciles cross-section references, one audit call per section confirms every source block was accounted for, and code compiles the result. Up to four calls run at a time. The 14-page BCBS guideline becomes about 36 sections, so the first assessment of the supplied pair makes about 75 model calls (about 2-6 minutes); later runs against the same guideline reuse the saved rule set, and a failed build resumes from saved sections. A single-call path for short guidelines and an applicability check before compilation are the obvious next optimizations.

## What breaks first - guideline change

1. **Exact citations.** Paraphrased quotes fail closed as `citation_invalid`. This is the likely first live failure mode - a failed run, not a wrong answer.
2. **Audit and reconciliation validation.** An audit that omits a block id, or a reconciliation that does not compile, fails the build without a repair call; retry reuses the saved sections.
3. **Output budget and deadlines.** The code defaults (4,096 tokens, 30 s per request) are tight for real models; `.env.example` recommends 8,192 tokens and longer deadlines. An incomplete answer fails as `invalid_output`.
4. **Unsupported semantics** -> `review_required` instead of satisfied.
5. **Omitted conditions.** Code cannot detect a governing condition the model never extracted; only known unresolved sections block. The control is independent annotated evaluation.
6. **Layout.** Logos, scans, annotations reject the whole document (conservative).
7. **Version/applicability ambiguity** -> `needs_input`.

## What breaks first - messy chart

1. **Scans/faxes/images are rejected - no OCR by default.** The most likely real-world blocker; one unreadable page rejects the whole chart.
2. **Dates not in labelled ISO form** leave date predicates at `needs_review`; conflicting dates -> conflicting.
3. **Repeated short phrases** -> an ambiguous quote -> citation failure; needs longer quotes.
4. **Long charts.** Chart facts come from one model call under the per-call budget `AIRA_BUILD_INPUT_TOKENS` (default 60,000 UTF-8 bytes, roughly 25-30 dense pages). A larger chart is rejected as `unsupported_input`, never truncated; there is no retrieval.
5. **Contradictions, wrong side, post-cutoff evidence** -> conflicting/needs_review, not met.

## Observed so far

- The supplied pair is a pacemaker chart against the BCBS vein policy - an applicability mismatch that correctly stops before necessity work. One live development run reached that outcome; controlled tests cover it on every check.
- The context-guardrail defect (serialized geometry counted against the limit) was found and fixed during implementation.
- No live accuracy benchmark has run, and the 98-page guideline path has been exercised only with controlled interpreters.

## Extensions (not built)

Retrieval only with evidence-recall evidence; an OCR adapter with provenance; partial-chart assessment that flags unreadable pages; more predicate kinds; multi-document charts; hosted storage and a shared database.

---

Owner docs: [architecture](architecture.md) · [contracts](contracts.md) · [decisions](decisions.md) · [results](results/) · [evaluation](evaluation.md)
