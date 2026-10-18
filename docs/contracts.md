# Domain and interface contracts

WP-02 establishes schema version `0.1.0` in `backend/app/schemas/`. Public classes are exported from `app.schemas`; they perform no HTTP, filesystem, database, model, or cloud operations. [The TRD](requirements/technical-requirements.md) owns behavior, and [WP-02](work-breakdown.md#wp-02-domain-and-interface-contracts) owns completion status.

## Loading and immutability

Use `Model.model_validate_json(payload)` at a JSON boundary and `model_dump_json()` for serialization. Strict Python construction requires the declared types, including enum members, dates, and tuples; it does not coerce numeric strings or booleans into integers. JSON dates and timestamps use ISO formats; timestamps require a timezone. Unknown fields and unsupported schema versions are rejected. Models are frozen and collections use tuples so validated records cannot be changed in place. Create and validate a new snapshot rather than using unchecked `model_copy(update=...)` as an update mechanism.

## Public record groups

| Group | Public contracts |
| --- | --- |
| Sources | `DocumentRecord`, `PageInventory`, `ExtractionRecord`, `ExtractedPage`, `TextBlock`, `SourceSpan`, `BoundingBox`. Page numbers are one-based; offsets are half-open Unicode character offsets within a block. Bounding boxes use PDF points with a top-left origin. |
| Request | `RequestContext`, `FieldSources`, `TextAnnotation`, `DateAnnotation`, `ApplicabilityResult`. Only request metadata is editable. Conflicting metadata resolutions retain original spans and an explicit reason. |
| Policy | `Policy`, `Criterion`, `AllNode`, `AnyNode`, `CriterionNode`, `PolicySection`, `ReviewIssue`; optional narrative/numeric/date predicates. The graph is flat and references node IDs. |
| Evidence | `ChartFact`, `EvidenceReference`, `Finding`. Facts contain spans; findings reference fact IDs with supporting, contradicting, or context relationships. |
| Execution | `RunRecord`, `AssessmentResult`, `ConfigurationProvenance`, `OperationalError`, `RunProgress`, `StageUsage`, and explicit lifecycle/outcome enums. |
| API | `CreateAssessmentRequest`, `AssessmentAccepted`, `DocumentResponse`, `PageResponse`, `ErrorResponse`, `LivenessResponse`, `ReadinessResponse`, `AssessmentExport`. |
| Provider candidates | `ScopeCandidate`, `PolicyCandidate`, `EvidenceCandidate` and their nested candidate types. They describe transport shape, not trusted domain artifacts. |

`ConfigurationProvenance` records `provider`, `model_id`, parser/prompt/schema versions, SDK version, inference settings, and parser configuration hash. OpenAI is the initial provider and has no AWS region. A future Bedrock configuration requires `region`. Secrets are not configuration fields. Provider verification records its provider, model, and check time; local readiness can be true while remote access remains unverified.

`DocumentResponse` wraps `document` and its `extractions`. The upload response can use an empty extraction collection: intake page inventory does not claim completed extraction. `PageResponse` identifies the document and extraction revision around an `ExtractedPage`. `AssessmentExport` wraps export time, the persisted run, and its policy/chart metadata. For `needs_input`, `run.result` is null and `run.applicability` explains the stop; unassessed criteria are not fabricated.

## Enforced invariants and remaining work

The baseline rejects incomplete page inventories, invalid identifiers, reversed spans, malformed policy references/cycles/unreachable nodes, unsupported positive findings without supporting evidence, unknown fact references, and contradictory lifecycle/outcome combinations. A satisfied result cannot coexist with a known governing blocker or unresolved policy section. A completed mismatch contains no necessity evaluation. Failed/interrupted runs require diagnostics and cannot contain a clinical result.

These checks do not execute the policy tree, resolve excerpts against source text, prove semantic support, detect omitted prose, authenticate parent-run relationships, or validate actual document bytes and hashes. Those responsibilities remain in WP-04 and WP-06–WP-10. A caller-supplied logical result is not proof of correct evaluation. Provider candidates intentionally allow some values that local domain validation rejects, and they must not be persisted as validated results. The initial flat candidate schemas still require verification against the selected OpenAI structured-output transport in WP-05; no provider compatibility claim is made by this schema-only change.

## Examples and verification

[Contract fixtures](../tests/fixtures/contracts/) include complete and clarification runs, a document/extraction response, and an intentionally invalid positive finding. They are artificial schema examples: their repeated-character hashes and measurement statements do not refer to real PDFs and are not clinical evaluation ground truth. Independent annotated scenario expectations live outside this directory.

[Contract tests](../tests/unit/test_schemas.py) exercise JSON roundtrips, strict types, evidence states, lifecycle contradictions, input isolation, graph structure, metadata clarification, provider configuration, and export eligibility. Run them with the repository's actual Python test command. Schema changes require a reviewed version change and coordinated consumer/fixture updates; parser and provider feasibility work may refine this initial baseline.

Baseline validation on October 18, 2026: all 45 contract tests passed with Python 3.13.15 and Pydantic 2.14.1. Ruff checks/format checks and strict mypy passed for the schema package and its test module. The exact test command was `uv run --project backend pytest -c backend/pyproject.toml tests/unit/test_schemas.py`. This verifies the local contract baseline, not parser, provider, or end-to-end workflow behavior.

## Reviewed integration amendments

On October 18, integration added `ScopeCandidate.field_sources`, grouping exact chart citations by request field. Its empty default preserves existing Python/JSON baseline examples; the strict provider schema requires the field, and conversion rejects unsupported non-null extracted metadata. The provider scope prompt is versioned `scope-v2`, with its exact output-schema hash retained by the experiment. This does not change the domain record version or rewrite reviewed patient expectations.

`StageUsage` now preserves unreported input/output tokens as null rather than implying a measured zero, and can retain the served model ID and response IDs. Existing records remain readable. A regression distinguishes unknown usage from an explicit zero. These additive integration amendments retain domain version `0.1.0`; incompatible contract changes require a new domain version and coordinated fixture migration.
