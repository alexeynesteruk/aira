# Aira prior authorization assistant

Take-home project for Aira's Forward Deployed Engineer assessment. The intended product helps clinic staff compare patient chart evidence with an uploaded insurer guideline and identify gaps before submitting a prior authorization request.

Status: requirements, architecture, and implementation decomposition documented. The chosen direction is FastAPI, React/TypeScript, and AWS Bedrock, with a one-command local runtime for reviewers. Application implementation has not started; there is no working run command yet.

- [Project documentation](docs/README.md)
- [Business requirements document](docs/requirements/business-requirements.md)
- [Technical requirements document](docs/requirements/technical-requirements.md)
- [Implementation plan and milestones](docs/implementation-plan.md)
- [Work breakdown and dependencies](docs/work-breakdown.md)
- [Architecture and evidence semantics](docs/architecture.md)
- [Evaluation and release checks](docs/evaluation.md)
- [AWS service choices and verified constraints](docs/aws.md)
- [Initial document exploration](docs/exploration.md)
- [Implementation research and recommendation](docs/research.md)
- [Assessment brief](docs/sources/Aira_FDE_Build_Case.pdf)
- [Supplied fictional patient chart](examples/charts/robert_mitchell_chart_final.pdf)
- [Guideline snapshots and provenance](examples/guidelines/README.md)

## Current structure

```text
docs/
  README.md                  Requirements and documentation guide
  requirements/
    README.md                Document ownership and traceability
    business-requirements.md Staff outcomes, scope, and business rules
    technical-requirements.md System and interface requirements
  implementation-plan.md     Scope, milestones, repository structure, delivery
  work-breakdown.md          Packages, dependencies, and completion evidence
  architecture.md            Context, components, lifecycle, and evidence logic
  evaluation.md              Acceptance scenarios and release gates
  aws.md                     AWS decisions and current service constraints
  exploration.md             Findings from the supplied documents
  research.md                Online research and proposed implementation
  sources/                   Original assessment materials
examples/
  charts/                    Supplied fictional chart and future synthetic inputs
  guidelines/                Versioned BCBS Florida policy snapshots
```

The [planned application structure](docs/implementation-plan.md#planned-repository-structure) will be created with the first implementation changes. Start with WP-01–WP-03 in the [work breakdown](docs/work-breakdown.md), followed by the Bedrock/PDF experiments. Submission requires a working product, a one-line launch command verified on a clean checkout, and a short design note. Code must reach the reviewers one day before the call.
