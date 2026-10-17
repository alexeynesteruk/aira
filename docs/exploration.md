# Initial document exploration

Reviewed the one-page assessment brief and seven-page supplied patient chart. Both PDFs have text on every page and are unencrypted. The first extraction experiment therefore does not need OCR; this does not establish support for unseen scanned inputs.

## Assessment materials

The [brief](sources/Aira_FDE_Build_Case.pdf) names BCBS Florida guideline **Treatments for Varicose Veins / Venous Insufficiency**, identifier **02-33000-31**. Its embedded link is [the BCBS Florida policy PDF](https://mcgs.bcbsfl.com/MCG?activity=openSearchedDocMcg&imgId=76F3FX62Y9H67N4ZU69). Online exploration retrieved this August 15, 2025 revision and the January 1, 2026 revision served by the policy-ID endpoint. Both are 14-page text PDFs; [local snapshots and provenance](../examples/guidelines/README.md) preserve the exact inputs. Their nested rules and versioning implications are discussed in the [research note](research.md#findings-from-the-example-guideline).

The [sample chart](../examples/charts/robert_mitchell_chart_final.pdf), page 7, explicitly says its patient identifiers are fictional and created for demonstration purposes.

## The sample pair does not match

The brief's example policy concerns BCBS Florida vein treatment. The chart lists UnitedHealthcare Medicare Advantage coverage on page 1 and a planned permanent cardiac pacemaker implantation, CPT 33207, on page 7. The chart comes from a New York cardiology practice rather than the Florida vascular setting in the brief.

This makes the supplied chart useful for checking generality and policy applicability. It does not support a coverage conclusion against the named vein policy. A matched policy or a matched synthetic chart is needed to exercise the full medical necessity workflow.

## Chart evidence to preserve

The following are observations from the chart, not independent clinical conclusions or coverage determinations.

| Observation | PDF pages | Implementation implication |
| --- | --- | --- |
| Repeatedly described as asymptomatic; no syncope, near-syncope, dizziness, or exertional limitation. | 3–4 | Preserve negation and repeated documentation without inventing symptoms. |
| Mean heart rate 46 bpm; 12 pauses over 2.5 seconds; longest pause 3.1 seconds, described as nocturnal. | 4–6 | Retain units, timing, and context alongside values. |
| No AV block; zero patient-triggered symptom events; report says no symptom-rhythm correlation can be established. | 4–6 | Do not infer a positive finding from a procedure request or measurement alone. |
| Metoprolol 25 mg remains in use; chart says cardiology reviewed it and deemed it unlikely to be the sole cause. | 2–4, 7 | Distinguish the clinician's documented interpretation from the evaluator's inference. |
| Planned pacemaker request is pending, submitted November 14, 2025. | 7 | Preserve the requested intervention and administrative status separately from evidence sufficiency. |
| Procedure summary reports normal CBC, but the displayed laboratory table gives no CBC values. | 3, 7 | Retain summary provenance; do not fabricate underlying laboratory measurements. |

## Timeline inconsistencies

The Holter report is titled November 1–29, 2025 and reports a wear duration of 29 days, 14 hours (page 5), but is signed November 11 (page 6). It includes a pause dated November 12 (page 5). The November 12 follow-up reviews the monitoring results (pages 3–4), and the November 14 submission references the November 1–29 monitoring period (page 7).

Those dates cannot all describe a completed monitoring period available at the recorded review, signature, and submission times. The product should surface the conflict and retain the conflicting sources rather than silently correcting dates or selecting whichever date appears last.

## PDF extraction observations

The chart uses two-column demographic fields, tables, and sections spanning page breaks. Plain text extraction changes reading order: some labels, values, and bullet content become separated. The Holter report crosses pages 5–6, and the follow-up crosses pages 3–4.

Page-aware extraction and section reconstruction are therefore early technical risks. Table values should remain associated with their labels, and supporting passages may need to span adjacent pages. Rendered pages 5–7 were checked against the extracted text for the monitoring dates and planned procedure.

## Working conclusions

- Check policy applicability before evaluating medical necessity.
- Preserve evidence provenance, negation, time context, and conflicting facts throughout the pipeline.
- Use this chart as an edge case, not a template to hard-code diagnoses, measurements, or criteria.
- Add matched synthetic cases after inspecting the example policy.
- Defer any conclusion about pacemaker coverage until an applicable policy has been supplied and reviewed.
