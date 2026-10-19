# Initial model provider decision

The initial MVP uses OpenAI through the Responses API. This October 18, 2026 decision follows the user's provider selection. The application remains a local FastAPI/React service with a thin model adapter. Direct OpenAI access using a reviewer-provided backend API key is required; an explicitly configured LiteLLM endpoint is optional. Cloud deployment is outside this MVP.

The supplied key lists models, but inference failed with `insufficient_quota` on October 18. The user deferred quota resolution; see the [feasibility record](results/model-feasibility.md). M1 must verify a supported model/API/schema combination on the annotated cases before selecting a tested default. `gpt-6-astra` was the initial probe candidate, not a validated model selection. [WP-05](work-breakdown.md#wp-05-model-experiment-and-adapter) owns the remaining experiment.

## Model contract

Use a narrow adapter for independent guideline/chart preparation and assessment over saved rules/facts. [WP-19](features/19-long-document-rule-compilation.md) adds bounded inventory, section extraction, dependency reconciliation, and coverage audit. Every inference operation, including repair and audit, must follow the same selected backend configuration. Configure the model explicitly through `AIRA_MODEL`; retain provider, model identifier, SDK version, prompt/schema revisions, inference settings, and input identities with each result. A model change invalidates affected reusable artifacts and triggers relevant evaluations.

The Responses adapter uses strict JSON-schema output, following the [official structured-output documentation](https://developers.openai.com/api/docs/guides/structured-outputs). It validates the response envelope and candidate locally. Controlled SDK tests pass; live schema compatibility remains an M1 gate. Keep provider transport schemas separate from stricter application invariants.

Flat policy nodes and explicit document/page/span references remain the domain representation. Local code checks references, graph structure, excerpts, supported comparisons, and aggregation. Transport-valid JSON does not prove that a policy is complete or that a quotation supports a finding. The model has no browsing or payer-submission tools.

## Reviewer configuration

Read `OPENAI_API_KEY` only on the server. Do not put it in frontend build variables, committed files, model prompts, exports, or logs. Record key presence and useful configuration errors without exposing the value. `AIRA_MODEL` is nonsecret configuration and must identify the model actually exercised in the experiment.

Document the key/model prerequisites for the local reviewer launch. For direct mode use `OPENAI_API_KEY`, explicit `AIRA_MODEL`, and `AIRA_LLM_BACKEND=openai` (default). Environment loading pins the official endpoint and Responses transport and ignores inherited `OPENAI_BASE_URL`/transport overrides. LiteLLM requires `AIRA_LLM_BACKEND=litellm` and an explicit `OPENAI_BASE_URL`; its default transport is `chat_completions`. All section, group/merge, audit, chart, scope, evidence, repair, and preflight calls share the selected adapter. Do not inherit a personal gateway silently, fall back between providers, or require a running proxy for direct mode. Test all extraction/assessment stages with controlled routing checks and a separate clean-checkout live direct-OpenAI run. The UI and liveness remain available when configuration is absent. Readiness checks local prerequisites and configuration; it does not perform periodic paid inference or assert remote model access. A separate explicit live preflight verifies the configured provider/model and records its outcome. Fixture mode remains labeled test execution and never substitutes silently for a failed live request.

## Reliability and measurement

Bound connection/request timeouts, provider retry attempts, output size, and the overall stage deadline. Classify authentication/access failure, rate limiting, timeout, refusal, incomplete output, and invalid schema/output separately. Configure retries at one deliberate layer; an invalid response may receive only the bounded application repair attempt allowed by the TRD. A failed stage remains an operational failure rather than `missing` clinical documentation.

Record elapsed time, attempts, request identifiers when available, token usage, and failure category. Select numeric budgets from M1 measurements and preserve failed/retried work in the report. A timeout does not establish that no provider work occurred; do not promise exactly-once billing. Currency estimates require dated provider pricing and explicit model assumptions.

## Long-document processing

[TR-019](requirements/technical-requirements.md#tr-019-long-document-rule-set-compilation) and the [WP-19 plan](plans/long-document-rule-compilation.md) replace a whole-document-call assumption with structure-aware section extraction, gathered source context, reconciliation, coverage audit, and deterministic compilation. Bound individual input/output as well as total build calls, tokens, attempts, concurrency, and duration. Preserve per-stage generation provenance, including the actual provider endpoint/transport/model, on reused artifacts. The [implementation record](results/wp19-implementation.md) reports controlled 100/200-page builds and budgets separately from pending live source-fidelity evaluation. Parser limits do not establish semantic support.

## PDF support and future options

Start with native page-aware PDF text/layout extraction. The default parser rejects image-only/unusable pages and unsupported rotation/forms/annotations; OCR remains opt-in. Intake is bounded at 250 pages / 10 MiB with a separate per-call/build budget. No page may disappear from an ordinary completed assessment. WP-15 finalizes the measured byte/page/token envelope from parser and model experiments; parser defaults alone are not a model-context guarantee.

OCR is a later option if representative failures justify the added dependency and an explicit scope decision includes it. Do not claim OCR support for the initial text-based implementation.

## Requirements and verification

The [BRD](requirements/business-requirements.md), [TR-010](requirements/technical-requirements.md#tr-010-model-contract-and-configuration), [technical design](architecture.md), and [evaluation matrix](evaluation.md) define the product contract. The [feasibility record](results/model-feasibility.md) contains the current API reference, implemented configuration, observed quota failure, commands, and remaining checks. M6 must verify the documented launch and new-upload workflow independently from fixture tests.
