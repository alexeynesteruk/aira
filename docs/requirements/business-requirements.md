# Aira business requirements

Build a provider-facing evidence checklist that helps clinic staff prepare a prior authorization request using an uploaded patient chart and insurer guideline. Staff should be able to identify the applicable requirements, inspect the supporting evidence, and resolve documentation gaps before submission.

This is the business baseline for the take-home MVP as of October 18, 2026. The requirements describe intended behavior; implementation and release verification remain pending. The [implementation plan](../implementation-plan.md), [architecture](../architecture.md), and [evaluation cases](../evaluation.md) define delivery and technical detail.

## Problem and requirement sources

The [assessment brief, page 1](../sources/Aira_FDE_Build_Case.pdf) describes a Florida vascular surgery practice where more than half of patients have BCBS Florida coverage. Staff rely on uneven institutional knowledge to find supporting chart evidence and anticipate missing medical necessity requirements. The business goals are to reduce preparation effort and avoid denials caused by missed requirements.

The brief requires a working product that accepts new guideline PDFs and unseen patient charts, runs locally from one command, and includes a short design note. It leaves product scope and stack to the developer. The assessment email adds a 45-minute discussion with the interviewer and founding engineer; code is due one day before the call.

Requirements below identify their origin as **brief**, **email**, or **MVP design**. The user's AWS preference informs the selected Bedrock inference platform; AWS is not mandated by the brief, and cloud deployment is outside the assessment's required work. Source-specific risks come from the [document exploration](../exploration.md). In particular, the supplied UHC pacemaker chart and BCBS vein policy are an applicability mismatch, not a matched successful case.

## Stakeholders and business outcomes

| Stakeholder | Need and responsibility |
| --- | --- |
| Clinic authorization staff | Find the relevant requirement and chart passage, understand gaps, and prepare a request with less manual searching. Select the intended procedure and clarify ambiguous administrative details. |
| Treating clinician or clinical reviewer | Resolve clinical ambiguity and contradictory documentation. The application preserves that judgment instead of inventing clinical facts. |
| Practice operations lead | Understand whether the workflow saves staff effort and prevents avoidable documentation omissions. |
| Aira assessors | Run unfamiliar inputs independently, inspect the evidence and failures, and assess design tradeoffs. |
| Project builder | Deliver the working local application, truthful validation results, run instructions, and design note. |

Patients and payers are affected by the wider authorization process but do not use or integrate with this MVP directly.

Observe staff effort through completion time for representative preparation tasks and the time needed to locate supporting passages. Assess documentation quality through reviewed criterion, evidence, and gap findings. Assess reviewer independence through successful clean-checkout execution and new uploads. Record observed results and errors; no baseline, percentage improvement, latency target, or denial-reduction target has been established. Actual denial reduction would require later operational outcome data.

## Scope and staff journey

An assessment contains one uploaded guideline version, one patient chart PDF, and one selected procedure request. It produces an inspectable checklist, unresolved issues, saved results, and an export. A chart may contain several problems or proposed procedures; selecting one request limits the assessment without limiting the product to a hard-coded procedure family.

1. Upload the guideline and chart and see whether all pages can be processed.
2. Confirm the procedure, relevant anatomical target or side, payer, plan, and dates. Select a request if the chart contains several possibilities.
3. Inspect policy applicability. Resolve uncertain scope or replace a mismatched guideline before proceeding.
4. Review requirements and findings grouped by the applicable policy logic. Open policy and chart sources at their cited pages.
5. Clarify ambiguous facts or identify existing documentation needed for an unresolved requirement. Corrections remain separate annotations; original evidence is preserved.
6. Save or export the result. Changed inputs or annotations create a new assessment version that can be compared with the earlier result.

The brief excludes compliance, security, infrastructure, HIPAA, and PHI work. The chosen MVP also excludes insurer decisions or payment guarantees, clinical treatment recommendations, payer submission, appeals generation, EHR/FHIR integration, automatic policy discovery, multi-document patient folders, and an open-ended chat assistant. These exclusions keep the initial workflow small; they do not permit fabricated findings or silent processing failures.

## Business requirements and acceptance

