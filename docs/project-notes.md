# Aira project notes

Orientation notes compiled from the repository documentation, source, tests, and a full local check run on **October 19, 2026**.

Verification basis for these notes:

- Read the BRD, TRD, architecture, implementation plan, work breakdown, evaluation contract, feature index, design note, contracts, decisions, provider decision, handoff, and relevant result records.
- Read the application, schema, storage, provider, workflow, build, compiler, validation, evaluation, CLI, API, and frontend modules.
- Ran `make check` from the repository root: **exit 0** (544 unit/integration tests, strict mypy across 44 files, ruff lint/format, build artifacts, frontend lint/type/tests/build).
- Ran `make browser-test` from the repository root: **exit 0** (14 Playwright journey and shell tests).
- Live review of the supplied pair on October 19, 2026: `run-1aa53c7481b545159a65c6b022b4d7cd` completed with `applicability_mismatch`. The chart request is a single-chamber pacemaker (CPT 33207) and the guideline is the BCBS vein policy. No medical-necessity findings were produced. Policy build `build-b0164b6e96e3451e96621337d1cbc2f1` saved 60 requirements from 39 of 39 sections.

---

## 1. Product purpose

Aira is a narrow prior-authorization **evidence checklist** for clinic staff.

One assessment consumes:

1. one uploaded insurer guideline PDF,
2. one uploaded patient chart PDF, and
3. one selected procedure request (procedure/code, anatomy/laterality, payer, plan, service date, optional assessment cutoff).

It produces a cited readiness review: applicable policy requirements, chart evidence, missing documentation, contrary evidence, conflicts, unsupported interpretation, and operational failures. It never issues an insurer approval or denial and never generates treatment recommendations.

The supplied example is intentionally a **mismatch**: a UHC pacemaker chart against a BCBS Florida vein policy. The correct behavior is to stop at applicability with citations, not to produce a favorable necessity result.

## 2. Staff journey

1. Upload a guideline and chart. Each document can be prepared independently.
2. Inspect build progress, coverage, issues, and saved versions.
3. Select completed policy/chart builds (optional explicit pins).
4. Confirm or clarify the request; ambiguous procedures, plans, dates, or scope cause `needs_input`.
5. Review applicability. A confirmed mismatch ends the assessment before necessity work.
6. Review requirements grouped by the policy's AND/OR structure, with policy and chart citations.
7. Resolve conflicts or identify missing documentation. Clinical evidence cannot be overridden in the UI.
8. Export JSON or Markdown. Changed inputs create a new assessment; prior results remain unchanged.

## 3. Architectural rules

- **Independent extraction:** guideline preparation receives only the guideline; chart preparation receives only the chart. Neither receives the other document, the selected request, or staff annotations.
- **Reusable artifacts:** a new patient or changed request reuses the saved guideline build. A changed guideline reuses saved chart facts.
- **Applicability before necessity:** payer/plan, procedure scope, dates, and effective period are checked before findings are mapped.
- **Model interprets; code validates and decides.** Model output is always an untrusted candidate.
- **One local process:** FastAPI serves the API and built React UI; one bounded asyncio worker; SQLite metadata plus content-addressed files in a local data directory.
- **No hosted services required:** no queue, retrieval service, agent framework, cloud storage, EHR/FHIR connection, or payer submission.
- **Observability is not a separate module:** usage and failure facts live on `RunRecord.usage`, `StageUsage`, `BuildRecord.usage`, and typed errors.

## 4. Processing pipeline

### 4.1 Document preparation

**Guideline build (WP-19):**

1. Native extraction retains every page and block.
2. `plan_sections` groups all source blocks into bounded structural chunks. Blocks are atomic; no block is split to meet a budget. Context carries adjacent blocks, parent headings, and table headers.
3. Each section is interpreted with `policy_section`, validated against its supplied source context, and checkpointed immutably.
4. `policy_reconcile` resolves definitions, references, and cross-section relationships. Very large builds use bounded groups and then `policy_merge`; a final merge is also bounded.
5. Every section is audited with `policy_audit`; every primary block must receive exactly one disposition.
6. `compile_policy` builds the final `Policy` with named procedure/scope paths, source-checked nodes/criteria, issues, and coverage.
7. Publication requires extraction, completed sections, and audited coverage. A failed/partial build cannot look complete.

