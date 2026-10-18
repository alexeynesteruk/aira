/**
 * Staff-facing labels for contract values. Status and outcome stay separate:
 * a run status says where processing stands, an outcome says what the saved
 * result concluded — and neither claims an insurer decision.
 */

import type { AssessmentResult, Finding } from './api'

export const READINESS_DISCLAIMER =
  'Documentation readiness only — not an insurer decision.'

export const OUTCOME_LABELS: Record<AssessmentResult['outcome'], string> = {
  applicability_mismatch: 'Policy does not apply to this request',
  documented_requirements_satisfied: 'Documented requirements satisfied',
  documentation_gaps_or_contrary_evidence: 'Documentation gaps or contrary evidence',
  review_required: 'Review required',
}

export const FINDING_LABELS: Record<Finding['status'], string> = {
  met: 'Met',
  not_met: 'Not met',
  missing: 'Missing',
  conflicting: 'Conflicting',
  needs_review: 'Needs review',
}

export const RUN_STATUS_LABELS: Record<string, string> = {
  queued: 'Queued',
  running: 'Running',
  completed: 'Completed',
  needs_input: 'Needs staff input',
  failed: 'Failed',
  interrupted: 'Interrupted',
}

export const PHASE_LABELS: Record<string, string> = {
  extracting: 'Extracting documents',
  interpreting_policy: 'Interpreting policy',
  extracting_chart: 'Reading the chart',
  checking_applicability: 'Checking applicability',
  mapping_evidence: 'Mapping evidence',
  validating: 'Checking the saved result',
  evaluating: 'Evaluating policy',
}

/** Staff-visible order. The model stages have no honest percent of work left. */
export const ASSESSMENT_PHASES = [
  'extracting',
  'interpreting_policy',
  'extracting_chart',
  'checking_applicability',
  'mapping_evidence',
  'evaluating',
] as const

export const PHASE_ACTIVITY: Record<string, string> = {
  extracting: 'Reading every page of the guideline and the chart.',
  interpreting_policy:
    'Building the rule set from the whole guideline. The model is working on this step, and it often takes several minutes.',
  extracting_chart: 'Reading the chart on its own and saving the facts for later assessments.',
  checking_applicability: 'Checking whether the saved policy applies to the saved chart facts.',
  mapping_evidence: 'Comparing the chart with the saved rule set.',
  validating: 'Checking that every quote still matches the saved pages.',
  evaluating: 'Scoring the checklist from the saved rules and the chart evidence.',
}

export const REQUEST_FIELD_LABELS: Record<string, string> = {
  procedure: 'Procedure',
  procedure_code: 'Procedure code',
  anatomical_target: 'Anatomical target',
  laterality: 'Laterality',
  payer: 'Payer',
  plan: 'Plan',
  service_date: 'Service date',
  assessment_cutoff: 'Assessment cutoff',
}

export const CLARIFICATION_FIELD_LABELS: Record<string, string> = {
  ...REQUEST_FIELD_LABELS,
  policy_scope: 'Policy scope',
  policy_effective_period: 'Policy effective period',
  plan_exception: 'Plan exception',
}

export const RELATION_LABELS: Record<string, string> = {
  supporting: 'Supporting',
  contradicting: 'Contradicting',
  context: 'Context',
}

export const APPLICABILITY_LABELS: Record<string, string> = {
  applicable: 'Policy applies',
  mismatch: 'Policy does not apply',
  unresolved: 'Scope unresolved',
}

export function fieldLabel(field: string): string {
  return (
    REQUEST_FIELD_LABELS[field] ??
    CLARIFICATION_FIELD_LABELS[field] ??
    field.replaceAll('_', ' ')
  )
}

export function outcomeLabel(outcome: string): string {
  return OUTCOME_LABELS[outcome as AssessmentResult['outcome']] ?? outcome
}

export function findingLabel(status: string): string {
  return FINDING_LABELS[status as Finding['status']] ?? status
}

export function runStatusLabel(status: string): string {
  return RUN_STATUS_LABELS[status] ?? status
}

export function phaseLabel(phase: string | null | undefined): string {
  return phase ? (PHASE_LABELS[phase] ?? phase.replaceAll('_', ' ')) : 'Waiting'
}

export function relationLabel(relation: string): string {
  return RELATION_LABELS[relation] ?? relation
}

const PAGE_QUALITY_LABELS: Record<string, string> = {
  needs_ocr: 'Needs OCR (scans are unsupported)',
  unusable: 'Unusable',
  uninspected: 'Not inspected',
}

export function pageQualityLabel(quality: string): string {
  return PAGE_QUALITY_LABELS[quality] ?? quality
}