The BR identifiers are stable. Acceptance references point to the corresponding rows in the [evaluation matrix](../evaluation.md#required-scenarios); they describe checks to perform, not completed results.

### BR-001 New guideline and chart uploads

**Origin: brief.** Staff and assessors can upload a new guideline PDF and an unseen patient chart PDF and obtain findings derived from those inputs. The example policy and patient are development materials, not embedded production answers. Unsupported input conditions must be explained rather than silently ignored.

Acceptance: [A02](../evaluation.md#required-scenarios), [A11](../evaluation.md#required-scenarios), [A14](../evaluation.md#required-scenarios), and [A18](../evaluation.md#required-scenarios).

### BR-002 One selected request with relevant side and dates

**Origin: MVP design.** Each assessment identifies one procedure request, including available code, anatomical target or laterality when relevant, payer, plan, and service date. Ambiguous requests require selection or clarification. Evidence from another side, procedure, or relevant time period cannot silently satisfy the request. If readiness is assessed as of a date, that cutoff is explicit. Submission, observation, signature, and service dates retain their distinct meanings.

Acceptance: [A05](../evaluation.md#required-scenarios), [A08](../evaluation.md#required-scenarios), and [A12](../evaluation.md#required-scenarios).

### BR-003 Policy applicability gate

**Origin: MVP design, supported by the sample mismatch.** A confirmed payer or procedure mismatch stops medical necessity assessment against that policy. Uncertain plan coverage, policy scope, effective period, or relevant exception requires clarification. Uploading a guideline does not establish that it applies, and a revision date is not automatically an effective date. The supplied mismatch must remain a useful failure rather than a favorable readiness result.

Acceptance: [A01](../evaluation.md#required-scenarios), [A10](../evaluation.md#required-scenarios), and [A12](../evaluation.md#required-scenarios).

### BR-004 Faithful and complete policy requirements

**Origin: MVP design fulfilling the brief's new-guideline requirement.** The checklist preserves relevant mandatory conditions, alternatives, exclusions, definitions, thresholds, units, durations, and program exceptions. A satisfied subset cannot override a known unresolved governing condition. Unknown or unsupported policy language remains visible for review. Staff are not asked to satisfy every alternative in an OR group, and an average score cannot replace the policy's mandatory logic.

Acceptance: [A06](../evaluation.md#required-scenarios), [A07](../evaluation.md#required-scenarios), [A08](../evaluation.md#required-scenarios), [A10](../evaluation.md#required-scenarios), and [A20](../evaluation.md#required-scenarios).

### BR-005 Distinct evidence states

**Origin: MVP design.** Findings distinguish supported requirements, explicit contrary evidence, missing documentation, conflicting evidence, and interpretation needing review. Missing documentation does not prove that a condition is false. Negation is interpreted relative to the requirement. Contradictory sources remain inspectable, including their dates. Processing failure is a separate state and cannot become a clinical documentation gap.

Acceptance: [A03](../evaluation.md#required-scenarios), [A04](../evaluation.md#required-scenarios), [A05](../evaluation.md#required-scenarios), and [A07](../evaluation.md#required-scenarios).

### BR-006 Inspectable policy and chart citations

**Origin: MVP design.** Each requirement links to its policy wording. Supported or contrary findings link to the chart passages that justify them; conflicts retain the competing sources. Staff can open the exact source pages, including passages spanning pages. A missing finding names the requirement and search limitation without inventing a supporting quote. An existing but irrelevant quotation does not establish support.

Acceptance: [A13](../evaluation.md#required-scenarios), [A15](../evaluation.md#required-scenarios), and [A18](../evaluation.md#required-scenarios).

### BR-007 Actionable gaps and human clarification

**Origin: MVP design.** Unresolved findings explain what clarification or existing documentation is needed for the relevant policy path. Staff can clarify request metadata and review contradictions while retaining the original sources and the provenance of corrections. Suggestions must not invent symptoms, measurements, treatment history, or clinical recommendations. User assertions do not silently become chart-supported evidence or override a conflicting source.

Acceptance: [A03](../evaluation.md#required-scenarios), [A05](../evaluation.md#required-scenarios), [A12](../evaluation.md#required-scenarios), and [A20](../evaluation.md#required-scenarios).

### BR-008 Saved assessments and versioned exports

**Origin: MVP design.** A completed or unresolved assessment can be reopened and exported as structured data and a readable checklist. The result identifies its selected request, exact document versions, findings, citations, unresolved issues, and processing configuration. Changing a guideline, chart, request annotation, or relevant processing configuration creates a traceable new result; prior results remain associated with their original inputs.

Acceptance: [A09](../evaluation.md#required-scenarios), [A10](../evaluation.md#required-scenarios), [A17](../evaluation.md#required-scenarios), and [A19](../evaluation.md#required-scenarios).

### BR-009 Progress and useful failure recovery

**Origin: MVP design.** Staff can see progress and distinguish a completed assessment from one awaiting input, failed, or interrupted. Unreadable pages, unsupported document limits, unavailable model access, and other processing failures explain the next action. Retry or a new run preserves prior results. Partial extraction cannot be presented as a fully processed assessment, and repeated errors must not leave the user in an unexplained loop.

Acceptance: [A14](../evaluation.md#required-scenarios), [A16](../evaluation.md#required-scenarios), and [A17](../evaluation.md#required-scenarios).

### BR-010 One-command live reviewer workflow

**Origin: brief; AWS direction comes from the user and the implementation decision.** From a clean checkout, assessors can launch the local application with one documented command after explicitly documented prerequisites, then process new uploads through live inference, inspect citations, and export results. AWS credentials and selected model access must be explained and verified before delivery. A fixture mode may support testing but cannot substitute for the live workflow. A hosted URL alone does not meet this requirement.

Acceptance: [A19](../evaluation.md#required-scenarios), with configuration and service failures covered by [A16](../evaluation.md#required-scenarios).

### BR-011 Generality and independent evaluation

**Origin: brief for unfamiliar inputs; MVP design for the evaluation protocol.** Validate the workflow across two policy families and unseen charts, including a separately held-out pair at release. Expectations come from reviewed source passages and logic, not from the model response being tested. Include successful cases, uncertainty, mismatches, changed policies, and failures. Report the tested scope, counts, errors, and limitations without claiming universal guideline support or clinical accuracy from a small suite.

Acceptance: [A01–A20](../evaluation.md#required-scenarios), particularly [A11](../evaluation.md#required-scenarios) for held-out inputs and [A20](../evaluation.md#required-scenarios) for omitted governing conditions.

### BR-012 Submission and design discussion

**Origin: brief and email.** Provide the code as a repository or zip with the verified one-line command at least one day before the call. Include a short design note explaining where judgment lives, what is data versus code, and what breaks first with changed guidelines or messy charts. Be prepared for the 45-minute discussion with the interviewer and founding engineer about their independently observed results, tradeoffs, and the path beyond the MVP.

Acceptance: [A19](../evaluation.md#required-scenarios), the [final verification record](../evaluation.md#final-verification-record), and a delivery check for the code, run instructions, design note, and submission timing. The calendar date is still to be established.

## Release acceptance and assumptions

Release requires the [evaluation gates](../evaluation.md#metrics-and-release-gates) and the live local workflow to pass. Known accepted applicability mismatches, fabricated citations, unsupported satisfied findings, omitted mandatory conditions or edges, and incorrect mandatory-rule evaluation block release. Unsupported or ambiguous inputs must produce the intended review or failure state. Narrowing supported scope requires documenting and retesting that boundary; it cannot eliminate the brief's requirement to handle new guidelines and patients.

The following questions remain implementation or delivery decisions rather than established business facts:

| Assumption or open decision | Required resolution |
| --- | --- |
| Staff have the intended chart, guideline, and sufficient request context. | Clarification must be possible when plan, procedure, relevant dates, or policy version cannot be established. A user annotation retains its origin and any source conflict. |
| The release has a bounded PDF envelope. | Feasibility work determines scanned/mixed-PDF support and document limits. Publish the boundary and test supported inputs and rejection behavior. |
| Reviewers can obtain the required AWS model access. | Verify and document the reviewer credential path before delivery; do not assume the author's access is transferable. |
| Evaluation expectations can be independently reviewed. | Select the second policy family and annotate its requirements and cases before using it to claim generality. Preserve a held-out release pair. |
| Delivery timing is relative to the call. | Confirm the actual call date and submission deadline when available; retain the one-day lead time and 45-minute discussion requirement. |

No production deployment, infrastructure procurement, or operational authorization outcome measurement is required to satisfy this take-home baseline.
