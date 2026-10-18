# WP-12 HTTP/source API and WP-14 export route verification

Verified October 18, 2026 against the working-tree application. [WP-12](../work-breakdown.md#wp-12-http-and-source-api) owns the API boundary and [WP-14](../work-breakdown.md#wp-14-exports) owns export behavior. Every check runs the real lifespan, `LocalStore`, and `WorkflowEngine` behind `httpx.TestClient` with the controlled interpreter injected — controlled orchestration evidence, never a provider call or a claim about live semantic quality.

## Routes and status codes

[`backend/app/api/routes.py`](../../backend/app/api/routes.py) implements the [TRD endpoint table](../requirements/technical-requirements.md#http-interface-contracts):

| Route | Behavior and statuses |
| --- | --- |
| `POST /api/documents` | Multipart `file` + `role`. 201 `DocumentResponse` + `Location` on success; 422 bad role/missing file/malformed PDF; 413 configured size limit; 415 non-PDF bytes. Reads at most `max_bytes + 1` and runs `inspect_pdf` in a threadpool. |
| `GET /api/documents/{id}` | 200 `DocumentResponse` with stored extraction revisions; 404 unknown. |
| `GET /api/documents/{id}/file` | 200 `application/pdf` original bytes, `inline` sanitized filename; 404 unknown. |
| `GET /api/documents/{id}/pages/{page}?extraction_id=` | 200 `PageResponse` from the named revision; 422 missing `extraction_id`; 404 unknown document/extraction, an extraction from another document, or an out-of-inventory page. |
| `POST /api/assessments` | `CreateAssessmentRequest` JSON. 202 `AssessmentAccepted` + `Location`; 400 malformed JSON syntax; 422 contract violations, wrong roles, or bad context; 404 unknown parent/documents; 503 unconfigured engine; 429 `queue_full`. |
| `GET /api/assessments/{id}` | 200 persisted `RunRecord` for every status; 404 unknown. |
| `GET /api/assessments/{id}/export?format=` | `json` (default) or `markdown`; other formats 422. 409 `state_conflict` unless `completed`/`needs_input`; 404 unknown. JSON is the `AssessmentExport` contract with an attachment filename; Markdown is `render_markdown` output. No model call. |

Errors use the versioned `ErrorResponse` envelope (`request_id`, `OperationalError`, optional `run_id`) over the new `not_found`/`invalid_request`/`state_conflict` codes added as an additive contract amendment. Every `/api` response carries `X-Request-ID: req-<hex>`. Strict contract models are parsed with `model_validate_json(await request.body())`: malformed JSON syntax returns 400 `invalid_request`, contract violations return 422 `invalid_request` naming the field locations (matching the TRD's 400-vs-422 rule), and unexpected server failures return a safe 500 `internal_error` with no exception text — server defects are never presented as client errors.

## Startup and readiness

`create_app` accepts test seams (`interpreter`, `configuration`, `data_dir`, `env_file`, `parser_config`, `limits`). The lifespan opens `LocalStore(data_dir)` — the `AIRA_DATA_DIR` env var or `data/app` — and, absent an injected interpreter, resolves `OpenAISettings` and builds the real adapter/interpreter/configuration. Missing credentials or an unwritable data directory land in `missing_prerequisites` and readiness returns `ReadinessResponse(ready=false, provider=unverified)` with 503; nothing calls the model at startup or in health checks, and readiness never claims verified provider access. `engine.start()` marks unfinished stored runs interrupted on boot; a set `engine.fatal_error` also makes readiness not-ready.

## Observed verification

Commands run from the repository root:

| Command | Result |
| --- | --- |
| `uv run --project backend --locked pytest -c backend/pyproject.toml tests/integration/test_api.py tests/integration/test_health.py tests/integration/test_workflow.py -q` | 32 passed in about 11 seconds. |
| `make check` | Ruff lint/format, strict mypy, all pytest checks, backend build, and frontend lint/typecheck/Vitest/build pass. |
| `make browser-test` | 2 Playwright checks pass: the built UI shows the readiness state the API reports, and a severed connection stays visible. |

[`test_api.py`](../../tests/integration/test_api.py) covers the matrix at API level: A14 intake rejects a non-PDF (415), a truncated PDF (422), an encrypted PDF (422), an oversized file (413 naming the limit), a bad role (422), and a missing file (422); A12/A15 cover role-swapped submissions (422), unknown documents/parent runs (404), unknown/other-document extractions and out-of-inventory pages (404), and the missing `extraction_id` (422); A16 covers `queue_full` (429), `configuration_missing` (503 with the named prerequisites), and a known failed run polling `failed` with its error while exports conflict (409); A19 covers page/file source inspection, repeated readiness without outbound HTTP (a patched `httpx.AsyncClient.send` fails the test on any attempt), and the built UI surviving missing configuration; A09/A17 cover export byte-stability across a later run on the January 2026 policy snapshot and a linked child run exporting `parent_run_id` and the staff annotation while the parent's export stays unchanged. Restart evidence: an in-flight run is `interrupted` with its last phase after a new app opens the same store. A secrets check confirms no response exposes the fake API key. Error-taxonomy checks cover malformed JSON (400), schema violations (422), and a simulated internal store failure (500 `internal_error` with `X-Request-ID` and no exception text).

## Limitations

- Controlled interpreter: outcomes are scripted; live provider behavior remains unverified behind the deferred quota.
- The staff review UI (WP-13) has not yet consumed these routes; UI download parity is a WP-16 check.
- `TestClient` exercises the same lifespan/worker path as uvicorn but not container networking or process signals.
