# Aira feature list

Each feature has its own implementation brief with linked business and technical requirements, concrete tasks, acceptance criteria, dependencies, and design references. The list includes product features and the engineering/delivery enablers required to ship them. Existing WP identifiers are reused so specifications and implementation packages stay connected.

These files define the implementation scope and checked work. The contract baseline, reviewed evaluation corpus, and the full non-live stack — extraction, storage, interpreter, workflow, API, exports, and review UI — are implemented; live model validation remains deferred behind API project quota. The [work breakdown](../work-breakdown.md#work-packages-and-dependencies) is the authoritative record for dependencies, owner roles, and implementation status. Checkbox completion in a feature file must be supported by actual artifacts and checks before its package is marked complete.

## Feature specifications

| Work package | Feature specification | Kind | Milestone |
| --- | --- | --- | --- |
| WP-01 | [Repository foundation and executable checks](01-repository-foundation.md) | Engineering enabler | M0 |
| WP-02 | [Domain and interface contract baseline](02-domain-contracts.md) | Engineering enabler | M0 |
| WP-03 | [Annotated fixtures and expected outcomes](03-evaluation-fixtures.md) | Engineering enabler | M0 |
| WP-04 | [Native PDF ingestion and extraction](04-pdf-ingestion-extraction.md) | Product feature | M2 |
| WP-05 | [OpenAI integration and model feasibility](05-model-integration.md) | Engineering enabler | M1 |
| WP-06 | [Versioned storage and artifact identity](06-versioned-storage.md) | Engineering enabler | M3 |
| WP-07 | [Request context and applicability](07-request-applicability.md) | Product feature | M3 |
| WP-08 | [Policy interpretation and completeness](08-policy-interpretation.md) | Product feature | M3 |
| WP-09 | [Chart facts and criterion evidence](09-chart-evidence.md) | Product feature | M3 |
| WP-10 | [Provenance validation and rule evaluation](10-rule-validation.md) | Engineering enabler | M3 |
| WP-11 | [Assessment workflow and recovery](11-assessment-workflow.md) | Product feature | M3 |
| WP-12 | [HTTP and source inspection API](12-http-source-api.md) | Engineering enabler | M3–M4 |
| WP-13 | [Staff upload and review interface](13-staff-review-interface.md) | Product feature | M4 |
| WP-14 | [Traceable assessment exports](14-assessment-exports.md) | Product feature | M4 |
| WP-15 | [OCR decision and supported input limits](15-ocr-input-limits.md) | Engineering enabler | M2 |
| WP-16 | [Integrated evaluation and regression checks](16-evaluation-regression.md) | Engineering enabler | M5 |
| WP-17 | [Reviewer setup](17-reviewer-packaging.md) | Delivery enabler | M6 |
| WP-18 | [Release verification and design note](18-release-handoff.md) | Delivery enabler | M6 |
| WP-19 | [Long-document rule-set compilation](19-long-document-rule-compilation.md) | Product feature and processing enabler | M2–M6 |

WP-19 is the October 18 long-document extension, with BR-013/TR-019/A21 and its own [implementation plan](../plans/long-document-rule-compilation.md). Existing identifiers and historical evidence remain unchanged. Its full section/dependency/coverage workflow is not established by the working-tree page-fold prototype.

## Start order

Start with [WP-01](01-repository-foundation.md), then establish the [WP-02 contracts](02-domain-contracts.md) and [WP-03 expectations](03-evaluation-fixtures.md). After the contract baseline, storage can progress independently. After the core fixtures, native PDF extraction, model feasibility, and pure validation/rule evaluation can proceed in parallel.

Applicability, policy, and evidence stages can be developed against shared fixtures before their runtime integration. The workflow can be completed only after the input-limit decision. The initial MVP explicitly rejects unsupported scans; handling unusable pages and setting measured limits are mandatory. OCR requires a later justified scope decision. Follow the [dependency graph and table](../work-breakdown.md#work-packages-and-dependencies) for later work and completion prerequisites.

## Requirements and evidence

Read the relevant [BRD](../requirements/business-requirements.md) and [TRD](../requirements/technical-requirements.md) clauses before implementation. The feature briefs describe each package's contribution to those requirements; a reference to a broad requirement does not mean that one package implements every clause.

Keep API/status/error definitions in the TRD, design decisions in [architecture](../architecture.md) and the [model provider decision](../model-provider.md), and scenario definitions in [evaluation](../evaluation.md). Feature files own task checklists and feature-specific acceptance details. When scope changes, update the owning requirement and its dependent references rather than creating a competing definition here.

Record implementation commit, checks run, observed results, and limitations in the work package's completion record. Keep live model evidence separate from fixture tests, preserve reviewed expected outcomes, and leave unchecked work visibly unfinished.
