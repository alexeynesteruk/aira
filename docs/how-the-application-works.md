# How Aira works

A briefing for a demo and a team discussion. Written 19 October 2026 from the running application, the committed design, and one completed live run of the supplied pair. Older notes in `docs/design-note.md` and `docs/decisions.md` still say live inference is blocked by quota. That is out of date. This file is the current picture.

The demo to open is [run-87d41efd30084df3a74abcbba81bac76](http://127.0.0.1:8000/?run=run-87d41efd30084df3a74abcbba81bac76). The saved guideline is [build-66e66663eddf4e3e8e612842439f4f87](http://127.0.0.1:8000/?build=build-66e66663eddf4e3e8e612842439f4f87).

## What the product is

Aira is a local workspace for clinic staff who are about to submit a prior-authorization request. They upload one insurer guideline PDF and one patient chart PDF. The application reads both, compiles the guideline into a reusable rule set, extracts cited facts from the chart, and checks whether that guideline applies to that request.

If the guideline applies, it maps chart facts onto the requirements and produces a documentation-readiness checklist. Every kept claim points at an exact passage on a page. The checklist never says the payer approved or denied the request. Staff still make the submission decision.

The supplied sample pair is the wrong match on purpose. The chart asks for a single-chamber pacemaker (CPT 33207). The guideline is the 14-page BCBS Florida medical policy for varicose-vein treatment. The correct terminal result is **Policy does not apply to this request**. Necessity is not evaluated. That is the run above.

Nothing in the production code hard-codes that patient, that CPT code, or that vein policy. A different upload drives a different result. The pair appears in examples and tests so the mismatch behavior can be checked. It is not a special case in the engine.

## What a reviewer sees

One FastAPI process serves the React application and the HTTP API on `http://127.0.0.1:8000`. The browser never sees the model key.

A staff member:

1. Uploads the guideline PDF and the chart PDF. The originals are stored by SHA-256. Identical bytes are one blob. A second upload of the same file still gets a new document id, because lineage is per upload.
2. Starts an assessment. Optional request fields (procedure, code, payer, plan, dates, laterality) can be filled by staff. If they are left empty, the model proposes them and the code keeps only the ones that have their own chart citations.
3. Watches progress. Document extraction is fast and has a page count. Model calls do not. The screen stays on one sentence until that call returns, because the adapter does not stream tokens into the progress record.
4. Lands on a terminal state. `completed` means processing finished with a valid outcome. It does not mean the request is ready to submit. `needs_input` means staff must confirm a field. `failed` means a processing error. Those three are different, and a processing error is never displayed as "the chart is missing this fact."

On the completed mismatch screen the banner is **Policy does not apply to this request**, with the rationale and source chips. The 65 requirements live on the policy build, not inside the assessment result. A mismatch result has no findings and no necessity aggregate.

## The pipeline

```text
guideline PDF                         chart PDF
     |                                     |
 native text extraction              native text extraction
     |                                     |
 plan sections from the blocks       one model call for facts
 one model call per section               |
 reconcile cross-section refs             |
 merge the rule graph if needed           |
 audit each section                       |
 compile a versioned rule set             |
     \                                   /
      \                                 /
       applicability on the saved pair
                 |
      mismatch or needs staff input
                 |  (only if applicable)
       map saved facts to requirements
                 |
       deterministic evaluation
                 |
       checklist, sources, export
```

Guideline preparation and chart preparation do not see each other's text, and neither sees the staff request while it is being built. Assessment is the first stage that is allowed to look at both saved artifacts together. That split is why a new patient can reuse a compiled guideline, and a new guideline can reuse a compiled chart.

Applicability is a gate. Unresolved scope stops as `needs_input`. A cited payer or procedure mismatch completes as `applicability_mismatch` and returns before evidence mapping. Only an applicable scope continues into mapping and evaluation.

## Architecture

The modules live in one process. They are not separate services. Domain code does not import HTTP, SQLite, or the provider SDK. Adapters sit at the edges.

| Module | Owns | Does not own |
| --- | --- | --- |
| `frontend/` | Upload, progress, checklist, source chips, exports. Polls `?run=`. | Rule evaluation. The UI renders saved records. |
| `backend/app/api/` | Routes, validation, ids, error envelopes. | Model work inside the upload request. Start returns a run id. |
| `backend/app/documents/` | PDF intake and native extraction. | Coverage decisions. |
| `backend/app/policies/` | Turning model candidates into a policy or a chart, and compiling the guideline graph. | Patient-specific rules. |
| `backend/app/evidence/` | Citation resolution, fact conflicts, finding validation. | Choosing a payer outcome. |
| `backend/app/assessment/` | Stage order, builds, pure evaluation, exports. | Calling OpenAI itself. |
| `backend/app/llm/` | Prompts, schemas, the adapter, the stage interpreter. | AND/OR aggregation. |
| `backend/app/storage/` | SQLite metadata and content-addressed files. | Parsing or inference. |
| `backend/app/schemas/` | Frozen Pydantic contracts, schema version `0.1.0`. | Side effects. |

Tests that drive the UI without a model use a fixture interpreter in `tests/`. That interpreter is not imported by `backend/app`. `make browser-test` runs two Playwright projects: the real unconfigured app on port 8000, and a fixture server on port 8001.

## Infrastructure

There is no queue, no cloud store, no retrieval index, and no agent framework.

**Process.** `./scripts/launch.sh`, or `uvicorn app.main:app` from the repository root so `Path(".env")` resolves. The working directory matters. The lifespan opens SQLite, loads provider settings, and starts one workflow engine. On startup, runs that were still `queued` or `running` are marked `interrupted`. They are not silently resumed.

**Data.** Default directory `data/app`, overridable with `AIRA_DATA_DIR` in the process environment, not in the env file. `aira.sqlite3` holds documents, extractions, builds, checkpoints, runs, and artifacts. Payloads live as immutable files under `objects/`, named by SHA-256. A row is published only after its file exists. Original PDFs stay. Deleting extractions, builds, and checkpoints forces a real re-read. Deleting only the run rows does not, because a completed build is reused by document hash plus configuration.

**Model path used for the demo.** The backend talks to an OpenAI-compatible API. The local setup is a LiteLLM proxy on `127.0.0.1:4000` with `AIRA_LLM_BACKEND=litellm` and `AIRA_LLM_TRANSPORT=chat_completions`. The configured model is `gemini-3.8-flash-high`. The key and the upstream URL stay in `.env`, which is gitignored. Readiness (`/health/ready`) checks that the store opened and the configuration parsed. It does not call the model. A separate preflight command does.

**Direct OpenAI is still a supported path.** Leave `OPENAI_BASE_URL` unset, set `OPENAI_API_KEY` and `AIRA_MODEL`, and the adapter uses `https://api.openai.com/v1` with the Responses API. A base URL that exists only in the shell is ignored for that direct path. An `OPENAI_BASE_URL` written in `.env` selects the compatible endpoint and chat completions. `AIRA_LLM_BACKEND=litellm` is the explicit proxy mode. There is no silent fallback from one provider to another.

**Deadlines that actually completed the sample run.** Request timeout 600 seconds (the schema maximum), adapter stage timeout 1200 seconds (also the maximum), workflow stage timeout about 1220 seconds, output budget 16384 tokens. Code defaults are much smaller: 30 seconds per request, 65 seconds per adapter stage, 90 seconds per workflow stage, 4096 output tokens. Those defaults are too small for this model on this guideline. A reconciliation call took 285 seconds and the chart call took 252 seconds. A 120-second request deadline would have aborted both.

**Concurrency.** Section interpretation and audits use a pool of four. Reconciliation is serial, because each batch depends on the merge ledger. The UI worker is one assessment at a time, with a small pending queue. This is a single-reviewer machine, not a service cluster.

## Where judgment lives

Three parties, and they do not overlap.

**The model** reads language. It proposes criteria, logical connectives, section dispositions, chart facts, an applicability judgment, and, when the scope is applicable, evidence mappings. Every proposal that is kept must carry an exact quote, a page, and a document id. The model has no tools, no browser, and no payer portal.

**The code** decides what is allowed to stand. It checks that the quote occurs in one block on that page, that the graph is well formed, that numeric and date predicates use supported operators and literal units, and that AND/OR is three-valued. Known gaps become blocking review issues. A blocking issue prevents `documented requirements satisfied` even when every evaluated node is true.

**Staff** can correct request metadata. They cannot click a requirement to "met." A clinical contradiction is resolved by adding a document, which starts a new run. Annotations are stored separately from extracted facts. A value that matches a staff annotation stays an annotation. It is not copied into the extracted request as if the chart had said it.

## How a guideline becomes rules

`COMPILER_VERSION` is `structural-compiler-v2`. Changing that string, the prompt, the schema, or the input packet misses the saved checkpoints. Changing only the local conversion code does not.

1. **Extract.** pdfplumber, adapter version `0.1.2`, reads native text into ordered blocks. Wrapped lines inside a block are joined. The quote matcher still refuses to join two blocks or two pages. Intake rejects scans, rotation, forms, and non-link annotations by default. Limits are 10 MiB, 250 pages, 50,000 characters per page, 2,000,000 per document. OCR is not the demo path.
2. **Plan.** Blocks are grouped into sections of about 7,000 UTF-8 bytes of primary text. The 14-page vein guideline plans as **39 sections**. Every source block is assigned. Nothing is truncated to fit.
3. **Interpret each section.** One structured model call. The candidate is flat on purpose: provider JSON schemas do not do well with recursive trees. Local code then checks citations, builds the nodes, and seals the fragment. An empty fragment with no rules is kept as a shell. A requirements label with no cited rule becomes a blocking review issue. In the local working tree, the inverse is also kept: cited rules whose blocks were not labeled `requirements` stay in the build with a blocking issue, and a blank title becomes a placeholder with a blocking issue. Those two behaviors are not in `origin/main` yet. They are why the fresh re-extraction finished.
4. **Reconcile.** Cross-section references, definitions, and exceptions are resolved in batches. A batch that would exceed the 60,000-byte input budget is split. Batches that contain only context and no rules are not sent to the model. Their dependency ids still have to be covered later. This guideline needed several reconcile batches. Some were bibliography and definitions.
5. **Merge.** If the combined reconciliation packet does not fit, it is sliced. Each slice must account for its reference ids exactly once. The slices are assembled, then the full policy is validated.
6. **Audit.** One call per section, with a compact packet: source text once, short wording, and only that section's resolutions. The audit asks whether every source block was accounted for. Discrepancies become blocking review issues. They do not delete the rules.
7. **Compile and store.** The published policy on this fresh run has **65 criteria, 87 nodes, 26 paths, and 293 blocking review issues**. The issues are mostly dates that are not `YYYY-MM-DD`, unsupported numeric operators, and conditions the reconciliation did not fully carry. They would block a favorable checklist. They did not apply on the demo, because the run stopped at mismatch.

Checkpoints are keyed by compiler version, stage, packet, prompt, generation id, and model. The packet includes the document id, so uploading the same PDF again does not reuse section checkpoints. A **completed** build is a different key: document SHA-256, role, and configuration. A new upload of the same bytes reuses that completed build after the pages are compared. To force a real recompile, the completed builds and the checkpoints both have to go. That is what the fresh demo did. Thirty-seven of the eighty-four build steps on the successful continuation were checkpoints from earlier attempts of that same fresh extraction, after two sections had failed local checks. They were not the older 60-criterion build. That older build was deleted before the re-read.

Failed sections are not checkpointed. A linked retry keeps the sections that saved and calls the model only for the rest.

## How a chart becomes facts

One model call, under the same 60,000-byte input budget. A larger chart is rejected. It is not truncated and it is not retrieved in pieces. Roughly 25 to 30 dense pages fit. The sample chart is 7 pages.

Facts need their own citations. A fact whose quotes do not resolve is not invented from the guideline. Unreadable dates stay on the fact as a staff note. They are not rewritten into ISO dates. The fresh chart build kept **51 facts** and **38 notes**. Most notes say a date was not `YYYY-MM-DD`. A few record contradictions the model saw in the chart.

In the local working tree, a chart citation whose block id is not on that page is tried once more as the same quote on the same page. A unique match keeps the real block. A missing or repeated quote drops that fact. Policy compilation does not do this. An unknown block id on a rule still fails that section. Blank anatomical target, laterality, and unit strings are stored as absent rather than failing the chart. That recovery is local only. `origin/main` still fails the chart build on those cases.

## Applicability, evidence, and evaluation

The applicability packet sends paths and criterion wording. It does not send the review-issue ledger or the executable nodes. Those copies pushed the rendered policy past the 200,000-character stage limit (the full render was about 230,000 characters, mostly issues). Evaluation still applies every saved issue if the run gets that far. The scope packet for this pair was about 68,000 characters.

The model returns a status of applicable, mismatch, or unresolved, plus quotes. Code then:

- Drops a request field that has no field-level chart citation. Scope quotes are not copied onto it.
- Turns an applicable judgment into unresolved when a kept field was dropped or a date is not a real `YYYY-MM-DD`.
- Leaves a **cited mismatch** as a mismatch when the date, payer, or plan is missing. Those fields stay unresolved on the request. They do not reopen the case. This was a real bug: an earlier live attempt stopped at "needs staff input" only because the service date was not ISO, and the procedure mismatch was hidden. The fix is in commit `7ce2717`.
- Requires a policy citation and a chart citation for any resolved judgment. If every citation is dropped, the stage fails. It does not invent sources.

On the fresh run the mismatch rationale is the pacemaker procedure against the vein-treatment passage. Citations checked out: chart page 7 for the procedure and CPT 33207, guideline page 1 for the saphenous-vein sentence, chart page 1 for the payer and plan. Service date, assessment cutoff, and laterality are unresolved. Applicability itself has an empty unresolved list, which is required: a resolved mismatch cannot carry open scope fields.

Evidence mapping and Kleene evaluation did not run. If they had, `met` is true, `not_met` is false, and every other evidence state is unknown. AND/OR follow three-valued logic. There is no score. `documented requirements satisfied` is impossible while any blocking review issue remains.

## Provenance, in one rule

A citation is a document, a page, and an exact quote. Whitespace is collapsed. Hyphenation is not repaired. Fuzzy match is not used. The quote must sit inside **one block**. A sentence that starts at the bottom of page 1 and continues at the top of page 2 is `quote_not_found`, even though a person would join it. An optional `block_id` picks one copy when the same sentence appears twice on the page. If that id is not on the page, `CitationResolver.resolve()` raises `unknown_block`. Tests require that. The scope and chart recovery above happens outside `resolve()`, and only after that error.

Every displayed source span stores the document hash, the extraction id, the page, the block, and code-point offsets. On the fresh run, 318 policy spans, 70 chart spans, and 9 applicability spans were checked against the extracted blocks. All of them were inside the named block. No criterion and no kept fact lacked a source.

## Decisions and the reason for each

| Decision | Why | What you give up |
| --- | --- | --- |
| One guideline, one chart, one request | The reviewer workflow stays traceable. | Multi-procedure charts become a clarification, not a silent choice. |
| Staged pipeline with applicability first | The sample pair is a mismatch. Necessity must not run anyway. | More round trips than one prompt that "does the whole chart." |
| Model proposes, code disposes | A quote can be checked. A vibe cannot. | The first live failures are rejected runs, which look harsh. |
| One process, SQLite, files | A reviewer clones and runs it. | No horizontal scale, no shared database. |
| Immutable artifacts and fingerprints | A result can be tied to the bytes, the prompt, and the model. | Reuse is strict. A new document id misses section checkpoints. A completed build is reused by file hash, which surprises people who re-upload and expect a full recompute. |
| Status, phase, and outcome are separate fields | A crash is not "documentation missing." | The UI has to teach three words. |
| No manual "met" | Staff text must not become chart evidence. | The demo cannot click its way to a satisfied checklist. |
| OpenAI-compatible adapter, explicit model | Direct OpenAI works with no proxy. Gemini and local models work when the env file says so. | The transport, schema, and timeouts have to be configured. A wrong timeout fails a correct model. |
| Native text only | Offsets have to land on real glyphs. | Scanned faxes are rejected. That will be the first real clinic failure. |
| Flat candidate schema, local graph | Structured output cannot express a recursive tree reliably. | The compiler is where the real policy object is born, and it is the part that fails closed. |
| Exact quote, one block | A reviewer can open the page and see the sentence. | Line wraps across blocks and hyphenated line breaks fail. That is intentional. |
| Three-valued logic, no score | Unknown is not half-true. | People ask for a percentage. There isn't one. |
| Long guidelines are many section calls, not one | A 14-page policy does not fit one output budget, and a single call drops distant exceptions. | The first build is slow. Thirty-nine calls, then reconciliation, merge, and thirty-nine audits. |
| Fixture tests never stand in for live calls | A green `make check` does not mean the model read the PDF. | You have to say that out loud in the discussion. |

## Trade-offs you will be asked about

**Speed against inspectability.** Four section calls at a time, and no streaming progress. On `gemini-3.8-flash-high` through the local proxy, the fresh guideline preparation was on the order of tens of minutes, not two to six. Later assessments of the same guideline skip the compile. The chart is one call (about four minutes on this run). Applicability was about 95 seconds. A document that says the first sample run takes 2–6 minutes is wrong for this model. Pull request #1 currently says that. Do not merge it unchanged.

**Fail closed against finishing the demo.** The fresh re-read stopped four times before it completed: a blank section title, rules that were not labeled as requirements, a chart citation with a block id that is not on the page, and blank anatomy strings. Each stop kept the sections that had already saved. The repairs keep the cited material and add a blocking review issue, or they drop the unsourced field. They do not loosen `resolve()`, and they do not cross blocks. `origin/main` at `7ce2717` has the mismatch-versus-dates fix and the long-guideline compiler. It does not have those four later repairs. A teammate who clones `main` and re-extracts can hit the same stops.

**Completeness against what the model omitted.** The compiler can prove a quote is real and a graph is connected. It cannot prove the model extracted every exception. The 293 blocking issues catch the gaps the model admitted or the code could see (bad dates, unsupported operators, unaudited blocks). A condition the model never mentioned is invisible. The control for that is a separate annotated evaluation, which has not been run live. Say that. Do not claim the 65 requirements are a complete encoding of the vein policy.

**Reuse against freshness.** Completed builds are keyed by file hash. That is what makes the second patient cheap. It is also why "I uploaded the PDF again" does not recompute the rules. The fresh demo deleted builds and checkpoints first, then uploaded again.

**One chart call against long charts.** Splitting the guideline was necessary. Splitting the chart was not, for a 7-page note. A long chart hits `unsupported_input` at the byte budget. There is no retrieval. Adding retrieval without a recall test would hide missing pages.

**Structured output against optional fields.** The scope packet does not include block ids. The model filled `block_id` anyway. Strict rejection is correct for rules. For scope and chart, the local code retries the quote once on that page, because the id was never in the input. A quote that is still ambiguous is dropped, not guessed.

## What the live run established, and what it did not

Established, on this machine, with `gemini-3.8-flash-high`:

- Both PDFs were parsed again after the old extractions were removed. 14 guideline pages, 7 chart pages, parser `0.11.10+aira.0.1.2`.
- The guideline compiled to 65 requirements, 39 of 39 sections.
- The chart compiled to 51 cited facts.
- Applicability completed as a mismatch in one call. Zero findings.
- Every saved quote was inside its named block.

Not established:

- That a matched chart would produce a correct checklist. This pair never entered evidence mapping.
- That the 65 requirements are clinically complete.
- That another model, or direct OpenAI, behaves the same way.
- That the 98-page guideline path has been run live.
- That `make check` and `make browser-test` have been re-run since the four local repairs. They passed on `7ce2717` (544 backend tests, 26 frontend tests, 14 browser tests). The later repairs have focused unit tests only.

## What a clone includes

The application includes section compilation, reconcile batching, merge slicing, audit packets, the smaller applicability packet, unsourced request fields dropped, and a cited mismatch that survives a bad date. A blank section title, rules that were not labeled as requirements, a chart block id that is not on the page, and a blank anatomy field no longer abort the build. A chart statement that is dropped, or kept without one of its citations or conflict partners, adds uncertainty and a blocking review issue so it cannot support a favorable checklist.

Pull request [#1](https://github.com/alexeynesteruk/aira/pull/1) is an older docs proposal. Do not merge it as written. Its recommended request deadline is 120 seconds, and it says the first sample assessment takes about 2–6 minutes. Both contradict the run you will demo. The deadlines in `.env.example` are 600, 1200, and 1220 seconds.

## How to talk about a failure

If a run fails, read the phase and the error code before changing a prompt.

| What you see | What it means |
| --- | --- |
| `citation_invalid` / `quote_not_found` | The quote is not in one block on that page. Often a line wrap. Do not fuzzy-match it. |
| `unknown_block` | The model named a block id that is not on the page. Rules should fail. Scope and chart, locally, retry the quote once. |
| `invalid_output` | The candidate broke a domain rule: empty required text, bad graph, unsourced resolved judgment. |
| `unsupported_input` | The packet or the PDF exceeded a budget. Raising `max_context_characters` would also change the workflow fingerprint. Prefer sending less duplicated JSON. |
| `needs_input` | A real stop for a missing date or an unsourced field when the scope is not already a cited mismatch. |
| `applicability_mismatch` | Success, for this pair. |
| Provider timeout, then a connection error | The upstream model host dropped. Not a compiler bug. The deadlines above are what survived. |

Progress that sits on "reconciling" for several minutes is usually one serial model call. `updated_at` does not move until the HTTP response returns.

## What is deliberately absent

OCR as a default, retrieval, multi-document charts, a manual clinical override, a numeric score, an insurer submission, a hosted database, and an agent loop. Each of those has a place after a measured failure. None of them is required to explain this demo.

The sentence to leave them with: the model is allowed to read, and it is not allowed to be the record. The record is the quote, the page, the block, and the rule that refused to guess.
