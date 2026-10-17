# Aira project documentation

Build a small, working assistant that helps clinic staff assess prior authorization readiness using a patient chart PDF and an insurer guideline PDF. It must work on new documents supplied by reviewers. The implementation direction is a cited evidence checklist using FastAPI, React/TypeScript, and AWS Bedrock, with a local one-command launch.

Requirements and research are documented; application implementation and live service validation are next. Start with the [implementation plan](implementation-plan.md).

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

## Chosen MVP

Assess one selected procedure request against one uploaded policy version. Extract scope, retain the policy's logical relationships, match chart evidence, and show a checklist with source-page navigation and unresolved documentation needs. Stop on a known policy mismatch and request clarification when scope is uncertain.

Missing documentation, contrary evidence, conflicting facts, unsupported interpretation, and processing failures remain distinct. A satisfied subset of extracted rules cannot override a known omitted governing condition. Staff resolve uncertainty; the product does not issue an insurer approval or denial.

The supplied chart is a UHC pacemaker request, while the example guideline concerns BCBS Florida vein treatment. That pair is an applicability test. Matched fictional cases and a second policy family are necessary to test the full workflow.

## Documentation guide

| Document | Purpose |
| --- | --- |
| [Implementation plan](implementation-plan.md) | Product scope, decisions, M0–M6 milestones, planned folders, reviewer launch, risks, and delivery. |
| [Architecture](architecture.md) | Domain records, policy representation, evidence and logical states, validation, execution, and storage. |
| [Evaluation](evaluation.md) | Acceptance scenarios, independent expectations, test layers, metrics, and release blockers. |
| [AWS research](aws.md) | Verified service constraints, Bedrock configuration, OCR choices, and later hosting path. |
| [Online implementation research](research.md) | Reddit workflow observations, public implementations, PDF tooling, and design tradeoffs. |
| [Document exploration](exploration.md) | Sample mismatch, source evidence, chronology conflicts, and extraction risks. |
| [Guideline provenance](../examples/guidelines/README.md) | Two exact policy snapshots, hashes, and observed differences. |

The Obsidian review informs engineering practices such as versioned prompts, independent test expectations, source verification, and honest failure reporting. Its detailed private source register stays in the vault. AWS-specific capabilities are checked against current public documentation.

## Next implementation gate

Finalize the domain contracts and annotated cases, then run the small Bedrock and PDF feasibility experiments in M1–M2. These establish the exact model/region, credential onboarding, parser settings, tested input limits, and whether OCR is included. No AWS deployment is needed to perform this work. Infrastructure, EHR integration, and payer submission remain outside the take-home scope.