**Chart build:** a separate bounded whole-chart call produces `ChartData` with sourced facts and interpretation issues. It has no policy, request, or annotation input.

### 4.2 Assessment

1. `extracting`: parse/reuse both extractions; validate source identities.
2. `interpreting_policy` / `extracting_chart`: load or create the saved build artifacts.
3. `checking_applicability`: `scope` selects a request and a policy path; returns `applicable`, `mismatch`, or `unresolved`.
4. `mapping_evidence`: map saved facts to the selected criteria. Findings may reference only existing fact IDs; facts cannot be added, dropped, or rewritten.
5. `validating`: revalidate citations, references, predicates, dates, units, anatomy, and time context.
6. `evaluating`: three-valued aggregation plus independent readiness blockers.

A mismatch returns a `completed` run with `applicability_mismatch` and no necessity evaluation. Unresolved scope returns `needs_input`. Processing failures return `failed`/`interrupted` with operational diagnostics.

## 5. Domain semantics

### 5.1 Finding states

| Status | Logical value | Meaning |
| --- | --- | --- |
| `met` | true | Cited evidence supports the full requirement in context. |
| `not_met` | false | Cited evidence establishes contrary evidence. |
| `missing` | unknown | Relevant documentation was not found in successfully processed input. |
| `conflicting` | unknown | Incompatible evidence remains unresolved. |
| `needs_review` | unknown | Interpretation or supported computation cannot determine the requirement. |

Absence is never treated as a negative finding. Negation is interpreted relative to the requirement.

### 5.2 Aggregation

Kleene-style three-valued logic in `backend/app/assessment/rules.py`:

- `all`: false if any child is false; true only if every child is true; otherwise unknown.
- `any`: true if any child is true; false only if every child is false; otherwise unknown.

Every child trace is preserved, including unused OR alternatives. A satisfied OR group exposes its supporting path.

### 5.3 Blockers and outcomes

Known blockers independently prevent `documented_requirements_satisfied`:

- unresolved applicability,
- blocking review issues,
- unresolved policy sections,
- unsupported/unverified predicates,
- build omissions/reconciliation/audit issues.

Outcomes: `applicability_mismatch`, `documented_requirements_satisfied`, `documentation_gaps_or_contrary_evidence`, `review_required`. Status and outcome are separate: `completed` only means a valid outcome was reached.

### 5.4 Dates and predicates

- Revision date, effective date, service date, observation date, documentation date, and signature date are distinct.
- Never infer an effective date from a revision date, or a service date from today/submission date.
- Numeric predicates support exact units only; no implicit conversion. Ambiguous units stay unresolved.
- Date predicates require an explicit ISO boundary and label/role.
- Unsupported semantics become blocking review issues.

### 5.5 Policy representation

- Flat `all` / `any` / `criterion` nodes referencing IDs; one root per evaluated path.
- `Policy.paths` identifies named procedure/plan scope; `select_policy_path` projects one path before evidence mapping.
- Local validation rejects duplicate IDs, unknown references, cycles, unreachable nodes, empty groups, and contradictions.
- Unsourced or invented rules are rejected; a source citation is necessary but is **not** proof of semantic support.

## 6. Module map

| Concern | Location |
| --- | --- |
| FastAPI wiring, lifespan, readiness, static UI | `backend/app/main.py` |
| HTTP routes and error envelopes | `backend/app/api/routes.py` |
| Versioned public schemas | `backend/app/schemas/` |
| Native PDF intake/extraction | `backend/app/documents/native.py` |
| Candidate → domain conversion | `backend/app/policies/conversion.py` |
| Section planning, reconciliation, compilation | `backend/app/policies/compiler.py` |
| Compatibility page helpers | `backend/app/policies/pages.py` |
| Citation resolution, predicates, finding validation | `backend/app/evidence/validation.py` |
| Bounded synonym helpers | `backend/app/evidence/synonyms.py` |
| Stage contracts and rendered inputs | `backend/app/assessment/stages.py` |
| Assessment engine | `backend/app/assessment/workflow.py` |
| Standalone document builds | `backend/app/assessment/builds.py` |
| Three-valued evaluation | `backend/app/assessment/rules.py` |
| Markdown export | `backend/app/assessment/export.py` |
| Build limit configuration | `backend/app/assessment/build_config.py` |
| Provider settings | `backend/app/llm/config.py` |
| OpenAI transport adapter | `backend/app/llm/openai_adapter.py` |
| Production stage interpreter | `backend/app/llm/interpreter.py` |
| Versioned prompts | `backend/app/llm/prompts.py` |
| Preflight and experiment CLIs | `backend/app/llm/preflight.py`, `experiment.py` |
| SQLite + content-addressed storage | `backend/app/storage/local.py`, `identity.py` |
| CLI | `backend/app/cli.py` |
| React workspace | `frontend/src/` |
| Saved Playwright journeys | `frontend/e2e/` |
| Test-only fixture server | `tests/e2e/fixture_server.py` |
| One-line launch | `scripts/launch.sh` |

