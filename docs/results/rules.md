# Pure provenance and rule core

Implemented on 2026-10-18 for [WP-10](../work-breakdown.md#wp-10-validation-and-evaluation-core). The package has no HTTP, provider, storage, or cloud calls. Integration status remains in the work breakdown. This report records the supported mechanical behavior; it does not establish clinical correctness, live-model accuracy, complete policy interpretation, or a working assessment workflow.

## Public interfaces and integration order

The source layer is [app.evidence](../../backend/app/evidence/validation.py):

- `CitationResolver(documents, extractions)` pins exactly one selected extraction for every document. `resolve(CandidateCitation, expected_document_id=...)` returns an addressed `SourceSpan`; `validate(SourceSpan, expected_document_id=...)` rechecks an existing span. Pass the expected policy/chart ID where a citation has a required role. `validate_policy` and `validate_facts` enforce the selected document roles and validate all nested sources.
- `check_predicate(criterion, fact, resolver, request=None)` returns `PredicateCheck(logical_value, reasons)`. It supports only the bounded numeric/date comparisons below. Narrative predicates return unknown because this function cannot perform semantic judgment.
- `validate_findings(policy, facts, findings, resolver, request=None)` checks domain references and citations, preserves existing missing/conflicting/review findings, and validates resolved judgments. Resolved numeric/date findings are recomputed from source-supported quantities; unsupported checks become `needs_review`. Both opposing comparison results become `conflicting`. Resolved narrative findings retain model judgment, subject to known uncertainty, context, conflict, and date checks.
- `predicate_support_reasons(criterion)` identifies known unsupported or unverified policy predicates independently of missing chart evidence. Its source spans must already have passed provenance validation.

The rule layer is [app.assessment](../../backend/app/assessment/rules.py). `evaluate_policy(policy, findings, applicability, issues=())` accepts a structurally valid policy and **already validated** evidence findings. It returns an immutable, serializable `EvaluationResult` with logical value, outcome, all node traces, a supporting path, and independent blockers. It cannot validate original bytes or fact references because it receives neither source bytes nor facts.

The workflow owner must convert provider candidates into domain records, resolve citations before consuming a stage, pass the selected request/cutoff into evidence checks, retain the original candidate for diagnostics, and persist the returned validated findings and traces. An invalid citation raises `CitationError` with a stable reason code; it is an invalid stage output, not a clinical gap. Cross-record errors raise `EvidenceValidationError`. Retry/repair policy and operational status handling belong to the workflow/provider layers.

## Citation boundary

Document IDs, declared SHA-256 values, selected extraction revision, one-based page, block ID, half-open Unicode character offsets, and excerpt must agree. Extraction/page inventory lengths must match. Cited pages must have usable extraction. If geometry is present, it must equal the preserved source block geometry. Ingestion remains responsible for hashing the actual uploaded bytes; the pure resolver verifies agreement between records, not file contents.

The only quotation normalization collapses runs of Python-recognized Unicode whitespace to one ASCII space and trims leading/trailing whitespace. It preserves spelling, case, punctuation, Unicode composition, and hyphenation. Returned spans contain the exact original substring and its offsets. No fuzzy search, changed number, case correction, dehyphenation, or cross-page search repairs a quote.

A candidate quote must have exactly one occurrence on its named page. Repeated or overlapping occurrences fail as ambiguous, even within the same block. A longer quote is required. One `SourceSpan` addresses one block; passages crossing blocks or pages require multiple citations. An existing quote may still be irrelevant or selectively omit important context. Mechanical resolution does not establish entailment.

## Supported comparisons

Numeric predicates support `gt`, `gte`, `lt`, `lte`, and `eq`, using decimal comparisons of the model's finite value **after** checking that value against source text. Accepted units are `mm`, `cm`, `m`, `ms`, `s`/`second`/`seconds`, `min`/`minute`/`minutes`, `h`/`hour`/`hours`, `day`/`days`, `consecutive_days` with the literal phrase “consecutive days,” `bpm`, and `%`. These are explicit spelling aliases; no scale conversion occurs. `cm` cannot silently become `mm`, nor hours become days.

The fact needs an explicit value and compatible unit. Its cited passages must contain one distinct matching quantity, and a quantity passage must contain the required context and selected target/side when supplied. Model context labels must also agree with the required context and source wording. Policy threshold and unit must occur in its cited policy text. Unsupported units, missing units, multiple incompatible quantities, fabricated values, recognized approximation/range/comparison/negation wording, scientific notation, and recognized compound-unit suffixes require review. The lexical checks are intentionally conservative; they are not a general measurement parser or proof that a value belongs to the claimed concept.

Date predicates support `before`, `on_or_before`, `after`, `on_or_after`, and `on` against an explicit calendar-date boundary cited in the policy. Supported roles are `event_date` and `documentation_date`. Source dates must use ISO `YYYY-MM-DD` with an explicit role label: `event date:` or `observation date:`; `documentation date:`, `report signed:`, or `documented:`. A model date that is not that literal form does not fail extraction and is not rewritten into a guessed calendar date. The cited condition stays unresolved, with a blocking review issue that asks staff to confirm the date. Multiple disagreeing dates, unsupported role labels, or a model date absent from the labeled sources require review. These label checks are a bounded input convention, not a date extractor.

When a cutoff is supplied, documentation availability must be established, and evidence dates after the cutoff require review. An event after its documentation date remains unresolved. Calendar months, relative recency, date arithmetic, inferred treatment duration, conversions between calendar periods, and free-form date semantics are unsupported. A literal completed consecutive-day quantity can be compared; the code does not reconstruct adherence from a date interval. The model still interprets the policy operator and relevance of the cited condition; presence of its threshold/date alone does not prove that interpretation.

## Aggregation and independent blockers

`met` maps to true, `not_met` to false, and missing/conflicting/review findings to unknown. AND is false when any child is false, true when all are true, and unknown otherwise. OR is true when any child is true, false when all are false, and unknown otherwise. Every child finding and unresolved reason remains in the trace. A true OR chooses the first true child in policy order for its displayed supporting path; other branches remain inspectable without becoming required documentation tasks.

Known unresolved policy sections, absent/unsupported predicates, unverified policy thresholds/date boundaries, and explicit blocking review issues prevent a satisfied outcome independently of tree truth. A true tree can therefore return `review_required` while retaining its supporting path. An otherwise unresolved root returns review for conflicts/review findings, or documentation gaps for missing evidence. A false root remains false and retains unresolved sibling evidence. Nonblocking issues do not become additional mandatory conditions.

Unresolved applicability produces no clinical trace or outcome; confirmed mismatch produces only the mismatch outcome. Supplying clinical findings before applicability is established is rejected. Structural cycles, missing references, and unreachable nodes remain rejected by the existing `Policy` schema. The pure evaluator requires one finding record per criterion, including explicit missing records for unused alternatives; it does not require each alternative to be satisfied.

A20 is covered for **known** unresolved governing sections/issues and unsupported interpretation. No deterministic function can discover an entirely omitted condition from prose it never received. Independent source-to-policy comparison and live semantic evaluation must still detect structurally valid but incomplete model interpretations.

## Verification

The tests cover all pairs of the five evidence states for AND/OR, an AND-to-OR counterexample, supporting paths, applicability gates, known completeness blockers, structural rejection controls, source identity/offset/quote ambiguity, numeric/date boundaries, units/context, source-unsupported model values, and evidence-reference integrity.

Fifteen applicable development cases from the independently reviewed WP-03 annotations exercise graph aggregation, including the ulcer alternative, negative/missing/conflicting states, changed rule, and second policy family. This test supplies the independent leaf states; it does not claim to extract or semantically validate them. It uses explicitly artificial logical-page extraction records. Reserved answers were not used for these implementation tests, and expected corpus files were not changed.

Final owned-package verification on 2026-10-18, Python 3.13.15:

```sh
uv run --project backend pytest -c backend/pyproject.toml tests/unit/test_rules.py tests/unit/test_provenance.py
uv run --project backend ruff check --config backend/pyproject.toml backend/app/evidence backend/app/assessment tests/unit/test_rules.py tests/unit/test_provenance.py
uv run --project backend ruff format --check --config backend/pyproject.toml backend/app/evidence backend/app/assessment tests/unit/test_rules.py tests/unit/test_provenance.py
uv run --project backend mypy --config-file backend/pyproject.toml backend/app/evidence backend/app/assessment tests/unit/test_rules.py tests/unit/test_provenance.py
git diff --check
```

Result: **140 tests passed**, Ruff lint and format checks passed, strict mypy passed for all six checked files, and the tracked diff had no whitespace errors. No live provider call was used. Full merged application/build/browser verification belongs to the integration owner and is separate from this pure-core evidence.
