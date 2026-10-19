# Long-document rule extraction research

Researched October 18, 2026 through the `web-headed` skill's real browser. This records public engineering research and the user's subsequent product decision. It is not an Aira implementation or model-quality result. Requirements live in the [BRD](../requirements/business-requirements.md) and [TRD](../requirements/technical-requirements.md); [WP-19](../features/19-long-document-rule-compilation.md) owns feature acceptance and tasks.

## Question and decision

How should Aira turn a 100–200-page insurer guideline into a detailed, sourced, reusable rule set without relying on a single document-sized model response?

Adopt structure-aware decomposition, contextual section extraction, explicit dependency reconciliation, coverage auditing, and deterministic compilation. Persist intermediate artifacts and the resulting versioned rule set. Policy processing remains independent of charts and requests. Chart processing remains independent of policies. Direct OpenAI access using the reviewer's backend API key is required; a compatible endpoint remains optional.

## Primary sources inspected

| Source | Observed approach | Application and limits for Aira |
| --- | --- | --- |
| [Google: Introducing LangExtract](https://developers.googleblog.com/introducing-langextract-a-gemini-powered-information-extraction-library/) | Smaller extraction contexts, parallel processing, repeated extraction passes, schema guidance, and source-character alignment. | Useful extraction pattern. Exact offsets establish traceability, not that an exception was interpreted correctly. The library does not supply an insurer-policy compiler. Do not use model world knowledge to add coverage rules. |
| [DocETL paper, sections 2–3](https://arxiv.org/html/2410.12189v2) | Split/gather/map/reduce operators; document metadata and heading context; resolution of duplicate concepts; bounded validation/refinement. | Use explicit stages and reconciliation. The paper does not establish Aira accuracy or require adopting its agentic optimizer. A merge must preserve records and source relationships rather than summarize them away. |
| [Docling chunking documentation](https://docling-project.github.io/docling/concepts/chunking/) | Hierarchical document elements with metadata, token-aware splitting/merging, and table-header preservation. | Preserve headings, list ancestry, table labels, and source coordinates when dividing text. Evaluate the existing parser before replacing it or adding dependencies. |
| [AWS: Create an Automated Reasoning policy](https://docs.aws.amazon.com/bedrock/latest/userguide/create-automated-reasoning-policy.html) | Source-to-rule/variable translation, focused incremental policy building, review of duplicates/conflicts/missing rules, and fidelity reports connecting source statements to rules. | A useful analogue for a build/review workflow. This is not a recommendation to adopt Bedrock. Do not copy its optional inferred or common-sense rules into Aira's source-derived coverage logic. |
| [AWS: Test an Automated Reasoning policy](https://docs.aws.amazon.com/bedrock/latest/userguide/test-automated-reasoning-policy.html) | Separates tests of encoded rule semantics from tests of natural-language translation. | Evaluate extraction, compilation, and patient evidence interpretation separately. Tests generated from an incorrect extracted policy cannot establish source completeness. |
| [Lost in the Middle, TACL 2024](https://aclanthology.org/2024.tacl-1.9/) | Found position-sensitive retrieval degradation in the models and tasks studied. | Motivation for testing long-context recall. It does not prove that every present model fails on 200 pages or establish an appropriate Aira chunk size. |

## Findings and Aira-specific inferences

The recurring pattern is a data pipeline with durable intermediate records. Chunking solves input size; gathered context and reconciliation address meaning distributed across sections. A token-budgeted call still needs sufficient output space for all extracted records.

For Aira, a heading such as “additional requirements” must retain its parent procedure and introductory conditions. An exclusion near the document's end may govern a requirement near its start. Page-by-page extraction alone cannot establish that these relationships survived.

Use a complete source inventory to account for every section. Retrieve references and definitions as supplementary context; top-k retrieval does not establish exhaustive guideline coverage. Summaries can help routing but cannot replace the original passages behind rules.

Keep three claims separate: schema-valid JSON, mechanically valid and repeatable rule execution, and faithful source interpretation. The first two can be checked deterministically; the third requires independently annotated cases and review. Model self-audits can find errors but cannot certify completeness.

The current working tree contains document-only interfaces, persisted rule/fact artifacts, a page-range helper, and a page-index/serial-fold prototype. Their presence is not completion evidence for this design. Excerpt-based page skipping, whole-graph rewriting on each page, and partial-build publication require explicit review against WP-19.

## Decisions left to experiments

- Measure tokenizer, section/input-output budgets, maximum concurrency, whole-build deadlines, and attempt caps on representative inputs. No universal chunk size or latency/cost target is established here.
- Demonstrate both 100- and 200-page native-text builds before advertising that envelope. Existing parser limits must be tested and deliberately amended; a larger context window alone is insufficient.
- Compare a feasible whole-document baseline with section extraction on the same reviewed inputs. Include boundary-spanning alternatives, remote exceptions, repeated terms, and distractors.
- Choose libraries only after the experiment identifies a gap in the current parser or orchestrator. Start with the existing FastAPI/Pydantic/SQLite architecture and configured inference adapter.
- Keep live trials separate from fixtures and respect the recorded quota deferral. No additional paid inference was performed for this research.

The executable design and implementation sequence are in the [WP-19 implementation plan](../plans/long-document-rule-compilation.md). The [work breakdown](../work-breakdown.md) remains the implementation status ledger.
