# OpenAI adapter and feasibility record

On October 18, 2026, the supplied key could list models, but inference returned HTTP 429 with error type `insufficient_quota` and a billing-related message. The user deferred quota resolution. Live model suitability, structured-output compatibility, and assessment quality remain unverified. No further live calls are scheduled automatically.

## Implemented and tested

`backend/app/llm/` contains server-side dotenv/environment configuration, the OpenAI Responses adapter, an explicit access probe, versioned scope/policy/evidence prompts, and an isolated-stage experiment CLI. The locked SDK is OpenAI Python 2.54.0. The adapter sends a strict JSON schema with all fields required and nullable optional values, `store=false`, and truncation disabled. It has no tools, browser access, or fixture fallback. [Official structured-output documentation](https://developers.openai.com/api/docs/guides/structured-outputs) was inspected during implementation; the selected account/model combination still needs a successful live schema test.

Controlled tests run the real SDK over a mock HTTP transport. They cover successful structured output, request identity/usage, access rejection, rate limits, exhausted quota, transient recovery, connection/request/stage timeouts, refusal, incomplete output, malformed envelopes and JSON, local schema rejection, and secret omission. Experiment tests verify source hashes, development-only inputs, separation from expected patient answers, and preparation without credentials. These tests establish adapter behavior, not model quality.

The initial configuration has a 30-second request timeout, a 65-second stage deadline, at most two provider attempts, and a 4,096-token output cap configurable via `AIRA_MAX_OUTPUT_TOKENS` (validated 1–32,768; changing it changes run/cache identity). These are provisional engineering bounds, not measured performance limits. SDK retries are disabled; the adapter owns transient retries. Exhausted quota is detected in either the provider's `code` or `type`, including nested error envelopes, and requires corrective action without retry. Invalid output is rejected without automatic repair in this first adapter.

## Observed live access result

| Item | Observation |
| --- | --- |
| Date | October 18, 2026 local time; initial probe timestamp `2026-10-17T21:50:22.604719+00:00`. |
| Probe model | `gpt-6-astra`, an explicit initial probe candidate, not a validated default. |
| Model listing | The key listed `gpt-6-astra`, `gpt-4.1-mini`, and `gpt-4o-mini`. Listing does not establish inference quota or quality. |
| Initial structured probe | Two HTTP 429 attempts, approximately 5.44 seconds total; no candidate returned and no token usage supplied. |
| Diagnostic request | One additional minimal request confirmed `type=insufficient_quota`; no successful inference. |
| Adapter correction | Quota classification now checks both error `code` and `type`. Regression tests cover the observed shape; no additional live request was made after the user deferred quota work. |
| Quality/cost conclusion | None. There are no live semantic results, cold/warm comparisons, measured token costs, or selected production model. |

Credentials remain in the ignored `.env` file or process environment. No key, provider response body, or private account identifier is included in this record.

## Reproducible commands

From the repository root, prepare an isolated fixture experiment without making an API call:

```sh
uv run --project backend python -m app.llm.experiment --case venous_matched --stage scope
```

The command writes the exact prompt, schema, logical page-tagged inputs, versions, and hashes under ignored `data/model-experiments/`. Stages are `scope`, `policy`, and `evidence`. The evidence stage uses independently annotated policy criteria to isolate evidence mapping; expected patient findings are never sent to the model. The policy stage receives only the policy and selected request. These are text experiments, not PDF extraction or a production assessment pipeline. The reserved release pair is excluded.

After quota is restored, explicitly verify access:

```sh
uv run --project backend python -m app.llm.preflight [--data-dir DIR]

# The probe persists its verdict atomically to <data-dir>/provider-verification.json
# (verified or failed, never the key); readiness reports it when its model matches.
```

Then run a billable stage experiment with the configured model:

```sh
uv run --project backend python -m app.llm.experiment --case venous_matched --stage scope --live
```

`--model MODEL_ID` selects a comparison candidate; `--repeat 2` records separate calls and stops on a failure. Every output records the actual model, SDK, prompts, schema, hashes, budgets, attempts, latency, and reported usage. `candidate_received` means transport/schema success only. Compare results with the referenced independent expectations and record citation, logic, and evidence discrepancies before claiming semantic success. The CLI never modifies expectations or treats its own answer as a passing score.

## Remaining WP-05 work

Restore API project quota, verify all three schemas against live Responses output, compare accessible models on A02–A05 and representative uncertainty/second-family cases, inspect source citations and semantic disagreements, and measure repeated-run latency/usage. Select a tested model and budgets only from those results. Production domain conversion, source validation, stage sequencing, and input-envelope verification are separate downstream integration gates.
