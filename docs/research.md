# Prior authorization implementation research

Research date: October 17, 2026. This review compares public reference implementations and primary library documentation with the Aira assessment. Recommendations below are engineering judgments for this project. Public samples demonstrate patterns; they do not establish production accuracy, prevalence, or a measured reduction in denials.

The [October 18 long-document follow-up](research/long-document-rule-extraction.md) and [WP-19 implementation plan](plans/long-document-rule-compilation.md) supersede the initial whole-document-call recommendation for long-guideline preparation. The earlier research below remains historical rationale, not long-document acceptance evidence.

## Recommended direction

Build a provider-facing evidence and documentation gap assistant. Start with a staged Python pipeline, a small upload and review UI, and explicit structured results. Use the uploaded policy as the source of requirements, retain page-level evidence, and keep staff in control of unresolved findings.

For the first experiment, process the complete guideline and chart when they fit the chosen model's measured limits. Compare that baseline with section-based retrieval before introducing a vector database. The assessment and Obsidian reviews informed FastAPI, React/TypeScript, Pydantic, and local SQLite/artifact storage. On October 18 the user selected OpenAI for initial inference. The exact model and native PDF limits still require representative-input experiments; unsupported scans are explicitly rejected initially. See the [implementation plan](implementation-plan.md) and [model provider decision](model-provider.md) for current decisions.

## Patterns in public implementations

