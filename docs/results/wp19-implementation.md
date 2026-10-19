# WP-19 implementation and verification

Recorded October 19, 2026 against the working tree based on `6351ac7`. This record covers the independent-extraction and long-document runtime changes; it does not declare a live release or a new implementing commit. [BR-013/TR-019](../requirements/README.md), the [feature/tasks](../features/19-long-document-rule-compilation.md), and the [execution plan](../plans/long-document-rule-compilation.md) remain the acceptance baseline.

## Delivered behavior

Guidelines and charts are independent, persisted document builds. Guideline preparation needs no chart, request metadata, or annotations. Chart extraction needs no guideline. Assessment consumes saved rules/facts, selects a named procedure path, maps evidence only to existing facts, and runs deterministic validation/evaluation. New patients and changed requests reuse the guideline; a changed guideline reuses chart facts.

The production guideline path inventories all native source blocks, plans bounded chunks with neighboring/heading/table context, extracts source-validated immutable local records, reconciles compact records, audits every primary block, and compiles the graph. Oversized reconciliation uses bounded groups followed by a bounded merge of scoped roots. Earlier criteria/internal edges cannot be regenerated or overwritten by that merge. Oversized atomic blocks, exhausted budgets, or failed required work fail explicitly without truncation or a partial final rule set.

Definitions and references retain source citations and explicit resolutions. Missing references, cycles, incompatible metadata, unresolved dispositions, omission findings, and unsupported semantics remain blockers. Exception resolution alone never proves executable exception support: those relationships require review. Mechanical source coverage and valid JSON are not semantic-completeness certificates. Human approval changes review state without removing blockers.

Builds persist original/extraction identities, exact sources, coverage, dependency resolutions, generation settings, limits, usage, errors, and immutable checkpoint receipts. Compatible completed work survives restart; unfinished jobs become interrupted. Same-upload requests coalesce; duplicate bytes receive a new citation binding only after exact extraction text/layout checks. Retry creates a linked attempt and may reuse checkpoints. Rebuild creates a fresh generation; retry of a failed rebuild stays in that generation and cannot select an older success. Corrupt/rejected manifests and rejected reuse ancestors fail closed. Earlier artifacts and assessments remain unchanged.

The UI supports policy-only/chart-only preparation, real progress, intermediate JSON, coverage/source inspection, issues, saved-version selection, approval/rejection, and linked retry/rebuild. Saved build URLs survive reload. Assessments use exact pinned extraction revisions, and matching parent pins carry into clarification. JSON/Markdown exports retain build/path IDs and actual generation configurations. The older policy/chart registries remain compatibility interfaces; new runtime selection uses build manifests.

## Implementation map

| Boundary | Files |
| --- | --- |
| Strict build/section/audit/path contracts | `backend/app/schemas/builds.py`, `policies.py`, `provider.py`, `runs.py`, `api.py` |
| Pure planner, local validation, reconciliation packets, compiler/path projection | `backend/app/policies/compiler.py` |
| Configured model operations and bounded repair | `backend/app/llm/prompts.py`, `interpreter.py`, existing `openai_adapter.py` |
| Durable execution and build guardrails | `backend/app/assessment/builds.py`, `build_config.py` |
| Immutable objects, snapshots, generation provenance, selection integrity | `backend/app/storage/local.py`, `identity.py` |
| Independent assessment and exact pins/exports | `backend/app/assessment/workflow.py`, `stages.py`, `export.py` |
| Build/step APIs and CLI | `backend/app/api/routes.py`, `main.py`, `cli.py` |
| Preparation, selection and review UI | `frontend/src/components/DocumentBuild.tsx`, `Upload.tsx`, `RunView.tsx`, `App.tsx` |

The production interpreter implements the structural interface. Explicit injected legacy test interpreters retain a labeled compatibility seam; its synthetic coverage is fixture support, not semantic evidence. Test interpreters remain under `tests/` and are never imported as production fallbacks. Old page helpers remain compatibility/experiment code; `_policy_by_page` is removed from the workflow.

## Configuration and supported envelope

Direct OpenAI reads backend-only `OPENAI_API_KEY` and explicit `AIRA_MODEL`. With no env-file `OPENAI_BASE_URL`, loading pins `https://api.openai.com/v1` and Responses transport and ignores a shell-only gateway URL. An env-file `OPENAI_BASE_URL` selects that OpenAI-compatible endpoint; its default transport is `chat_completions`. `AIRA_LLM_BACKEND=litellm` reads the URL from the process environment when the file does not set one. Section extraction, reconciliation/merge, audit, chart, scope, evidence, repair, and explicit preflight share the selected adapter. Readiness displays active connection/model and makes no inference calls. Preflight records bind model, backend, transport and endpoint hash; old/different connection verification is unverified for the current configuration. Credentials never enter browser configuration, prompts, exports, or saved provenance.

`./scripts/launch.sh` / `make run` preserves the local reviewer workflow. Standalone CLI: `uv run --project backend python -m app.cli prepare --role policy --document path/to/guideline.pdf --data-dir data/cli`; use `--role chart` for facts. Preparation/assessment/preflight are explicit billable operations.

