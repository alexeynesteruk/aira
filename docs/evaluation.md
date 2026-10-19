# Aira evaluation and release checks

Evaluate evidence correctness and useful failure handling before optimizing presentation or adding infrastructure. Expected outcomes come from annotated source passages and policy logic; they do not come from the same model response being tested. The acceptance matrix describes the full target. Deterministic foundation, contract, controlled-interpreter, and fixture browser checks have passed locally and in GitHub Actions; see the [implementation evidence](work-breakdown.md#implementation-evidence). No live semantic benchmark has run. An OpenAI access probe failed with insufficient quota; its [experiment record](results/model-feasibility.md) preserves that limitation.

## Case design

Each case manifest identifies policy and chart files by hash, the selected request, expected applicability, relevant criteria and logical edges, acceptable evidence spans, expected findings, unresolved issues, and provenance of the annotation. Distinguish observed source facts from author-created synthetic facts. Mark every synthetic chart as fictional. Record ambiguity explicitly instead of inventing an authoritative medical conclusion.

Use a development set to debug and tune prompts, and a separate held-out set for release. Keep expected outputs in reviewed files and prevent evaluation runs from rewriting them. If a held-out failure becomes a tuning example, record that change and add a new held-out case. A small take-home suite demonstrates bounded behavior; it does not establish clinical accuracy at scale.

## Required scenarios

| ID | Scenario | Expected behavior | Primary check |
| --- | --- | --- | --- |
| A01 | Supplied UHC pacemaker chart with BCBS vein policy. | Applicability mismatch with payer/procedure citations; no necessity conclusion. | Integration and browser |
| A02 | Applicable policy and fictional chart supporting all required branches. | Correct cited findings and a traceable satisfied rule path. | Semantic evaluation |
| A03 | Remove one mandatory fact from A02. | Missing documentation, with the affected criterion identified; no invented evidence. | Paired semantic evaluation |
| A04 | Replace a supporting statement with explicit negative evidence. | Contrary evidence when it negates this requirement, rather than missing or satisfied. | Paired semantic evaluation |
| A05 | Test the supplied impossible timeline at the chart-extraction stage, then use an applicable fictional pair with conflicting dates or post-cutoff evidence. | Retain conflicting sources and date roles; do not silently use later evidence as if available earlier. The supplied pair itself still stops at mismatch. | Extraction and semantic evaluation |
| A06 | Exercise distinct OR alternatives, including the example policy's branch-specific compression wording. | One valid alternative can satisfy its group; unneeded alternatives are not mandatory. | Rule unit tests and extraction evaluation |
| A07 | One false child in AND; unknown children in AND/OR. | Truth-table results and unresolved reasons match [architecture](architecture.md#finding-and-aggregation-semantics). | Unit tests |
| A08 | Values and duration/recency just below, at, and above a threshold; incompatible or absent units; awake versus sleeping context. | Correct boundaries only with valid units, context, and date roles. Unspecified calendar/duration semantics require review instead of an assumed conversion. | Unit and semantic tests |
| A09 | Change a policy requirement, preserve an old run, and assess the same chart again. Also assess a different patient against the unchanged guideline. | New document/run identity, changed result where warranted, old result unchanged. A different patient reuses the saved guideline without a policy model call; a changed guideline reuses unchanged chart facts. Verify duplicate uploads and restart reuse with document-correct citations. | Integration |
| A10 | Compare the two supplied BCBS revisions. | Preserve their different versions and coding change; do not assume a clinical rule change or infer effective dates from revision dates. | Parsing and semantic evaluation |
| A11 | A second policy family and an unseen chart, with a separately held-out pair at release. | No procedure-specific code changes; unsupported language is surfaced precisely. | Held-out live evaluation |
| A12 | Multiple requested procedures, opposite-side findings, missing plan details, or uncertain policy effective scope. | Request selection or clarification; no silent top-one choice, wrong-side evidence, or policy substitution. | Integration and browser |
| A13 | Two-column layout, tables, and a section crossing pages. | Values remain attached to labels; cross-page evidence opens the right source pages. | Parser integration and visual check |
| A14 | Scan, mixed text/image PDF, malformed/encrypted PDF, blank page, and unsupported size. | Every page accounted for. Unsupported scans and unusable pages produce an explicit limitation or error, with no completed assessment from partial input. Any later OCR scope requires separate verification. | Parser integration |
| A15 | Invented page/quote, quote from the wrong document, unsupported claim with a real but irrelevant quote. | Mechanical provenance errors rejected; semantic mismatch caught by annotated cases and negative controls. | Unit and semantic tests |
| A16 | Model provider access failure, throttling, timeout, refusal, truncated/invalid model output, and interrupted process. | Bounded attempts, persisted diagnostic state, useful UI, no clinical missing-evidence substitution. | Provider contract and integration |
| A17 | Repeated uploads/retries and a changed prompt, model, parser, or request annotation, including an annotation contradicting source evidence. | Reuse only compatible completed artifacts; retain new execution provenance and original conflicts. Policy/chart extraction prompts receive only their own document; assessment receives saved facts/rules. Changing a chart/assessment prompt cannot invalidate policy extraction, and changing a policy/assessment prompt cannot invalidate chart extraction. Failed/rejected/corrupt artifacts cannot be reused. Metadata resolution requires an explicit value/reason; annotations cannot silently create chart-supported clinical findings. | Integration and browser |
| A18 | Place decisive evidence near the start, middle, and end among distractors; add instructions embedded in a document. | Relevant evidence remains discoverable; document text cannot change the workflow's instructions. | Semantic evaluation |
| A19 | Fresh checkout, documented OpenAI configuration, one-line launch, new uploads, citation inspection, export. | Reviewer completes the real workflow without author-specific services or manual source edits. | Live smoke test and saved browser test |
| A20 | An otherwise valid, satisfied tree omits a mandatory condition or exception in governing source prose. | Known unresolved coverage blocks favorable readiness; annotated comparisons catch unrecognized omissions and incorrect logical edges. | Domain validation and semantic evaluation |
| A21 | Prepare complete 100- and 200-page guidelines independently of charts; exercise cross-section scope/definitions/exceptions, changed dependencies, reuse/restart/concurrency, and direct OpenAI execution. | All sections are accounted for; supported rules preserve sources/grouping/scope; failed or unprocessed work cannot publish a complete rule set; saved artifacts are reused independently. UI exposes real progress/coverage/retry/version identity. All model calls use the configured backend. | Parser/domain/storage/provider integration, saved browser journeys, and separate live evaluation |

A21 is the October 18 user-authorized extension; A01–A20 keep their original identifiers and expected meanings. Its detailed matrix is [LD-AC01–LD-AC12](features/19-long-document-rule-compilation.md#acceptance-checks), with fixtures, denominators, and execution sequence in the [WP-19 plan](plans/long-document-rule-compilation.md). Add reviewed long-document expectations before model trials. Whole-document versus section-pipeline comparisons must use the same inputs; padding alone does not demonstrate extraction fidelity. Include remote exceptions, parent-heading context, changed shared definitions, missing external references, procedure isolation, and meaningful negative controls. A second model's audit or generated-rule tests cannot establish source completeness.

For A09, use a clearly labeled synthetic policy mutation or a second sourced version whose relevant rule changed. The existing BCBS pair's unchanged clinical pages cannot prove sensitivity to changed clinical requirements.

## Test layers

Unit tests cover the rule evaluator, state transitions, schema/domain validation, citation resolution, date/unit predicates, and artifact fingerprints. Include a failing control for meaningful assertions: changing an AND to an OR or swapping a cited page should cause the relevant tests to fail.

Integration tests exercise actual parser output, SQLite/file persistence, API contracts, and the OpenAI adapter with recorded or deliberately malformed responses. Separate fixture execution from a tagged live provider smoke test. Provider response fixtures verify adapter behavior, not model quality.

Saved browser tests cover the small number of user journeys that cross component boundaries: upload and successful review, mismatch, missing evidence, and actionable processing failure. Use explicit assertions on visible outcomes and source navigation. Exploratory review is useful feedback, but is not a repeatable release gate.

Live semantic evaluations run versioned prompts and the selected model against the annotated case set. Repeat representative success, uncertainty, and failure cases to expose variability; record the number of runs and every outcome. Report disagreement for human review instead of averaging it into a successful result. A second model may provide critique, but cannot establish ground truth.

## Metrics and release gates

| Measure | Definition and use |
| --- | --- |
| Applicability errors | Count known mismatches accepted and supported matches incorrectly blocked, with unresolved cases separate. |
| Criterion completeness | Fraction of annotated relevant criteria recovered, alongside logical-edge/exception errors. Report denominators and severity. |
| Citation validity | Fraction resolving to the correct input, page, and source span. This measures mechanical provenance, not semantic support. |
| Evidence recall | Fraction of annotated relevant evidence found; especially useful if later adding retrieval. |
| Finding correctness | Compare each status and its supporting rationale with reviewed expectations. Keep missing, negative, and conflict errors separate. |
| Unsupported satisfied findings | Count cases/criteria labeled met without evidence supporting the full requirement. A critical release blocker. |
| Operational behavior | Completion/failure counts, per-stage and end-to-end latency, attempts, input/output tokens, OCR pages if later supported, and provider/model/configuration. |
| Reviewer utility | Can a reviewer locate the relevant evidence, understand the gap, and identify the next documentation action? Record observed problems. |

For release, all mandatory deterministic checks must pass. The annotated release set must contain no known accepted applicability mismatch, fabricated citation, unsupported satisfied finding, omitted mandatory criterion/edge, or incorrectly evaluated mandatory branch. Each ambiguous or unsupported case must expose the intended review state. A failing critical case is fixed or the supported scope is explicitly narrowed and retested; changing the expected output to agree with the model is not a fix.

Publish the evaluation date, commit, input hashes, provider/model, SDK, prompts/schemas/parser versions, counts, failures, and limits. Report actual latency and token usage before choosing a latency or cost target. Any currency estimate needs a dated price source and the relevant provider/model/OCR assumptions. Do not reuse historical vault cost estimates as current pricing.

## Final verification record

M6 should add a short result file with the exact launch command tested, environment/prerequisites, build/typecheck/lint/test results, live case outcomes, source-inspection results, known limits, and remaining manual checks. Do not fill this with expected successes in advance. The [implementation plan](implementation-plan.md) remains incomplete until that evidence exists.

## October 19 WP-19 evidence boundary

The [runtime/check record](results/wp19-implementation.md) reports real 100/200-page fictional PDF parsing with independently authored condition/path gold, structural graph/source controls, durable recovery/reuse, configured SDK routing, and saved preparation journeys. The interpreter in those tests is scripted. A21 live source fidelity, rule/edge/exception recall, entailment, instruction resistance, repeatability, calibrated limits, and clean-checkout reviewer execution remain open. Expected insurer/patient outcomes above are unchanged.
