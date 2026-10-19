# WP-06 local storage verification

Verified October 18, 2026 against the working-tree storage package. [WP-06](../work-breakdown.md#wp-06-storage-and-identity) owns implementation status and the integrating commit. This record covers storage behavior; it does not establish PDF extraction quality, model accuracy, or the completed assessment workflow.

## Implemented boundary

[`backend/app/storage/`](../../backend/app/storage/) uses standard-library SQLite and content-addressed local files. Documents retain separate role-scoped IDs and metadata even when their original bytes share one blob. Extraction revisions, run snapshots, and artifact payloads are immutable objects. SQLite relationships and local checks bind records to their document identities.

Files are written to a temporary path, flushed, and atomically published without replacing an existing object. Metadata is committed afterward. An interruption may leave an unreferenced complete object, but it cannot create a reusable artifact record before its files exist. Reads verify content hashes. Missing or corrupt cache objects never return a cache hit. There is no background garbage collector.

Run updates use an expected previous snapshot as an optimistic concurrency check. The check compares the validated record, so an older snapshot that omits optional fields added later still matches the snapshot that was read. Each successful change adds a revision; stopped runs are immutable. Retry and clarification create new queued runs with `parent_run_id`. `interrupt_unfinished()` explicitly marks queued/running work interrupted at application startup; constructing a second store does not change execution state.

## Integration API

Import the following from `app.storage`:

| Operation | Interface and caller responsibility |
| --- | --- |
| Initialize | `LocalStore(Path(data_directory))`. Operations are synchronous; the workflow/API must use an appropriate local worker/thread boundary. |
| Original inputs | `put_document(record, content)`, `get_document(id, expected_role=...)`, `read_document(id)`. Intake must validate actual PDF format and its supported limits before persistence. |
| Extractions | `put_extraction(record)`, `get_extraction(id, document_id=...)`, `list_extractions(document_id)`. Reprocessing uses a new extraction ID. |
| Assessment identity | `assessment_fingerprint(policy, chart, configuration, request_context, annotations)` supplies a new queued `RunRecord.input_fingerprint`. |
| Run history | `create_run(record)`, `get_run(id)`, `update_run(record, expected=previous)`, `run_history(id)`. Input IDs/hashes, configuration, annotations, parent, and original fingerprint remain fixed. An active run may acquire extracted request context. |
| Recovery | `interrupt_unfinished(at=...)` returns changed records and retains their last phase and previous snapshots. |
| Stage artifacts | `put_validated_artifact(run_id, phase, value, extraction_ids=..., upstream_artifact_ids=..., validation_version=...)` returns a typed `StoredArtifact`. The run must be executing that phase. |
| Read/reuse | `get_artifact(id, output_type)` and `find_artifact(run_id, phase, output_type, extraction_ids=..., upstream_artifact_ids=..., validation_version=...)`. Cache lookup returns the saved origin run and value, or `None`. |

Storage revalidates typed payloads and checks source document/extraction/page relationships. The caller must complete domain and semantic validation before publishing a validated artifact. Exact excerpt/block validation, graph evaluation, clinical support, and stage order remain WP-10/WP-11 responsibilities. Operational filesystem/SQLite errors must be handled as processing failures by the workflow.

Run-scoped stage artifacts stay conservative: their identity includes the submitted input fingerprint, provider/model/SDK, parser and prompt versions, schema, inference settings, request context, annotations, extraction revisions, upstream payload identities, output schema, and validator version. Policy rule sets and chart-fact artifacts use a separate identity: document bytes, parser output, and that extraction's own prompt, provider, transport, model, and inference settings. An identical re-upload under a new document ID reuses the validated artifact and rebinds citations to the new document and extraction IDs. Failed, incomplete, rejected, and corrupt rows are not returned as reusable successes. A valid completed stage may be reused after its originating run later fails or is interrupted; incomplete stage work has no cache publication path. Draft technical reuse does not imply human approval.

## Observed verification

Commands run from the repository root:

| Command | Result |
| --- | --- |
| `uv run --project backend --locked pytest -c backend/pyproject.toml tests/integration/test_storage.py -q` | 30 passed in 0.49 seconds. |
| `uv run --project backend --locked ruff check --config backend/pyproject.toml backend/app/storage tests/integration/test_storage.py` | Passed. |
| `uv run --project backend --locked ruff format --config backend/pyproject.toml --check backend/app/storage tests/integration/test_storage.py` | Four files already formatted. |
| `uv run --project backend --locked mypy --config-file backend/pyproject.toml backend/app/storage` | Passed for three source modules. |

[`test_storage.py`](../../tests/integration/test_storage.py) exercises real SQLite transactions and temporary files. Cases cover A09/A15/A17 storage behavior: original and extraction retention, wrong roles/references, changed policy, configuration/request/annotation/validator/schema invalidation, duplicate-byte citation isolation, immutable parent lineage, explicit restart recovery, actual saved output, concurrent stale writers, damaged cache files, and injected failures before file publication and after file publication but before metadata completion.

No dependencies, shared schemas, live provider calls, deployment, or shared completion-status changes were required. Full merged application verification and workflow integration remain separate evidence.