| Guardrail | Default |
| --- | --- |
| PDF intake | 10 MiB; 250 pages; 50,000 extracted characters/page; 2,000,000 total |
| Scan behavior | Explicit rejection by default; opt-in OCR with a bounded Tesseract subprocess |
| Primary section budget | 7,000 UTF-8 bytes as a conservative token upper bound |
| Complete call/output reservation | 60,000, including schema, instruction/envelope reserve and output |
| Adapter output | 4,096 tokens; `AIRA_MAX_OUTPUT_TOKENS` configurable |
| Whole build | 600 sections; 3,000 worst-case calls; 100,000,000 reserved tokens; 3,600 seconds |
| Local execution | One build worker; four pending builds; dedicated bounded parser executor |

An uncached operation reserves up to six transport/repair attempts. Actual provider usage and identifiers are retained when supplied. Backend `AIRA_BUILD_*` configuration adjusts build limits; manifests retain the actual values. The byte upper bound is conservative budgeting, not measured model token usage. The final scope merge is also bounded; arbitrary dense documents can exceed it and fail explicitly. Charts currently use a bounded whole-chart call. No model/context/quality capacity is inferred from parser limits.

## Controlled corpus and checks

[Fixture construction and provenance](../../tests/fixtures/long-documents/README.md), [hash manifest](../../tests/fixtures/long-documents/manifest.json), and independent `gold-100.json` / `gold-200.json` pin fictional sources. Each page has a mandatory condition, with separate Alpha/Beta paths, distant D1/E1 references, continuation, and an injected instruction. These are not blank padding or generated clinical expectations. `pdf-create` rendered the native-text PDFs; `pdf-inspect` confirmed exact page counts, and the final 200-page page was rendered and visually inspected.

| PDF | Planned sections | Primary/audited blocks | Gold/extracted conditions | Procedure paths | Controlled operations |
| --- | --- | --- | --- | --- | --- |
| 100 pages | 34 | 508 | 100/100 | 2 | 69: sections, reconciliation, audits |
| 200 pages | 68 | 1,008 | 200/200 | 2 | 141: sections, four reconciliation groups, one merge, audits |

The 100-page build uses the 60,000 reservation; the 200-page test explicitly lowers it to 40,000 to force group/merge execution. Repeated builds and duplicate bindings make no new interpretation calls. These counts exercise the real parser, compiler, durable service, and source identities with a scripted interpreter. They do not measure live rule recall, entailment, exception fidelity, injection resistance, latency, or cost.

Coverage includes invalid spans and audit ledgers, omitted/replaced/unknown graph branches, table-header context, unsupported exceptions, source/path isolation, independent reuse and invalidation, restart/interruption, coalescing, corruption, rejection lineage, budget failure, and failed-rebuild resumption. Controlled SDK tests exercise real OpenAI client requests on both the direct Responses route and an explicit OpenAI-compatible chat-completions route, including group merge, with destination/key assertions. Saved browser journeys cover standalone preparation/source inspection, exact version selection, rebuild/reload, and linked failed retry.

Final integrated verification (working tree; no paid inference):

| Command | Observed result |
| --- | --- |
| `make check` | Exit 0: Ruff/format, mypy (44 sources), **492 pytest tests**, wheel/sdist, frontend lint/types, **26 Vitest tests** (7 files), production UI build. Pytest: 139.26 seconds in the recorded run. |
| `make browser-test` | Exit 0: **14 Playwright tests**, both shell/journeys projects, 18.9 seconds. Includes independent preparation, exact selection/rebuild/reload, and linked failed retry. |
| `git diff --check` | Exit 0. |
| Local documentation links and fixture hashes | All checked links resolve; pinned PDF/HTML/gold hashes match. |

Checks ran after the generation-resume, rejection-lineage, conservative-budget, and typed step-response changes. Historical component counts in other records remain historical.

## Reviewed changes to existing checks

Existing clinical fixture expectations were preserved. Old page-plan/serial-policy mock response sequences were replaced with section/reconciliation/audit responses, retaining the same declared assessment outcomes. Workflow ordering now prepares both documents before applicability; an assessment-only context limit fails after independent preparation. Cache inputs sort upstream fingerprints consistently so identical assessments reuse their saved work.

The old registry corruption integration case now targets authoritative build manifests: corruption fails operationally until explicit rebuild, while the independent chart remains reusable. Default scan behavior was restored to the documented native-text boundary; the mixed-page test now expects `needs_ocr` and explicit failure rather than assuming default OCR. A duplicate chart method in the test double was removed. These are documented contract/scaffolding changes, not altered insurer/patient answers.

## Remaining acceptance

LD-02–LD-08 runtime is delivered with controlled evidence. LD-01 has the fictional construction/gold corpus; independent held-out insurer cases and detailed semantic table/footnote annotations remain open. LD-09 live source fidelity, rule/edge/exception recall, unsupported satisfied findings, repeatability and calibrated budgets remain open. LD-10 clean-checkout direct-OpenAI upload/build/reuse/assessment/source/export demonstration remains open under the recorded quota deferral. WP-19 remains in progress for release purposes; no live assessment accuracy or remote billing guarantee is claimed.
