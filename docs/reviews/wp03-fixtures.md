# WP-03 independent fixture review

Reviewed on 2026-10-18 by the Codex assessment reviewer, separately from the fixture author. This review accepts the current corpus as an initial source-consistent engineering reference set. No blocking disagreement remains between the authored source text and its expected answers after the corrections below. This is not clinical validation, an assessment of payer policy correctness, or evidence that the application passes the scenarios.

Implementation status remains in the [work breakdown](../work-breakdown.md#wp-03-annotated-fixtures-and-evaluation-expectations). The [coverage register](../../evals/coverage.json) and [construction tasks](../../evals/construction-tasks.json) retain the checks that are still unimplemented or unexecuted.

## Scope and method

The reviewed corpus contains 17 development cases, one reserved case, and 23 registered sources: 20 fictional Markdown documents and three supplied/public PDF references. I read the fictional policies and charts against the independent policy annotations, findings, applicability decisions, and selected request metadata. I traced the flat rule graphs back to the stated connectives, checked positive and negative evidence meaning, and reviewed the source-bound section inventories. Expected answers were not derived using the application evaluator, provider output, or a live model run.

For the supplied mismatch, I independently checked the three registered PDF hashes and inspected the cited chart pages 1 and 7 and the 2025 guideline page 1 using `pdf-inspect` and `pdf-extract`. The chart payer, plan, and procedure-code excerpts and the guideline subject excerpt match those pages. The policy publisher's identity is documented in the [guideline provenance](../../examples/guidelines/README.md); the subject mismatch is independently visible in the documents. This review did not perform a new full clinical comparison of the two BCBS versions.

The corpus integrity test was reviewed separately. It checks source hashes, exact logical-page selectors, references, graph structure, annotation invariants, contrast pairs, and reserved-set separation. It does not compute clinical truth or make a live inference call. Markdown page markers are logical fixture pages, not proof of PDF pagination. Runtime extraction IDs, blocks, and offsets must be produced by the future parser adapter rather than invented in these annotations.

## Findings by scenario

| Scenarios and cases | Independent assessment |
| --- | --- |
| A01: `supplied_pair_mismatch` | The pacemaker request and venous-treatment guideline do not match. Applicability stops before clinical findings; the expected empty findings and null logical value are appropriate. Missing service-date details cannot repair the procedure mismatch. No medical-necessity conclusion follows. |
| A02–A05: matched, missing diameter, negative reflux, conflicting diameter | The matched chart supports the required symptom branch. Omitted diameter remains `missing`; explicit absence of reflux is `not_met`. The two incompatible measurements remain `conflicting`, with both observations retained and no assumed supersession. |
| A06–A07: ulcer alternative and false-plus-unknown | The source expressly permits an ulcer alternative without compression. Unused symptom-branch findings remain missing while the satisfied path establishes the root. A false mandatory reflux condition makes the root false while the separate missing diameter is retained. |
| A08–A09: thresholds, missing unit, changed policy | Below/at/above the inclusive diameter boundary produce the expected states. A unitless number requires review. The same chart fails the deliberately raised fictional threshold. This is a controlled rule change, not a claim that the real BCBS clinical requirements changed. |
| A11: monitoring family | The distinct procedure family uses its own requirements. An explicit statement that no prior tracing captured the episodes supports the policy's absence requirement; negative wording is not automatically contrary evidence. |
| A05/A12: date conflict, wrong side, unknown plan | A future observation with an earlier signature cannot establish valid pre-cutoff evidence; `needs_review` preserves the conflicting context. Left-side imaging does not satisfy right-side requirements, so the right-side facts remain missing. An undocumented plan stops at `needs_input`, without findings or a clinical outcome. |
| A18: embedded instruction | The untrusted instruction does not change the source-authored expected findings. In particular, an explicitly absent ulcer remains `not_met`; the legitimate symptom branch independently satisfies the policy. |
| A19: reserved pair | The independently stored input and expectations agree with their authored policy and request. Review does not make this pair blind: it was authored alongside the corpus and read during this review. It remains excluded from tuning/default live runs. |
| A20: policy completeness | The section inventories account for scope, requirements, alternatives, target/cutoff context, and the provenance caveat in the fictional texts. A complete expected graph exists. The application test for detecting a structurally valid partial interpretation remains open. |

## Corrections resolved with the author

- Applicability rationales previously exceeded their cited evidence. Applicable cases now cite policy procedure scope and effective date plus chart request, service date, and cutoff; the unknown-plan case also cites the policy's required plan.
- The unresolved measurement conflict previously used preliminary/final report labels, which could imply a priority rule. The source now uses Report A and Report B and expressly leaves supersession unexplained; expectations and source hashes were updated by the author.
- The wrong-side issue now cites both the left-side reflux statement and the left-side measurement, so both missing right-side findings can be investigated.
- Policy annotations now retain source-bound section inventories and governing context as well as the flat requirement graph. These give subsequent interpretation checks an independent completeness reference.

The reviewer did not edit the corpus or silently revise expected answers.

## Remaining limits and decisions

The fictional compression rule states 90 consecutive days. It deliberately avoids interpreting calendar months, adherence schedules, or clinical sufficiency. The observation/signature conflict is intentionally unresolved; a future implementation must not fix its dates or choose a valid-looking date merely to obtain a favorable result. The author supplies simple direct statements for the other synthetic requirements, so these examples do not establish performance on ambiguous clinical prose.

The integrity mutation that deletes a graph node while leaving its criterion catches a structural inconsistency. It does **not** test A20's harder case where both the governing criterion and its graph node are omitted, leaving valid JSON and a valid partial graph. FT-03 and FT-11 must still exercise that omission against the independently complete source annotations and block an unsupported satisfied outcome.

Actual PDF rendering/pagination, table and column extraction, OCR, larger charts, duration/recency edge cases, runtime citation resolution, provider failures, persistence, UI/export flows, and live semantic evaluations remain assigned in the construction-task register. The original chart's timeline also needs its own extraction checks; stopping at applicability does not test temporal extraction. Review completion closes only the independent source-consistency portion of the work, not all of FT-11 or A01–A20.

The reserved pair must be replaced before release if its answers inform implementation or prompt tuning. FT-12 still calls for a separately curated/reviewed PDF pair and a fresh-checkout workflow. No corpus score, runtime success rate, or clinical accuracy estimate is established here.

## Verification record

After the author recorded the completed source review in annotation provenance, the reviewer ran:

```sh
uv run --project backend pytest -c backend/pyproject.toml tests/unit/test_evaluation_fixtures.py
```

Result: **23 passed**, Python 3.13.15, on 2026-10-18. Review-document links and anchors also resolved. These results establish corpus integrity, not application acceptance.

The following SHA-256 snapshot identifies the reviewed manifests and answers. The source registry pins the individual source-document bytes. Later answer or source changes require corresponding review; routine runtime execution records are separate.

| File | SHA-256 |
| --- | --- |
| `evals/source-registry.json` | `2690da52af36a43a56bc729273b68a108dd52fa8bd207fbd73707539dc34d448` |
| `evals/cases/development.json` | `d75728e6c81fb5673c2e309b15fe16cfc1357a567583bfa2243463cb80736255` |
| `evals/cases/held-out.json` | `5e472105ee8328606262e4399e4c9a720a255a2d77efc862777384eae34e7462` |
| `evals/expected/policies.json` | `38d6b70cd9da03790cde05e7cb80a870a0f436b27998a261c6dab01c926ab293` |
| `evals/expected/development.json` | `68fbd652754ed280c130f1f42171ebb3da031803e73ff873245f1324f4ca9348` |
| `evals/expected/reserved.json` | `5613a995014959e2986d549c1fe2261cc73e00b02a051b00e7d23d036b0685e2` |
| `evals/coverage.json` | `13295014d91bb6d25d68fa3568774e4443f8b3901f529d27837a9def058738ec` |
| `evals/construction-tasks.json` | `1447bd9ec77cb044b6878fe22efe8463f10350bdf760ca9cbf09c548f05dacf5` |
