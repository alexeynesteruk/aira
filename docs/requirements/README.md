# Aira requirements and design documents

Use the business requirements to understand the staff outcome, then the technical requirements to implement the corresponding behavior. Both are the implementation baseline for the take-home MVP. Application delivery is still pending.

| Document | Owns |
| --- | --- |
| [Business requirements document](business-requirements.md) | Problem, stakeholders, scope, business rules, BR identifiers, outcomes, and delivery obligations. |
| [Technical requirements document](technical-requirements.md) | Testable technical behavior, TR identifiers, interface contracts, failure semantics, and operational constraints. |
| [Technical design document (TDD)](../architecture.md) | Current implementation snapshot, system architecture, deployment boundary, components, runtime lifecycle, data model, and design rationale. |
| [Model provider decision](../model-provider.md) | Active OpenAI integration boundary, configuration, and feasibility gates. |
| [AWS research](../aws.md) | Superseded initial proposal and dated service findings retained for future options. |
| [Implementation plan](../implementation-plan.md) | Product direction and milestone summaries M0–M6. |
| [Work breakdown](../work-breakdown.md) | Assignable WP packages, dependencies, responsibility, implementation status, and completion evidence. |
| [Feature specifications](../features/README.md) | Per-package business/technical scope, implementation tasks, deliverables, acceptance details, and source references. |
| [Evaluation](../evaluation.md) | A01–A20 acceptance scenarios, independent expected outcomes, metrics, and release gates. |

Requirement identifiers stay stable when wording is clarified. The TRD maps technical requirements to business requirements and acceptance cases; the work breakdown maps implementation packages to technical requirements. Feature briefs provide direct links and implementation checklists for each package. For example, the applicability business requirement BR-003 is implemented through TR-005 and [WP-07](../features/07-request-applicability.md) and checked by A01 and the other scope cases.

Treat the work breakdown as the implementation status record. A milestone is complete when its packages have the required evidence, not when a planning document has been written. Record completed work with its commit, checks, observed results, and limitations.

When behavior changes, update the owning requirement and its rationale, then adjust the architecture, affected packages, and evaluation expectations. Do not silently change expected outcomes to match model output. API contracts belong in the TRD; runtime diagrams belong in the architecture; case expectations belong in evaluation fixtures. This avoids maintaining several conflicting specifications for the same behavior.

The October 18 baseline keeps BR-001–BR-012, TR-001–TR-018, A01–A20, WP-01–WP-18, and M0–M6 stable. OpenAI supersedes the earlier Bedrock proposal; native PDF extraction and explicit scan rejection remain the initial support boundary. Quota deferral changes validation status, not feature scope. Update the work breakdown as evidence arrives instead of repeatedly rewriting the implementation sequence.
