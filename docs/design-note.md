# Design note — where judgment lives, and what breaks first

*Draft for the submission discussion. Live model observations are pending: the API project quota is deferred, so every claim below rests on deterministic tests, the controlled/fixture interpreters, and the documented contract — not on a live semantic run.*

## What it does

Aira is a narrow prior-authorization evidence workspace. Staff upload one insurer guideline PDF and one patient chart PDF, select one procedure request, and the system extracts native text, gates policy applicability, interprets the guideline into a validated rule structure, maps chart evidence to each requirement, and produces a deterministic documentation-readiness checklist with exact page/span citations — saved, versioned, and exportable. It never claims approval or denial.

## Where judgment lives

- **Model:** policy text → criteria, connectives, sections, and predicate kinds; candidate applicability; chart facts and narrative finding statuses. Every claim must be backed by exact quotes, and the model's output is treated as an untrusted candidate.
- **Code:** page accounting and input rejection; exact-quote citation resolution; graph validation; recomputing numeric and date findings from cited quantities; three-valued AND/OR; readiness blockers; the status/outcome lifecycle. Nothing payer- or procedure-specific.
- **Staff:** select/clarify request metadata; resolve metadata conflicts with a reason; resolve clinical contradictions by adding documentation (no override); the final submission decision.

## Data vs code

- **Data:** original PDFs, extraction revisions, the per-run interpreted `Policy` (criteria/nodes/sections/issues), facts/findings, staff annotations, configuration (model, limits), and the reviewed evaluation expectations.
- **Code:** prompts (versioned + hashed), schemas, validators, the evaluator, the workflow.

Consequence: a new guideline needs no code change — it is data. A new kind of rule semantics (calendar-month durations, unit conversion) needs code, and until then surfaces as a blocking review issue rather than a guess. The BCBS vein policy appears only in tests and examples.

## What breaks first — guideline change

1. **Exact citations.** Paraphrased or line-spanning quotes fail closed as `citation_invalid`. This is the likely first live failure mode — a failed run, not a wrong answer.
2. **Output budget.** Long policies may exceed the provisional 4,096-token default → `invalid_output` (incomplete); `AIRA_MAX_OUTPUT_TOKENS` raises it.
3. **Unsupported semantics** → `review_required` instead of satisfied.
4. **Omitted conditions.** Code cannot detect a governing condition the model never extracted; only known unresolved sections block. The control is independent annotated evaluation.
5. **Layout.** Logos, scans, annotations reject the whole document (conservative).
6. **Version/applicability ambiguity** → `needs_input`.

## What breaks first — messy chart

1. **Scans/faxes/images are rejected — no OCR.** The most likely real-world blocker.
2. **Dates not in labelled ISO form** leave date predicates at `needs_review`; conflicting dates → conflicting.
3. **Repeated short phrases** → an ambiguous quote → citation failure; needs longer quotes.
4. **Long charts** beyond the 200,000-character rendered guardrail → explicit `unsupported_input`; no truncation, no retrieval.
5. **Contradictions, wrong side, post-cutoff evidence** → conflicting/needs_review, not met.

## Observed so far

- The supplied pair is a UHC pacemaker chart against the BCBS vein policy — an applicability mismatch that correctly stops before necessity work.
- The context-guardrail defect (serialized geometry counted against the limit) was found and fixed during implementation.
- Live model behaviour: **pending** — quota deferred; no live semantic benchmark has run.

## Extensions (not built)

Retrieval only with evidence-recall evidence; an OCR adapter with provenance; more predicate kinds; multi-document charts; hosted storage and a shared database.

---

Owner docs: [architecture](architecture.md) · [contracts](contracts.md) · [decisions](decisions.md) · [results](results/) · [evaluation](evaluation.md)
