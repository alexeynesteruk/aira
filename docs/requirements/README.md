# Aira requirements and design documents

Use the business requirements to understand the staff outcome, then the technical requirements to implement the corresponding behavior. Both are the implementation baseline for the take-home MVP. Application delivery is still pending.

| Document | Owns |
| --- | --- |
| [Business requirements document](business-requirements.md) | Problem, stakeholders, scope, business rules, BR identifiers, outcomes, and delivery obligations. |
| [Technical requirements document](technical-requirements.md) | Testable technical behavior, TR identifiers, interface contracts, failure semantics, and operational constraints. |
| [Architecture](../architecture.md) | System context, deployment boundary, components, runtime lifecycle, data model, and design rationale. |
| [AWS decision](../aws.md) | Provider/service choices and the current AWS constraints supporting those choices. |
| [Implementation plan](../implementation-plan.md) | Product direction and milestone summaries M0–M6. |
| [Work breakdown](../work-breakdown.md) | Assignable WP packages, dependencies, deliverables, responsibility, and completion evidence. |
| [Evaluation](../evaluation.md) | A01–A20 acceptance scenarios, independent expected outcomes, metrics, and release gates. |

Requirement identifiers stay stable when wording is clarified. The TRD maps technical requirements to business requirements and acceptance cases; the work breakdown maps implementation packages to technical requirements. For example, the applicability business requirement BR-003 is implemented through TR-005 and WP-07 and checked by A01 and the other scope cases.

Treat the work breakdown as the implementation status record. A milestone is complete when its packages have the required evidence, not when a planning document has been written. Record completed work with its commit, checks, observed results, and limitations.

When behavior changes, update the owning requirement and its rationale, then adjust the architecture, affected packages, and evaluation expectations. Do not silently change expected outcomes to match model output. API contracts belong in the TRD; runtime diagrams belong in the architecture; case expectations belong in evaluation fixtures. This avoids maintaining several conflicting specifications for the same behavior.