## 7. Storage and identity

- Original upload bytes are preserved and hashed (SHA-256).
- Extraction revisions, run snapshots, build manifests, checkpoints, policy rule sets, and chart interpretations are versioned and immutable.
- Files publish before SQLite metadata; reads verify hashes.
- Cache identity includes source bytes, parser configuration, relevant prompt/schema versions, provider/endpoint/transport/model, inference settings, and upstream artifact identities.
- Policy keys exclude chart/request/annotation/assessment settings; chart keys exclude policy/request/annotation/assessment settings.
- Assessment identity additionally includes the selected request and annotations.
- Only completed validated artifacts are reusable. Rejected/corrupt builds fail closed.
- Same-upload builds coalesce into one active job; duplicate bytes may share blobs while retaining role-scoped document IDs.
- Restart marks unfinished work `interrupted`; it never claims resumption.
- Retry creates a linked attempt and may reuse compatible checkpoints. Rebuild creates a new generation.
- Human approval changes review state only; it does not clear interpretation blockers or imply semantic correctness.

## 8. HTTP surface

From `backend/app/api/routes.py` and the TRD:

| Method/path | Purpose |
| --- | --- |
| `POST /api/documents` | Multipart upload with `role=policy|chart`. |
| `GET /api/documents/{id}` | Metadata and extraction revisions. |
| `GET /api/documents/{id}/file` | Original PDF bytes. |
| `GET /api/documents/{id}/pages/{page}?extraction_id=...` | One extracted page. |
| `POST /api/assessments` | Queue an assessment; 202 + run ID + `Location`. |
| `GET /api/assessments/{id}` | Persisted status/result. |
| `GET /api/assessments/{id}/export?format=json|markdown` | Saved export; 409 if ineligible. |
| `GET /api/policy-rule-sets` | Legacy rule-set registry compatibility. |
| `POST /api/policy-rule-sets/{id}/approve` | Legacy approval compatibility. |
| `POST /api/documents/{id}/builds` | Start standalone preparation. |
| `GET /api/documents/{id}/builds` | Saved build versions. |
| `GET /api/builds/{id}` | Persisted build manifest/result/coverage/usage. |
| `GET /api/builds/{id}/steps/{key}` | Intermediate checkpoint output + receipt. |
| `POST /api/builds/{id}/{retry|rebuild|approve|reject}` | Linked retry/rebuild or review action. |
| `GET /health`, `GET /health/live` | Liveness; no provider call. |
| `GET /health/ready` | Local prerequisites/config only; 503 when not ready. |

Error contract: `error.code`, `message`, `retryable`, optional `stage`/`page`/`document_id`, and corrective `action`, plus a request ID. Typical statuses: 400 malformed syntax, 415 unsupported file type, 422 contract failure, 413 limit exceeded, 404 unknown resource, 409 state conflict, 429 queue full, 503 missing configuration/processing unavailable.

Readiness reports the persisted explicit preflight state but never performs inference. `/health` is a newly added alias for liveness in the working tree.

## 9. Provider and configuration

