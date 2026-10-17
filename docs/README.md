# Aira project documentation

Build a small, working assistant that helps clinic staff assess prior authorization readiness using a patient chart PDF and an insurer guideline PDF. It must work on new documents supplied by reviewers. This page separates the assessment requirements from proposed implementation choices.

## Confirmed requirements

Source: [build case, page 1](sources/Aira_FDE_Build_Case.pdf). The delivery logistics also come from the accompanying assessment email.

| Area | Requirement |
| --- | --- |
| Problem | Reduce staff effort preparing requests and reduce denials caused by missed medical necessity requirements. |
| Setting | A Florida vascular surgery practice; more than half of patients have BCBS Florida coverage. |
| Guideline input | Accept new guidelines as PDF uploads. The example is not a fixed boundary. |
| Patient input | Accept patient chart PDFs, including patients not seen during development. Synthetic examples are allowed. |
| Product | A working, narrow MVP that runs end to end on real inputs. Scope is ours to define. |
| Runtime | A one-line command on the reviewers' machine, tested from a clean checkout. |
| Stack | Any stack. Aira uses Python, FastAPI, React, TypeScript, and Postgres; these are not mandated. |
| Submission | Code as a repository or zip, sent one day before the call. |
| Design note | Explain where judgment lives, what is data versus code, and what breaks first with guideline changes or messy charts. |
| Discussion | A 45-minute call about the reviewers' findings, assumptions, tradeoffs, failures, and how to extend the MVP. |
| Explicit exclusions | Do not spend time on compliance, security, infrastructure, HIPAA, or PHI handling. |

## Proposed MVP

These choices are provisional until research and a small extraction experiment establish feasibility.

1. Upload a guideline PDF and a patient chart PDF.
2. Extract the payer, plan, requested procedure, relevant dates, and guideline scope, retaining page references.
3. Show whether the selected guideline appears applicable. Stop or request clarification for a mismatched payer, procedure, or unresolved scope.
4. Extract medical necessity criteria and their logical relationships from the guideline.
5. Match chart evidence to each criterion, preserving explicit negative findings, missing information, and contradictions as different states.
6. Present a reviewable checklist with guideline and chart citations, unresolved gaps, and supported next steps for staff.

The output describes evidence against a supplied policy. It does not claim the insurer has approved or denied a request. No insurer portal submission, EHR integration, billing workflow, or broad policy discovery service is planned for the initial MVP.

## Initial architecture hypothesis

Keep PDF extraction, policy interpretation, chart evidence extraction, and evaluation as separate stages. Retain original text and page identity so staff can inspect every material claim. A structured intermediate representation should preserve AND/OR logic, exclusions, thresholds, units, dates, and uncertainty rather than flattening the policy into a summary.

An LLM may interpret prose and locate evidence; code can validate output structure, check citations, and evaluate supported rule types. Whether the rule representation can cover enough unseen guidelines is an open design question. Unsupported policy logic should remain visible for review.

Proposed record types are a document with page text, a scoped policy with criteria, a procedure request, chart evidence with provenance, and an assessment linking criteria to evidence. No framework, model, persistence layer, or UI library has been selected.

## Candidate acceptance scenarios

These are proposed checks for implementation, not completed tests.

- A previously unseen guideline and chart produce a cited, reviewable assessment.
- The supplied BCBS vein guideline and UHC pacemaker chart trigger an applicability mismatch.
- Explicit denial of symptoms does not become a missing symptom history or a positive symptom finding.
- Missing documentation, contrary evidence, and conflicting documentation remain distinguishable.
- An OR branch can satisfy a criterion without requiring every alternative; an AND branch requires all mandatory elements.
- A threshold retains its unit and context, such as sleeping versus awake measurements.
- Unreadable input or unsupported policy logic produces an actionable error or review state.
- A changed guideline produces a new assessment tied to that exact document.
- A clean checkout starts with the documented one-line command and clearly stated prerequisites.

## Open decisions

- What minimum set of policy logic can we represent and evaluate reliably?
- How should staff resolve an ambiguous procedure, payer, plan, policy version, or service date?
- Which PDF extraction approach handles tables and page-spanning sections adequately?
- Does the first release include OCR, or explicitly surface scanned PDFs as unsupported?
- Which model and structured output approach perform adequately on unseen inputs?
- What launch command and dependency packaging make local evaluation easiest?
- Which small set of synthetic cases demonstrates failures as well as successful matches?

## Next exploration steps

1. Review common approaches, community reports, and primary technical sources.
2. Obtain and inspect the linked example guideline, recording its scope and version.
3. Select a thin workflow and prototype extraction on both matched and mismatched document pairs.
4. Decide the application structure, stack, and evaluation cases based on those results.
5. Build the end-to-end product and write the short design note from actual tradeoffs.

See [initial document exploration](exploration.md) for source-specific findings.
