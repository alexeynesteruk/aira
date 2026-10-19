# Candidate conversion record

Implemented for [WP-07–WP-09](../work-breakdown.md#work-packages-and-dependencies). [`backend/app/policies/conversion.py`](../../backend/app/policies/conversion.py) turns provider-shaped candidates into source-valid domain records. The module has no provider, HTTP, storage, or workflow side effects and no document-specific or procedure-specific rules. This record states the mechanical behavior of that boundary. It does not establish clinical correctness, live-model accuracy, complete policy interpretation, or a working end-to-end assessment.

## Entry points

| Function | Phase guard | Consumes | Produces |
| --- | --- | --- | --- |
| `convert_scope` | `checking_applicability` | `ScopeCandidate` plus annotations | `ScopeConversion` with the request context and applicability result |
| `convert_policy` | `interpreting_policy` | `PolicyCandidate` fragment | `Policy` plus review issues |
| `convert_chart` | `extracting_chart` | `ChartCandidate` | `ChartData` with saved sourced facts |
| `convert_findings` | `mapping_evidence` | `FindingsCandidate` plus already-saved facts | `EvidenceConversion` with validated findings |

`convert_policy` is the single policy converter. The long-document section compiler calls it per extracted section fragment, so a whole-guideline build and a single request-scoped interpretation share one validation path.

Every entry point runs inside a `_guard(phase)` context. A pydantic `ValidationError` or a raised `ValueError` becomes a `CandidateConversionError` carrying `ErrorCode.INVALID_OUTPUT`, the guarding phase, and the offending field locations. Citation failures surface as `ErrorCode.CITATION_INVALID` with the phase that consumed them. These are operational stage failures; the workflow turns them into a `failed` or retryable run, never into a clinical `missing` finding.

`convert_findings` deliberately does **not** build facts. Facts are produced once by `convert_chart` from the chart document alone and saved; assessment maps findings onto those saved fact IDs. This is the independent-extraction rule from TR-019. A removed earlier `convert_evidence` helper re-derived facts during mapping and had no production caller; it was deleted rather than kept as an untested seam.

## Unreadable model dates

A model may return a date in a form the application does not parse, such as `08/15/25` or `October 28, 2026`. Conversion never guesses a calendar date and never rewrites the candidate's text into an ISO string. Instead, each date field is read through `_literal_date`, which reports whether the supplied text was usable.

Behavior differs by field, deliberately:

| Field | Unreadable date behavior | Blocks readiness |
| --- | --- | --- |
| Criterion `date_boundary` | The predicate is dropped; the criterion keeps its cited wording, role, and sources. A review issue (`DATE_CONFIRMATION` / `DATE_CONFIRMATION_ACTION`) asks staff to confirm the date. | Yes |
| Policy `revision_date`, `effective_from`, `effective_to` | The field is left `None`. One `conversion-policy-date` issue (`POLICY_DATE_CONFIRMATION` / `POLICY_DATE_ACTION`) is added. It carries no source span because the candidate has no citation for its metadata fields; attaching the first criterion's passage would imply support that does not exist. | Yes |
| Chart fact `event_date`, `documentation_date` | The field is left `None` and the fact is **kept** with its proposition, value, unit, and sources intact. A non-blocking `CHART_DATE_CONFIRMATION` note naming the fact ID is appended to `ChartData.interpretation_issues`. | No |

The rationale is that a chart is the clinic's own document: a lost fact forces staff to re-scan a chart they already hold, so the fact survives and the uncertainty is visible. A policy date or a criterion boundary governs whether a result may be favorable at all, so those block readiness until confirmed. A dropped date is always `None`, never a parsed approximation, and the unreadable text never appears in the persisted record.

The readable path is unchanged: a literal `YYYY-MM-DD` that is also a real calendar date is used as-is. A value that is not in that literal form — including an eight-digit `20260230` or an impossible `2026-02-30` — is treated as unreadable, never silently carried. It becomes the field-specific confirmation behavior above rather than a hard conversion failure.

## Provenance and structural checks

`_citations` resolves every candidate citation through the `CitationResolver` and rejects a quote that is absent, ambiguous, or attributed to the wrong role. Charts resolve only against the chart extraction and policies only against the policy extraction, so a fact cannot cite policy text even when the same words exist there.

`Policy` and `ChartData` schema validation then enforces structure: unique criterion and fact IDs, acyclic and reachable nodes, nonempty logical groups, fact conflicts that reference known siblings, and sources whose document ID and SHA-256 match the artifact. `validate_findings` re-checks domain references, recomputes resolved numeric and date judgments from source-supported quantities, and preserves `missing`, `conflicting`, and `needs_review` states as issued. See the [rules record](rules.md) for that layer.

## Verification

```sh
uv run --project backend --locked pytest -c backend/pyproject.toml tests/unit/test_candidate_conversion.py
uv run --project backend --locked ruff check --config backend/pyproject.toml backend/app/policies tests/unit/test_candidate_conversion.py
uv run --project backend --locked mypy --config-file backend/pyproject.toml backend/app/policies
```

Observed October 19, 2026: **62 tests passed**; Ruff lint and strict mypy passed. The suite covers scope/applicability conversion, policy graph conversion, chart fact conversion, findings mapping, unreadable-date handling for all three field groups above, citation role isolation, ambiguous and invented quotes, and every invalid-input class that must become an operational failure rather than a coverage gap.

These checks use hand-built candidates. They do not measure live rule recall, entailment, exception fidelity, or repeatability; those remain open under the recorded quota deferral and are owned by WP-16/LD-09.