- Required backend-only `OPENAI_API_KEY` and explicit `AIRA_MODEL`; the key never reaches the browser, prompts, exports, or logs.
- Direct OpenAI default: `https://api.openai.com/v1` with Responses API.
- A base URL or transport present **only in the process environment is ignored** unless `AIRA_LLM_BACKEND=litellm`.
- An `OPENAI_BASE_URL` written in `.env` selects any OpenAI-compatible `/v1` endpoint for every call. Default transport there is chat completions; `AIRA_LLM_TRANSPORT=responses` opts into Responses.
- One retry owner: SDK retries disabled; adapter owns bounded attempts. Stage deadlines bound the loop.
- Strict JSON-schema structured output; `store=false`; truncation disabled.
- Invalid structured output or citation-invalid output may receive **one** application repair attempt with unchanged source input.
- Prompt identity is version + instruction/schema digest. Policy reuse keys include only policy prompts; chart reuse keys include only the chart prompt.
- `python -m app.llm.preflight` is an explicit billable/verification action; readiness is not proof of remote access.

## 10. Guardrails and supported input

| Limit | Default |
| --- | --- |
| Upload | 10 MiB |
| Pages | 250 |
| Extracted characters/page | 50,000 |
| Total extracted characters | 2,000,000 |
| Section primary budget | 7,000 UTF-8 bytes (conservative token upper bound) |
| Complete section request/output reservation | 60,000 |
| Adapter output | 4,096 tokens (`AIRA_MAX_OUTPUT_TOKENS`) |
| Build sections | 600 |
| Build worst-case calls | 3,000 |
| Build reserved tokens | 100,000,000 |
| Build duration | 3,600 seconds |
| Pending builds | 4 |
| Assessment rendered input | 200,000 characters |
| Uncached operation reservation | Up to 6 transport/repair attempts |

Native-text boundary: image-only pages, embedded raster images (even decorative), rotation, interactive forms, and vector-only non-text pages are rejected. OCR is **opt-in only** and requires Tesseract. No page may disappear from a completed assessment.

## 11. Frontend behavior

- React SPA with URL state: `/?run=...` and `/?build=...` survive reload.
- Uploads are role-specific; preparation can run for policy or chart alone.
- Build view shows real status/phase, section counts, model/source SHA, saved versions, coverage, issues, intermediate checkpoint links, coverage/source inspection, approve/reject, retry, and rebuild.
- Run view polls persisted state and renders decided results only. The UI never evaluates rules.
- Findings show policy and chart citations; missing findings show "Documentation needed" without invented chart citations.
- Source viewer highlights exact block offsets and links the original PDF at the cited page.
- JSON/Markdown exports reflect the saved run, not a rerun.
- Failure cards show the code, stage, document, failed pages, and next action.
- The browser test server uses `tests/e2e/fixture_server.py`, a clearly labeled controlled interpreter over real citations. It must never be wired into `backend/app`.

## 12. Repository inputs and fixtures

- `examples/guidelines/`: two BCBS Florida snapshots (2025-08-15 and 2026-01-01).
- `examples/charts/`: supplied fictional Robert Mitchell chart.
- `examples/synthetic/`: rendered synthetic PDFs for venous and monitoring scenarios.
- `evals/`: hash-pinned development corpus, held-out pair, expected outcomes, policy annotations, source registry, scenario coverage, construction-task ledger.
- `tests/fixtures/pdf/`: native layout, blank, image-only, mixed, encrypted, annotation, vector-only, navigation-link cases.
- `tests/fixtures/long-documents/`: 100- and 200-page native-text fictional guidelines with independently authored gold manifests.
- `tests/support.py`: controlled interpreter helpers.
- `tests/long_support.py`: long-document scripts.
- `tests/e2e/fixture_server.py`: browser-journey interpreter.

The eval corpus is an engineering reference set, not a clinical benchmark. Expectations were authored from sources and reviewed separately; they must not be changed to match model output.

## 13. Verification and observed results

### Local commands

```sh
make install          # uv sync --locked + npm ci
make check            # ruff, format, mypy, pytest, wheel/sdist, frontend lint/type/Vitest/build
make browser-test     # build UI + Playwright shell and journey projects
make dev-api          # uvicorn on 127.0.0.1:8000
make dev-ui           # Vite dev server
./scripts/launch.sh   # one-line reviewer launch on port 8000
```

### `make check` on October 19, 2026 (this working tree)

- Ruff lint: passed.
- Ruff format check: 91 files already formatted.
- mypy: no issues in 44 source files.
- pytest: **494 passed** in 143.56s.
- Wheel and sdist built successfully.
- ESLint: passed.
- TypeScript: passed.
- Vitest: **26 passed** across 7 files.
- Production Vite build: succeeded.

