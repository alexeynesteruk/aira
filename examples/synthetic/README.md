# Synthetic scenario PDFs (development)

**These are fictional software test fixtures — not payer guidelines, patient
records, or medical recommendations.** Each file renders one authored Markdown
source from `tests/fixtures/scenarios/` so reviewers and future live
evaluations can exercise the PDF-only intake. The held-out pair
(`held_policy`, `held_chart`) is deliberately not rendered.

`manifest.json` pins each PDF to its source (`path` + `sha256`), records the
logical→PDF page identity, and names the rendering tool
(`pdf-tools pdf-create` 0.4.0 / WeasyPrint 70.0). Regenerate with:

```bash
python3 scripts/render_scenarios.py
```

## Development cases

Request metadata below is from `evals/cases/development.json`; the intended
outcome is the reviewed expectation in `evals/expected/development.json`.

| case_id | policy PDF | chart PDF | intended scenario |
| --- | --- | --- | --- |
| venous_matched | venous_policy_v1 | venous_chart_matched | documented requirements satisfied |
| venous_missing_diameter | venous_policy_v1 | venous_chart_missing_diameter | documentation gaps (missing diameter) |
| venous_negative_reflux | venous_policy_v1 | venous_chart_negative_reflux | contrary evidence (no reflux documented) |
| venous_conflicting_diameter | venous_policy_v1 | venous_chart_conflicting_diameter | conflicting evidence → review required |
| venous_ulcer_alternative | venous_policy_v1 | venous_chart_ulcer_alternative | satisfied via the ulcer OR-branch |
| venous_false_and_unknown | venous_policy_v1 | venous_chart_false_and_unknown | gaps: false + unknown findings |
| venous_threshold_below | venous_policy_v1 | venous_chart_threshold_below | below the 3.0 mm bound → gaps |
| venous_threshold_at | venous_policy_v1 | venous_chart_threshold_at | at the bound → satisfied |
| venous_threshold_above | venous_policy_v1 | venous_chart_threshold_above | above the bound → satisfied |
| venous_unit_missing | venous_policy_v1 | venous_chart_unit_missing | unstated unit → review required |
| venous_rule_changed | venous_policy_v2 | venous_chart_matched | revised wording changes the outcome → gaps |
| venous_wrong_side | venous_policy_v1 | venous_chart_wrong_side | left-leg evidence, right request → gaps |
| venous_date_conflict | venous_policy_v1 | venous_chart_date_conflict | observation after cutoff → review required |
| venous_embedded_instruction | venous_policy_v1 | venous_chart_embedded_instruction | embedded "ignore the policy" text is inert → satisfied |
| venous_unknown_plan | venous_policy_v1 | venous_chart_unknown_plan | unresolvable plan metadata → needs staff input |
| monitor_matched | monitor_policy | monitor_chart | satisfied (monitoring scenario family) |
| supplied_pair_mismatch | (real BCBS policy PDF) | (real supplied chart) | applicability mismatch — not rendered |

All venous cases use the same request: procedure "endovenous ablation",
target "great saphenous vein", laterality "right", payer "Fixture Health
Plan", plan "Test Vascular", service date 2026-10-28, cutoff 2026-10-18.
The monitoring case uses procedure "outpatient ambulatory ECG recording",
payer "Fixture Health Plan", plan "Test Monitoring", same dates.

## Example run

```bash
uv run --project backend python -m app.cli assess \
  --policy examples/synthetic/venous_policy_v1.pdf \
  --chart examples/synthetic/venous_chart_matched.pdf \
  --procedure "endovenous ablation" \
  --anatomical-target "great saphenous vein" \
  --laterality right \
  --payer "Fixture Health Plan" \
  --plan "Test Vascular" \
  --service-date 2026-10-28 \
  --assessment-cutoff 2026-10-18
```

Requires a configured `OPENAI_API_KEY` and `AIRA_MODEL`; see the repository
README. These files are also the inputs the fixture browser journeys stand
in for when no live model is available.
