# Policy requirements and completeness

Clinic staff receive requirements organized according to the uploaded policy's actual alternatives, mandatory conditions, and exceptions. Unsupported interpretation remains visible instead of becoming a guessed rule.

Work package and status: [WP-08](../work-breakdown.md#wp-08-policy-interpretation-and-completeness). Kind: **Feature**. Milestone: **M3**. Owner: [Domain](../work-breakdown.md#work-packages-and-dependencies).

## Business requirements

- [BR-004](../requirements/business-requirements.md#br-004-faithful-and-complete-policy-requirements): preserve governing conditions, definitions, thresholds, durations, alternatives, and program exceptions. A satisfied extracted subset cannot override known unresolved conditions.
- [BR-006](../requirements/business-requirements.md#br-006-inspectable-policy-and-chart-citations): retain source wording for every requirement and interpreted relationship.
- [BR-011](../requirements/business-requirements.md#br-011-generality-and-independent-evaluation): interpret unfamiliar policies without procedure-specific production code.

Extract the whole guideline independently of any patient or selected request. Preserve every section and source-defined branch, with unsupported semantics exposed for review. Assessment selects and checks the request afterward; extraction is not a universal executable language for every possible policy.

## Technical requirements

Implement [TR-006](../requirements/technical-requirements.md#tr-006-policy-requirements-and-logical-structure): metadata, criteria, source spans, a complete section inventory, flat `all`/`any`/`criterion` nodes, and one root. The extraction input contains only the guideline. Save and reuse technically validated drafts as well as approved artifacts; approval is a separate human judgment.

Map governing text to a supported rule, contextual definition, or unresolved interpretation. Submit candidate graphs and citations to WP-10 validation. Known completeness issues independently block favorable readiness; structural validity alone cannot detect every omitted condition. Preserve exact document and interpretation versions for downstream evidence mapping.

## Implementation tasks

- [x] Implement policy interpretation: versioned prompts in `backend/app/llm/prompts.py`, the stage interpreter in `backend/app/llm/interpreter.py`, and conversion/graph validation in `backend/app/policies/`.
- [x] Capture criteria, connectives, definitions, exceptions, and section coverage with source spans.
- [x] Represent unsupported predicates as explicit review issues.
- [x] Retain generated policy graphs in a hash-keyed rule-set registry (`draft` until human approval; approved graphs are reused for the same document hash/configuration without re-running policy extraction).
- [ ] Compare extracted trees against independently annotated expectations from two policy families.

- [ ] Implement WP-19 LD-03–LD-06 structural planning, contextual local extraction, reference/exception reconciliation, coverage audit, and scoped deterministic compilation; see the [feature](19-long-document-rule-compilation.md) and [plan](../plans/long-document-rule-compilation.md).

## Acceptance criteria

- [ ] Compression stays within the applicable symptom alternative rather than every indication. [A06](../evaluation.md#required-scenarios)
- [ ] Changed thresholds, duration semantics, and policy versions remain distinguishable. [A08–A10](../evaluation.md#required-scenarios)
- [ ] A second policy family needs no procedure-specific code change. [A11](../evaluation.md#required-scenarios)
- [ ] Known omitted governing prose blocks satisfaction even when the extracted tree is true. [A20](../evaluation.md#required-scenarios)

## Dependencies and references

Completion depends on [WP-04](../work-breakdown.md#wp-04-native-pdf-extraction), [WP-05](../work-breakdown.md#wp-05-model-experiment-and-adapter), and [WP-10](../work-breakdown.md#wp-10-validation-and-evaluation-core). Use selected-request fixtures while applicability is integrated. Follow [policy structure](../architecture.md#policy-structure) and [validation boundaries](../architecture.md#validation-boundaries). Controlled-interpreter evidence is in [results/stage-interpreter.md](../results/stage-interpreter.md); acceptance requires live semantic evidence, blocked by the deferred API quota.
