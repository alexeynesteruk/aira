# Independent extraction and assessment verification

Controlled record re-checked on this working tree on October 19, 2026. The [WP-19 implementation record](wp19-implementation.md) owns runtime contracts, limits, and remaining gates; its integrated run reports the same 492 pytest and 14 browser counts. This is controlled evidence. It is not live-model validation. No paid probe was run. `evals/expected/` was not edited.

## What the checks exercise

Guideline preparation receives only the guideline. Chart preparation receives only the chart. Assessment then uses the saved rule set, saved facts, the selected request, and staff annotations. Applicability runs before medical-necessity findings. Findings cite saved fact IDs. `require_saved_fact_mapping` rejects an invented or rewritten fact and returns the saved facts unchanged. Extraction and provider failures stay operational errors.

Document builds are the persisted form. A missing or corrupt policy build is not reused and does not hide a readable chart build. An explicit rebuild is required before that policy can be prepared again. Draft reuse does not require human approval. Rejecting a build does not extract the chart again.

The production interpreter may prepare a long guideline as sections. The controlled test interpreters use the document-only `policy()` and `chart()` methods. Every guideline page is still in the extraction that those builds read. Fixture and adapter passes are not semantic accuracy.

## Commands and results

| Command | Result |
| --- | --- |
| `pytest tests/unit/test_stages.py tests/unit/test_fact_mapping.py` | 19 passed in 0.06s. Exit 0. |
| `pytest tests/integration/test_independent_reuse.py` (run twice) | 3 passed in 7.24s, then 3 passed in 7.55s. Both exits 0. |
| `pytest tests/integration/test_openai_interpreter.py::test_chat_transport_keeps_extraction_inputs_and_credentials_isolated` | 1 passed in 1.36s. Exit 0. |
| `make check` | Exit 0. Ruff, format, and mypy (44 sources) passed. Pytest: 490 passed in 116.84s, including 8 document-build tests (`test_document_builds.py` collected and ran both 100-page and 200-page cases). Vitest: 7 files, 25 passed. Frontend production build succeeded. |
| `make browser-test` | Exit 0. 14 passed in 16.1s, including checklist, clarification, source view, export, and a second request whose chart citation is still page 3 of the uploaded chart. |
| `git diff --check` | Exit 0. `evals/expected/` has no diff. The fixture interpreter is not imported by `backend/app`. |

## Still open

Live semantic accuracy, model comparison, and the measured token envelope remain blocked by the deferred API quota. WP-05, A19, and the other live gates stay open. These fixture results do not close them.