### Historical counts and drift

- `docs/results/wp19-implementation.md` records 492 pytest and 26 Vitest.
- `docs/results/independent-extraction.md` records 490 pytest and 25 Vitest.
- The current tree actually has 494 pytest and 26 Vitest.
- Treat these records as revision-specific; the current observed count is above. Do not silently rewrite historical records unless the owning note is being updated with a clear date.

### Not run in this pass

- `make browser-test` (Playwright). Historical record: 14 passed.
- Any live model call, preflight, or paid probe.

## 14. Current implementation status

| Work package | Status |
| --- | --- |
| WP-01 Foundation | Complete |
| WP-02 Contracts | Complete |
| WP-03 Fixtures | Complete; held-out semantic curation still open |
| WP-04 Native PDF extraction | Complete |
| WP-05 Model feasibility | Blocked by deferred quota; adapter/CLI/controlled tests exist |
| WP-06 Storage | Complete |
| WP-07–WP-09 Domain stages | In progress; controlled conversion/interpreter evidence, live semantic checks open |
| WP-10 Rules/provenance | Complete |
| WP-11 Workflow | In progress; live run open |
| WP-12 HTTP API | Complete |
| WP-13 Review UI | Complete |
| WP-14 Exports | Complete |
| WP-15 Input limits | In progress; parser boundary verified, model token envelope open |
| WP-16 Integrated evaluation | In progress; live semantic report open |
| WP-17 Reviewer setup | In progress; clean-checkout live workflow open |
| WP-18 Release handoff | In progress; design-note draft exists |
| WP-19 Long-document compilation | In progress; runtime/controlled checks delivered, LD-09/LD-10 live acceptance open |

Open release gates: live semantic accuracy, model selection, measured parser+model envelope, A19 clean-checkout live run, A21 rule/edge/exception fidelity and repeatability, held-out pair curation.

## 15. Current working tree (uncommitted)

`git status --short` shows a broad in-progress update:

### Staged

- `.github/workflows/ci.yml` deleted. Documentation and `AGENTS.md` now say verification is local and there is no hosted CI. README previously linked GitHub Actions.

### Modified application code

- `backend/app/llm/config.py`: endpoint selection reworked. Env-file `OPENAI_BASE_URL` now selects a compatible endpoint for any backend; shell-only values are ignored unless `AIRA_LLM_BACKEND=litellm`; custom endpoints imply `litellm` backend and chat-completions transport unless explicitly overridden; blank shell values no longer override the env file.
- `backend/app/main.py`: added `GET /health` as an alias of `/health/live`.
- `backend/app/policies/__init__.py`, `conversion.py`: removed the unused `convert_evidence` helper. Production now uses `convert_chart` then `convert_findings`, preserving saved-fact mapping. Unreadable model dates are handled as staff-confirmation issues:
  - criterion `date_boundary`: predicate dropped, wording/sources kept, blocking `DATE_CONFIRMATION`.
  - policy revision/effective dates: field left `None`, one blocking `conversion-policy-date` issue.
  - chart event/documentation date: field left `None`, fact kept, non-blocking note in `ChartData.interpretation_issues`.
  - literal `YYYY-MM-DD` unchanged; an invalid real date such as `20260230` still fails conversion.
  - logical groups may carry a stray `criterion_id`: children win. A group with no children and no criterion fails. A group node with only `criterion_id` becomes a criterion leaf.
- `backend/app/policies/compiler.py`: an empty fragment (no criteria) is treated as a shell, not a failed extraction; a requirements disposition without a cited rule becomes a blocking review issue instead of failing the section.
- `backend/app/storage/local.py`: run update conflict detection now compares the validated snapshot (`expected != current`) instead of re-hashing the loaded record. This allows older snapshots missing later optional fields to be updated/interrupted without a false conflict.

### Modified tests / frontend

