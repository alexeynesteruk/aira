# Initial model provider decision

The initial MVP uses OpenAI through the Responses API. This October 18, 2026 decision follows the user's provider selection and supersedes Bedrock as the implementation dependency. The application remains a local FastAPI/React service with a thin model adapter. AWS credentials, Bedrock activation, and a cloud deployment are not prerequisites for this MVP.

The supplied key lists models, but inference failed with `insufficient_quota` on October 18. The user deferred quota resolution; see the [feasibility record](results/model-feasibility.md). M1 must verify a supported model/API/schema combination on the annotated cases before selecting a tested default. `gpt-6-astra` was the initial probe candidate, not a validated model selection. [WP-05](work-breakdown.md#wp-05-model-experiment-and-adapter) owns the remaining experiment.

## Model contract

Use a narrow adapter for policy/request interpretation and chart evidence mapping. Configure the model explicitly through `AIRA_MODEL`; retain provider, model identifier, SDK version, prompt/schema revisions, inference settings, and input identities with each result. A model change invalidates affected reusable artifacts and triggers relevant evaluations.

The Responses adapter uses strict JSON-schema output, following the [official structured-output documentation](https://developers.openai.com/api/docs/guides/structured-outputs). It validates the response envelope and candidate locally. Controlled SDK tests pass; live schema compatibility remains an M1 gate. Keep provider transport schemas separate from stricter application invariants.

Flat policy nodes and explicit document/page/span references remain the domain representation. Local code checks references, graph structure, excerpts, supported comparisons, and aggregation. Transport-valid JSON does not prove that a policy is complete or that a quotation supports a finding. The model has no browsing or payer-submission tools.

## Reviewer configuration

Read `OPENAI_API_KEY` only on the server. Forward it explicitly to the backend container; do not put it in frontend build variables, committed files, model prompts, exports, or logs. Record key presence and useful configuration errors without exposing the value. `AIRA_MODEL` is nonsecret configuration and must identify the model actually exercised in the experiment.

Document the key/model prerequisites for the local reviewer launch. The UI and liveness remain available when configuration is absent. Readiness checks local prerequisites and configuration; it does not perform periodic paid inference or assert remote model access. A separate explicit live preflight verifies the configured provider/model and records its outcome. Fixture mode remains labeled test execution and never substitutes silently for a failed live request.

## Reliability and measurement

Bound connection/request timeouts, provider retry attempts, output size, and the overall stage deadline. Classify authentication/access failure, rate limiting, timeout, refusal, incomplete output, and invalid schema/output separately. Configure retries at one deliberate layer; an invalid response may receive only the bounded application repair attempt allowed by the TRD. A failed stage remains an operational failure rather than `missing` clinical documentation.

Record elapsed time, attempts, request identifiers when available, token usage, and failure category. Select numeric budgets from M1 measurements and preserve failed/retried work in the report. A timeout does not establish that no provider work occurred; do not promise exactly-once billing. Currency estimates require dated provider pricing and explicit model assumptions.

## PDF support and future options

Start with native page-aware PDF text/layout extraction. The current conservative parser rejects all raster-image pages, including decorative images in otherwise textual pages, plus unsupported rotation/forms and unusable text. No page may disappear from an ordinary completed assessment. WP-15 finalizes the measured byte/page/token envelope from parser and model experiments; parser defaults alone are not a model-context guarantee.

OCR is a later option if representative failures justify the added dependency and an explicit scope decision includes it. Do not require Textract access or claim OCR support for the initial text-based implementation. The [October 17 AWS research](aws.md) remains useful for evaluating future Bedrock, Textract, and hosted deployment options; its service-specific requirements do not apply to the current provider.

## Requirements and verification

The [BRD](requirements/business-requirements.md), [TR-010](requirements/technical-requirements.md#tr-010-model-contract-and-configuration), [technical design](architecture.md), and [evaluation matrix](evaluation.md) define the product contract. The [feasibility record](results/model-feasibility.md) contains the current API reference, implemented configuration, observed quota failure, commands, and remaining checks. M6 must verify the documented launch and new-upload workflow independently from fixture tests.
