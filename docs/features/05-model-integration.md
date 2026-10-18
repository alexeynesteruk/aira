# Model feasibility and OpenAI integration

The model-integration developer establishes a real, repeatable inference path for reviewers. Domain stages receive typed candidate interpretations, usage, and explicit errors through one adapter, without depending on the author's local gateway.

**Work package:** [WP-05](../work-breakdown.md#wp-05-model-experiment-and-adapter). **Kind:** Enabler. **Milestone:** M1. **Owner role:** Model integration. **Status:** [Work breakdown](../work-breakdown.md#work-packages-and-dependencies).

## Business requirements

- [BR-001](../requirements/business-requirements.md#br-001-new-guideline-and-chart-uploads): model interpretation must use supplied document content.
- [BR-010](../requirements/business-requirements.md#br-010-one-command-live-reviewer-workflow): verify the reviewer credential/configuration path and live model access.
- [BR-009](../requirements/business-requirements.md#br-009-progress-and-useful-failure-recovery) and [BR-011](../requirements/business-requirements.md#br-011-generality-and-independent-evaluation): expose failures and record observed quality/usage rather than assuming model suitability.

## Technical requirements

[TR-010](../requirements/technical-requirements.md#tr-010-model-contract-and-configuration) requires a thin OpenAI Responses API adapter, versioned prompts/schemas, explicit `AIRA_MODEL`, pinned SDK compatibility, and a server-only `OPENAI_API_KEY`. M1 verifies the model/API/schema combination; no default is considered validated before this experiment. Keep transport/schema checks separate from richer local validation. [TR-016](../requirements/technical-requirements.md#tr-016-measurement-and-resource-budgets) requires bounded calls and recorded attempts, latency, tokens, and failure categories. Provider-native citations cannot replace application source references.

## Implementation tasks

- [x] Implement `backend/app/llm/` and a CLI experiment using fixed page-tagged fixture text, independent of parser completion.
- [ ] Compare accessible candidates, record any single-model limitation, and select a tested configuration.
- [ ] Verify structured output and credentials with a real invocation; record cold/warm behavior and configuration versions.
- [x] Add controlled-response contract tests for denied access, refusal, timeout, truncation, and malformed output; label fixtures separately from live results.

## Acceptance criteria

- [ ] A02–A05 results can be inspected against independent expected evidence; schema conformity alone does not establish correctness.
- [ ] Adapter checks reject transport/schema failures and keep retries bounded without clinical `missing` substitutions or silent fixture fallback. Fixture/manual comparison records citation discrepancies; production provenance rejection is verified in WP-10/WP-11. [A15–A18](../evaluation.md#required-scenarios)
- [ ] The live-provider portion of A19 succeeds using documented server/container configuration; the chosen SDK recognizes the transport fields and the API key is absent from frontend assets and results.

Use the [evaluation matrix](../evaluation.md#required-scenarios). Model, API configuration, and timeout choices remain experiment outcomes until this evidence exists. AWS credentials are not prerequisites.

## Dependencies and references

Completion dependencies: [WP-02](../work-breakdown.md#wp-02-domain-and-interface-contracts), [WP-03](../work-breakdown.md#wp-03-annotated-fixtures-and-evaluation-expectations).

Design references: [adapter boundaries](../architecture.md#components-and-dependency-direction), [model contract](../model-provider.md#model-contract), [reviewer configuration](../model-provider.md#reviewer-configuration), and [retry principles](../model-provider.md#reliability-and-measurement).

Current evidence: [adapter and feasibility record](../results/model-feasibility.md). The first live probe failed with insufficient quota; the user deferred account resolution. Provider compatibility, semantic evaluation, and tested model selection remain open.
