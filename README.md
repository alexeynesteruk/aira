# Aira prior authorization assistant

Take-home project for Aira's Forward Deployed Engineer assessment. The intended product helps clinic staff compare patient chart evidence with an uploaded insurer guideline and identify gaps before submitting a prior authorization request.

Status: exploration and requirements. Application implementation has not started; there is no application run command yet.

- [Project documentation](docs/README.md)
- [Initial document exploration](docs/exploration.md)
- [Implementation research and recommendation](docs/research.md)
- [Assessment brief](docs/sources/Aira_FDE_Build_Case.pdf)
- [Supplied fictional patient chart](examples/charts/robert_mitchell_chart_final.pdf)
- [Guideline snapshots and provenance](examples/guidelines/README.md)

## Current structure

```text
docs/
  README.md                  Requirements, proposed scope, and open decisions
  exploration.md             Findings from the supplied documents
  research.md                Online research and proposed implementation
  sources/                   Original assessment materials
examples/
  charts/                    Supplied fictional chart and future synthetic inputs
  guidelines/                Versioned BCBS Florida policy snapshots
```

Application folders and the stack will be chosen after exploration. Submission requires a working product, a one-line launch command verified on a clean checkout, and a short design note. Code must reach the reviewers one day before the call.