- `tests/unit/test_candidate_conversion.py`: switched to `convert_chart` + `convert_findings`; added unreadable policy/chart date tests; stray group `criterion_id` test; removed `bad_date` from hard-failure cases.
- `tests/unit/test_policy_compiler.py`: shell/empty-fragment coverage.
- `tests/integration/test_storage.py`: legacy snapshot update/interruption regression.
- `tests/integration/test_openai_adapter.py`: env-file compatible-endpoint selection and transport tests.
- `tests/integration/test_health.py`: `/health` alias assertion.
- `frontend/src/App.test.tsx`, `frontend/src/components/Readiness.tsx`: label a non-openai backend as "OpenAI-compatible API", not "LiteLLM" or "Direct OpenAI".

### Modified documentation

Broad synchronization across README, AGENTS, and docs: architecture, requirements, evaluation, implementation plan, work breakdown, provider decision, decisions, handoff, feature 09/17/19, plans, research logs, and result records. Includes the CI removal, current WP-19/independent-extraction evidence, endpoint-selection wording, and date-confirmation behavior.

### Untracked

- `docs/results/candidate-conversion.md`: detailed record of conversion entry points, unreadable-date policy, provenance checks, and the observed 53-test verification.

Nothing in this working tree should be assumed committed or final until reviewed and checked again.

## 16. Important invariants to preserve

- Do not hard-code the supplied patient, procedure, payer, or coverage rules. New uploads must drive results.
- Do not let processing failures become clinical `missing` findings.
- Do not treat schema-valid JSON or an existing quote as semantic support.
- Do not fuzzy-match fabricated quotes. Resolve exact spans; ambiguity is a failure.
- Do not let evidence for another side, procedure, or time period silently satisfy a requirement.
- Do not ask staff to satisfy every unused OR alternative.
- Do not let a satisfied subset override a known unresolved governing condition.
- Do not publish a partial rule set as complete.
- Do not reuse rejected/corrupt artifacts or rewrite earlier results.
- Do not change reviewed evaluation expectations to match generated output.
- Do not wire the fixture interpreter into `backend/app`.
- Do not commit `.env`, runtime data, private vault material, or credentials.

## 17. Known failure modes / what breaks first

**Guideline changes**
1. Paraphrased or line-spanning quotes fail as `citation_invalid`.
2. Long policies may exceed the output budget (`invalid_output`); raise `AIRA_MAX_OUTPUT_TOKENS`.
3. Unsupported semantics produce `review_required`.
4. Omitted governing conditions can only be caught by annotated evaluation.
5. Layout changes/scans reject the document.
6. Version/applicability ambiguity produces `needs_input`.

**Messy charts**
1. Scans, faxes, and images are rejected.
2. Non-ISO dates leave date predicates at `needs_review`; unreadable dates now request confirmation.
3. Repeated short phrases can be ambiguous citations; longer quotes are needed.
4. Charts beyond the 200,000-character rendered guardrail fail explicitly.
5. Contradictions, wrong side, and post-cutoff evidence become `conflicting`/`needs_review`, not `met`.

## 18. Where to read what

| Question | Document |
| --- | --- |
| Business outcomes and BR IDs | `docs/requirements/business-requirements.md` |
| Testable behavior, API/error contracts, limits | `docs/requirements/technical-requirements.md` |
| Current design and implementation snapshot | `docs/architecture.md` |
| Package status/dependencies/completion evidence | `docs/work-breakdown.md` |
| Milestones and rationale | `docs/implementation-plan.md` |
| Acceptance cases A01–A21 | `docs/evaluation.md` |
| Schema/contract amendments | `docs/contracts.md` |
| Decisions AD/TD | `docs/decisions.md` |
| Provider boundary | `docs/model-provider.md` |
| Submission argument | `docs/design-note.md` |
| Continuation instructions | `docs/agent-handoff.md` |
| Per-package tasks | `docs/features/` |
| WP-19 design/algorithm | `docs/plans/long-document-rule-compilation.md` |
| Evidence records | `docs/results/` |

## 19. Practical continuation notes

- Before changing behavior, read the owning BR/TR and the relevant feature file.
- For document/build/assessment changes, run the focused tests first, then `make check` and `make browser-test`.
- Keep live evidence separate from controlled/fixture evidence.
- Update the work breakdown only with actual command results and observed output.
- Preserve the existing uncommitted changes unless they are clearly superseded; they look like a coherent robustness/doc-sync pass.
- The main open work is not more shell tests: it is restoring quota, running live semantic evaluation (LD-09/WP-16), verifying A19 on a clean checkout, and finishing the held-out long-document annotations.
