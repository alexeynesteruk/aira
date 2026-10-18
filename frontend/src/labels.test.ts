import { describe, expect, it } from 'vitest'

import {
  FINDING_LABELS,
  findingLabel,
  OUTCOME_LABELS,
  outcomeLabel,
} from './labels'

describe('outcome and finding labels', () => {
  it('maps every saved outcome to its staff wording', () => {
    expect(OUTCOME_LABELS).toEqual({
      applicability_mismatch: 'Policy does not apply to this request',
      documented_requirements_satisfied: 'Documented requirements satisfied',
      documentation_gaps_or_contrary_evidence:
        'Documentation gaps or contrary evidence',
      review_required: 'Review required',
    })
    expect(outcomeLabel('applicability_mismatch')).toBe(
      'Policy does not apply to this request',
    )
  })

  it('keeps review_required visibly unsatisfied', () => {
    expect(outcomeLabel('review_required')).toBe('Review required')
    expect(outcomeLabel('review_required')).not.toMatch(/satisfied/i)
    expect(
      new Set([
        outcomeLabel('applicability_mismatch'),
        outcomeLabel('documented_requirements_satisfied'),
        outcomeLabel('documentation_gaps_or_contrary_evidence'),
        outcomeLabel('review_required'),
      ]).size,
    ).toBe(4)
  })

  it('gives each finding status a distinct label', () => {
    expect(new Set(Object.values(FINDING_LABELS)).size).toBe(5)
    expect(findingLabel('met')).toBe('Met')
    expect(findingLabel('not_met')).toBe('Not met')
    expect(findingLabel('missing')).toBe('Missing')
    expect(findingLabel('conflicting')).toBe('Conflicting')
    expect(findingLabel('needs_review')).toBe('Needs review')
  })
})
