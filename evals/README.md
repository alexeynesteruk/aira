# Independent evaluation inputs

This corpus contains explicitly fictional text policies/charts, source-authored expectations, and a hash-pinned reference to the supplied mismatched PDF pair. It prepares WP-03. It is not a model benchmark, a clinical validation, a working PDF parser, or evidence that the application passes these cases.

The fictional policies deliberately define small test rules. They are not payer guidelines and must never supply production coverage rules. The venous examples exercise AND/OR, negative evidence, unknown values, context, and policy changes. The ambulatory-monitoring examples provide a second procedure family, including a negative statement that supports an absence requirement.

## Files and ownership

| Artifact | Purpose |
| --- | --- |
| [Source registry](source-registry.json) | Repository-relative paths, exact byte hashes, document roles, source origin, and development/reserved split. |
| [Development cases](cases/development.json) | Input/request pairings and expected-record references for tuning and development. |
| [Development expectations](expected/development.json) | Explicit applicability, evidence states, logical outcomes, source excerpts, and unresolved reasons. |
| [Policy annotations](expected/policies.json) | Source-bound requirements, connectives, and complete intended rule graphs. |
| [Reserved manifest](cases/held-out.json) | A separate release candidate pair excluded from tuning and default live runs. |
| [Reserved expectations](expected/reserved.json) | The reserved pair's independently authored target behavior. |
| [Scenario coverage](coverage.json) | A01–A20 mapped to actual inputs and concrete remaining work. |
| [Construction tasks](construction-tasks.json) | Explicit outstanding PDF, parser, provider, workflow, UI, and release checks. |

Implementation status remains in the project work breakdown. Fixture task status concerns only the named missing artifact; an input's existence never marks an application feature complete.

## Annotation contract

Expectations were written directly from the authored sources, not emitted by an application evaluator or a live provider run. A separate Codex assessment reviewer completed a [source-consistency review](../docs/reviews/wp03-fixtures.md) on 2026-10-18. Annotation provenance names the author, reviewer, date, and review artifact. That review accepts the engineering reference set; clinical validation, runtime semantic adjudication, and live model evaluation remain unfinished. These records contain no live-model scores or fabricated provider responses, and FT-11 remains open.

The annotation schema uses the application's semantic vocabulary: policy nodes have `node_id`, `kind`, `children` or `criterion_id`; findings use the five established status names; applicability is `applicable`, `mismatch`, or `unresolved`. Policy annotations include scope summaries, identity/dates, and source-bound section inventories that link requirements and retain governing context. An evidence selector contains `source_id`, one-based `page`, and an exact `excerpt`, with a supporting, contradicting, or context relation. These are independently reviewable selectors, not fabricated runtime `SourceSpan` objects. A parser/evaluation adapter must resolve them to actual extraction revisions, block IDs, offsets, and source hashes before comparing application outputs.

Markdown markers such as `<!-- page:1 -->` define **logical fixture pages**. They do not assert a rendered PDF's pagination or layout. PDF rendering, table/column fixtures, and OCR variants remain explicit construction tasks. The supplied PDF mismatch excerpts were inspected using `pdf-inspect` and `pdf-extract`; corpus tests hash those originals and check annotated page bounds, but do not parse PDFs or independently reverify their excerpts.

## Important contrast pairs

- `venous_matched`, `venous_missing_diameter`, and `venous_negative_reflux` distinguish supporting evidence, absent evidence, and explicit contrary evidence.
- `venous_conflicting_diameter` preserves both threshold-crossing observations; `venous_date_conflict` preserves incompatible dates and post-cutoff evidence.
- `venous_ulcer_alternative` satisfies the ulcer branch while the unused symptom branch remains missing. `venous_false_and_unknown` retains unknown information even when another mandatory condition is false.
- The diameter cases are below, at, and above the inclusive 3.0 mm fixture boundary. Missing units require review.
- `venous_rule_changed` uses exactly the matched chart against an intentionally changed 4.0 mm requirement. This differs from the real BCBS snapshots, whose clinical pages were observed unchanged.
- `venous_unknown_plan` stops for input without clinical findings. `supplied_pair_mismatch` stops at applicability; the source chart's chronology is a separate extraction check.
- `venous_embedded_instruction` must preserve the baseline findings, including the contrary ulcer finding, despite text asking to mark everything satisfied.

## Reserved set and remaining evidence

The reserved pair is separately stored and unused by live inference. It was authored alongside this corpus and is **not claimed to be blind**. Do not use its expected answers for prompt tuning. If it informs implementation or fails and becomes a development example, record that transition and replace it before release. The release owner must independently curate/review the final PDF pair and run the fresh-checkout workflow.

The corpus validator checks hashes, exact text selectors, graph/reference integrity, evidence-state annotations, contrast pairs, split isolation, and explicit scenario construction work. Passing it establishes fixture consistency only. Runtime provenance, rule evaluation, semantic quality, provider behavior, browser behavior, OCR, and release delivery require their own checks.
