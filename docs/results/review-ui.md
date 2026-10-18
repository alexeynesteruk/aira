# WP-13 review UI verification

Verified October 18, 2026 against the working-tree application. [WP-13](../work-breakdown.md#wp-13-staff-interface) owns the staff workspace and [WP-14](../work-breakdown.md#wp-14-exports) owns the export actions it exposes. Every browser check runs against `tests/e2e/fixture_server.py` — a test-only `create_app` whose `E2EInterpreter` returns source-valid domain records resolved from the real extractions of the uploaded PDFs. The readiness `provider.detail` labels the fixture ("Fixture interpreter for browser tests; no live model calls."), and the journeys exercise the real routes, persistence, and UI code — controlled evidence, never a live-model claim.

## Implemented views

- **Upload** (`frontend/src/components/Upload.tsx`): per-role file inputs that upload on selection and show filename/page count/short SHA or the API error message plus action; optional request-metadata fields become `staff-<field>` text/date annotations; `request_context` stays omitted.
- **Readiness** (`components/Readiness.tsx`): prerequisites and `provider.detail` shown; starting an assessment stays disabled until ready.
- **Run view** (`components/RunView.tsx`): 1 s polling while queued/running with phase, completed phases, and "X of Y" pages (never a percentage); document filenames; `parent_run_id` link; outcome banner with the four saved-outcome labels plus the fixed disclaimer; failed/interrupted runs show the stored error and a linked retry; `needs_input` runs show the rationale and the clarification form (sourced fields require a resolution reason and produce `resolves_conflict` annotations with `original_sources`); completed runs show applicability with citations, the request summary with annotations, the node-tree checklist (all/any grouping, finding cards with five distinct status labels, policy and chart citations, "Documentation needed" for missing findings), issues with `blocks_readiness`, a provenance block (model/prompts/parser/sdk/per-stage usage), and the two export links. The UI never evaluates rules itself.
- **Source viewer** (`components/SourceViewer.tsx`): side panel per citation — document filename, page, extraction ID, the block list with the cited `[start, end)` span marked, and an "Open original PDF" link to the byte-preserving file route.
- **Routing**: `?run=<id>` via `history.pushState`; a fresh visit or reload of `?run=<id>` reopens the persisted run (journey 6 proves it).

## Journeys (fixture interpreter, saved in `frontend/e2e/journeys.spec.ts`)

| Journey | Matrix coverage (UI level) |
| --- | --- |
| Mismatch (A01): upload without metadata → "Policy does not apply to this request", no checklist, applicability citation opens the page with the exact `<mark>` span, fixture label visible. | A01, A19 |
| Gaps (A03): procedure `E2E gaps` → "Documentation gaps or contrary evidence", "All of the following" tree, Met finding with chart citation, Missing finding with "Documentation needed" and no chart citation, policy p3 and chart p3 viewers, JSON export filename `aira-<run>.json` reloaded to the same run and badge-matching statuses, Markdown export `aira-<run>.md`. | A03, A12, A13, A19 |
| Contrary: procedure `E2E contrary` → real evaluator outcome `documentation_gaps_or_contrary_evidence`, "Not met" and "Conflicting" badges, the "Contradicting" relation label, and a mutually conflicting fact pair. | A02, A04, A05 |
| Satisfied: procedure `E2E satisfied` → single met criterion → "Documented requirements satisfied". | A03 |
| Clarify: procedure `E2E clarify` → `needs_input` listing `plan`; submitting creates a linked child run (new URL, "Previous attempt") completing with the staff `plan` annotation preserved; the parent stays `needs_input` and its Markdown export states "Assessment stopped for staff input". | A13, A16, A17 |
| Failure: image-only chart → status `failed` with the extraction message/action and no outcome banner; linked retry offered. | A16 |
| Upload rejection: encrypted chart → the API error message shows and Start stays disabled. | A14 |
| Persistence: `?run=<id>` reloaded renders the same persisted outcome and findings. | A19 |

The shell spec still proves the unconfigured application explains missing prerequisites and disables Start.

## Observed verification

| Command | Result |
| --- | --- |
| `npm --prefix frontend test` | 19 checks across 6 files pass. |
| `npx playwright test` (`shell` + `journeys`) | 10 checks pass (2 shell, 8 journeys). |
| `make check` | Backend checks pass; frontend lint/typecheck/Vitest/build pass. |

Unit coverage: outcome/finding label maps (five distinct finding labels and an unsatisfied `review_required`), the all/any policy tree in node order, a missing finding without a chart citation, conflict-resolution vs plain clarification annotations, the failed-run view with its action and retry, readiness prerequisites plus `provider.detail`, and code-point-accurate citation highlighting through an astral-plane character.

## Limitations

- Fixture interpreter: outcomes are scripted records over real citations; semantic quality and live A19 remain unverified behind the deferred quota.
- No Docker locally — the container path is verified in CI; locally the same static mount serves the built assets.