| Source | Pattern observed | Relevance to Aira |
| --- | --- | --- |
| [Azure AutoAuth](https://github.com/Azure-Samples/autoauth-solution-accelerator) | OCR and clinical extraction followed by hybrid vector/BM25 policy retrieval and an assessment stage. | Retrieval helps when selecting from a policy collection; the take-home already lets the user supply the policy. |
| [Microsoft multi-agent accelerator](https://github.com/microsoft/Prior-Authorization-Multi-Agent-Solution-Accelerator) | Separate compliance, clinical, coverage, and synthesis agents with per-criterion findings and human review. | The staged responsibilities are useful. Four deployed agent services add complexity beyond the initial workflow. |
| [Anthropic prior authorization assessment reference](https://github.com/anthropics/healthcare/blob/main/plugins/healthcare/skills/prior-auth/references/01-intake-assessment.md) | Payer-side review with policy lookup, criterion-level MET / NOT_MET / INSUFFICIENT findings, supporting evidence, and gaps. | Borrow the distinction between finding states. Payer decision rules and mandatory external lookups do not define our provider-facing product. |

Across these examples, the recurring useful abstraction is **policy requirement → chart evidence → criterion finding → reviewable gaps**. This supports a checklist workflow more directly than an open-ended chat interface.

## Reddit workflow findings

Read four public discussions, including their visible comments. These are a small, self-selected sample. Claimed roles, deployments, and outcomes are unverified, and several participants promote products. Use the discussions to generate product hypotheses and evaluation cases, not to validate an implementation or rank vendors.

| Discussion and post date | Observations from the discussion | Implication for our MVP |
| --- | --- | --- |
| [Cardiology prior authorization AI tools](https://www.reddit.com/r/PriorAuthorization/comments/1wlgsb0/caridiology_prior_auth_ai_tools/), September 20, 2026 | The author describes cardiology-specific difficulties. A commenter claiming to review cardiac requests says generic summaries are skipped; another contrasts concise relevant notes with sending an entire chart. A disclosed vendor advocates a copilot workflow. | Show the exact criterion and supporting chart passage. Test whether a user can inspect the relevant evidence quickly. |
| [Prior authorization automation](https://www.reddit.com/r/PriorAuthorization/comments/1wtqyvg/prior_authorization_automation/), September 30, 2026 | Medication-focused discussion includes complaints about opaque processing and onboarding, plus a suggestion to examine cases that get stuck and identify the next actor. Product recommendations and claimed success rates are mixed into the replies. | Show processing state, unresolved gaps, and the next review action. Do not treat a faster upload as the whole user outcome. |
| [Automating prior authorizations in healthcare](https://www.reddit.com/r/automation/comments/1mt2x1x/automating_prior_authorizations_in_healthcare/), August 17, 2025 | Startup feedback thread emphasizes fitting practice workflows. A disclosed automation vendor describes exception handoff with context as a major adoption issue. | Make partial results and failure states useful to staff. Retrying without explanation is an inadequate handoff. |
| [Parsing PDF tables accurately](https://www.reddit.com/r/Rag/comments/1ti6zw8/how_to_parse_tables_from_pdfs_with_100_accuracy/), May 20, 2026 | The author reports merged and split columns despite readable text. Replies mix validation suggestions, conflicting tool experiences, and vendor promotion. | Benchmark table alignment and detect suspect outputs on our own documents. The parser capabilities below are grounded in primary documentation, not these comments. |

Excluded from the recommendation: anecdotal approval percentages, universal claims about vendor staffing, and claims of perfect parsing. Medication workflows also do not establish how vascular procedure authorization works.

## Findings from the example guideline

The [assessment-linked PDF](https://mcgs.bcbsfl.com/MCG?activity=openSearchedDocMcg&imgId=76F3FX62Y9H67N4ZU69) is revised August 15, 2025. The [policy-ID endpoint](https://mcgs.bcbsfl.com/MCG?mcgId=02-33000-31&pv=false), retrieved October 17, 2026, serves a January 1, 2026 revision. Its update log identifies removal of CPT 37500; text comparison detected no changes on clinical criteria pages 1–4. Preserve the selected snapshot and service date instead of silently substituting a newer policy.

Page 2 has nested AND/OR requirements. The three-month compression requirement sits within the persistent-symptom alternative, rather than across every indication. A flat checklist can therefore impose an extra requirement. Separate branches also depend on the vein treated, prior procedures, and timing; program exceptions appear on page 7. These are source-specific extraction findings, not a coverage decision for a patient.

Use the local [versioned snapshots](../examples/guidelines/README.md) to test branch extraction and policy changes. The supplied pacemaker chart remains an applicability mismatch.

## What to avoid copying from reference code

Public samples sometimes define separate insufficient and contradictory evidence decisions, then map both to `NOT_MET`, or label a case compliant using an 80% criterion threshold and average confidence when critical criteria pass. Those are implementation choices, not medical necessity rules we should inherit. Aira retains distinct states and evaluates the actual policy's required combinations.

Some samples also adjust confidence from the lengths of evidence and reasoning text. That is not evidence that the resulting number estimates correctness. Prefer visible evidence and measured error rates over an uncalibrated percentage in the MVP.

The [Microsoft decision rubric](https://github.com/microsoft/Prior-Authorization-Multi-Agent-Solution-Accelerator/blob/main/docs/architecture.md) includes an approval fallback when no policy is found but clinical evidence is strong. That is outside our proposed product contract: a missing or mismatched guideline should require clarification rather than produce a supported-by-policy result.

The [AutoAuth pipeline](https://github.com/Azure-Samples/autoauth-solution-accelerator/blob/main/src/pipeline/paprocessing/run.py) selects the first retrieved policy and explicitly marks this choice for improvement. Our policy selection needs to remain visible, especially because the supplied Aira chart and named policy do not match.

These observations come from static source inspection. The reference applications have not been installed or benchmarked in this workspace.

## Document extraction options

| Option | Documented capability | Proposed use |
| --- | --- | --- |
| [pdfplumber](https://github.com/jsvine/pdfplumber) | Page and character coordinates, text and table extraction, visual debugging; best suited to machine-generated PDFs. It does not provide OCR. | A lightweight baseline for the supplied text PDFs. Check column reading order and label/value associations. |
| [Docling](https://github.com/docling-project/docling) | Layout and reading order analysis, table structure, OCR, a structured document representation, and JSON/Markdown exports. | Compare against the baseline on difficult tables, scans, and page-spanning sections. Include setup and processing time in the comparison. |

Do not choose a parser by a generic ranking. On our small corpus, compare extracted payer and procedure fields, negation, table values, dates, page provenance, and cross-page continuity. Keep original PDFs available in the review UI. A successful text extraction is not proof that the reading order is correct.

## Proposed processing stages

1. **Ingest and inspect.** Assign a content hash, preserve the original PDF, extract page text, and detect pages requiring OCR or review.
2. **Identify the request and policy scope.** Extract payer, plan, procedure, laterality where relevant, service date, policy identifier, effective dates, and covered scope. Ask for clarification when multiple requests or ambiguous applicability remain.
3. **Extract the policy requirements.** Preserve named indications, exclusions, AND/OR groups, thresholds, units, required duration, and relevant notes. Every criterion points back to policy text.
4. **Locate evidence against each criterion.** Return supporting, contradicting, missing, or conflicting evidence with document IDs, page numbers, and source quotations. Separate what a clinician documented from what the model inferred.
5. **Validate and aggregate.** Validate the output schema and references in code. Evaluate explicitly represented logical groups and supported comparisons. Keep unsupported interpretations unresolved.
6. **Present a review checklist.** Show applicable policy, criterion findings, exact evidence, documentation gaps, and unresolved conflicts. Let staff inspect source pages and correct extracted information.

Use schema validation such as [Pydantic strict mode](https://github.com/pydantic/pydantic/blob/main/docs/concepts/strict_mode.md) where silent coercion would be harmful. Schema validity only establishes shape and types; separate checks must address whether quotations exist, citations resolve, criteria are complete, and the interpretation is justified.

## Where judgment should live

**Policy data** contains the uploaded document, scope, version, criteria, logical groups, and source references. Updating a supported guideline should produce new policy data rather than require editing procedure-specific conditions in Python.

**Model judgment** handles prose interpretation, candidate evidence selection, negation and time context, and criterion interpretation where ordinary language is involved. This remains fallible even when a response matches its JSON schema.

**Application code** handles validated states, provenance checks, supported logical operators, numeric comparisons with explicit units, error handling, and result aggregation. A deterministic evaluator cannot repair an incorrectly extracted policy rule; its trace should expose the inputs it evaluated.

**Staff judgment** resolves ambiguous scope, conflicting chart facts, and unsupported policy language. Unknown must not silently become satisfied or unsatisfied.

The [architecture](architecture.md#finding-and-aggregation-semantics) defines `met`, `not_met`, `missing`, `conflicting`, and `needs_review`, mapping to true/false/unknown while preserving the original reasons. Scope exclusions are evaluated separately and require source support. The [evaluation cases](evaluation.md) cover their aggregation semantics.

## Full context and retrieval

An uploaded policy and a short chart do not automatically require embeddings or a policy search service. A full-context baseline keeps the first experiment small and makes retrieval omissions easier to isolate. It still needs token limits, source tagging, and evaluation of misplaced or missed evidence.

For longer inputs, retrieve per criterion using section structure and potentially hybrid lexical/semantic search. Include neighboring context, exclusions, definitions, and policy-wide requirements. Measure evidence recall separately from answer quality. Keep policy and patient evidence in separate document scopes.

The [Lost in the Middle research repository](https://github.com/nelson-liu/lost-in-the-middle) provides experiments with relevant passages placed at different positions among distractors. A useful test adapted to this project is moving decisive evidence to the beginning, middle, and end of a chart. This is a proposed test, not a benchmark result for our eventual model.

## Evaluation before framework expansion

Use a small set of hand-reviewed cases with expected criteria, evidence, and findings. The [AutoAuth evaluation framework](https://github.com/Azure-Samples/autoauth-solution-accelerator/blob/main/evals/README.md) separates declarative case expectations from pipeline execution; that separation is useful without adopting its cloud evaluation stack.

Include at least these scenarios: matching policy and supported evidence; missing required documentation; explicit negative evidence; an OR branch; an AND branch with one missing requirement; numeric boundary and unit cases; a mismatched payer or procedure; contradictory chart dates; a changed policy; and a scan or malformed PDF.

Measure applicability errors, criterion extraction completeness, citation validity, evidence recall, unsupported satisfied findings, and correct handling of uncertainty. Also record latency and model cost per case. A polished explanation should not compensate for an incorrect criterion result.

## Application structure

Use FastAPI, React with TypeScript, Pydantic schemas, and a thin OpenAI Responses API adapter. This aligns with Aira's stated stack while keeping policy logic outside the UI. Local files and SQLite preserve saved runs without additional services. Postgres, retrieval, queues, and agent orchestration require demonstrated needs.

The [implementation plan](implementation-plan.md#planned-repository-structure) owns the folder structure and the one-line launch contract. The backend/frontend foundation and shared contracts are implemented; current package evidence is in the [work breakdown](work-breakdown.md#implementation-evidence). Browser checks pass in GitHub Actions. The complete live workflow still requires clean-checkout verification with documented OpenAI credentials and available API quota.

## Extension path

For a later integrated product, study the [HL7 Da Vinci electronic prior authorization workflow](https://github.com/HL7/davinci-pas/blob/master/input/pagecontent/epaWorkflow.md), including interactions between provider systems, payer systems, and prior authorization coordinators. This concerns system exchange and workflow integration; it does not replace interpretation of medical necessity prose. FHIR and insurer submission belong after the PDF-to-checklist MVP for this assessment.

## Research limits and next experiment

This is a targeted review of relevant Reddit threads, public code, library documentation, an experimental research repository, a standards repository, and the actual example policy. It is not an exhaustive search of the internet. No external accuracy, latency, or approval-rate claim has been adopted as an expected outcome for Aira.

Contracts and the independently reviewed two-family text corpus are implemented. Parser and isolated OpenAI experiments now follow the [stable milestones](implementation-plan.md#implementation-sequence). The supplied pair remains the mismatch case. Live inference is deferred until project quota is available; the [feasibility record](results/model-feasibility.md) records the observed failure and repeatable commands. Inspect criterion structure, citations, failures, latency, and usage before adding retrieval or an agent framework.

## October 18 follow-up: long-document rule extraction

The user requires independent persisted guideline and chart extraction, and complete rule-set preparation for 100–200-page guidelines. The [dated research log](research/long-document-rule-extraction.md) records primary sources inspected through the web-headed browser: Google LangExtract, Berkeley DocETL, Docling, AWS policy-to-logic building/testing, and the TACL long-context study. It separates observed claims from Aira-specific inferences and unmeasured limits.

The accepted design is structure-aware decomposition, contextual section extraction, explicit dependency reconciliation, coverage/omission auditing, deterministic compilation, and immutable intermediate/final artifacts. A top-k retrieval result or a short page excerpt cannot establish complete coverage. JSON shape, graph validity, and source-faithful interpretation require separate checks.

Implementation is [WP-19](features/19-long-document-rule-compilation.md), with BR-013/TR-019/A21 and a [task-by-task execution plan](plans/long-document-rule-compilation.md). Direct OpenAI using the reviewer's backend key is required; LiteLLM remains optional. These are design/specification findings, not implementation or live accuracy results.
