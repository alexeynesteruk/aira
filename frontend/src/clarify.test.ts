import { describe, expect, it } from 'vitest'

import type { RequestContext, SourceSpan } from './api'
import { buildClarificationAnnotations } from './clarify'

const SPAN: SourceSpan = {
  block_id: 'block-1',
  document_id: 'doc-1',
  document_sha256: 'a'.repeat(64),
  extraction_id: 'ext-1',
  page: 2,
  start: 4,
  end: 20,
  excerpt: 'documented excerpt',
}

const context: RequestContext = {
  procedure: 'endovenous ablation',
  field_sources: [{ field: 'payer', sources: [SPAN] }],
  unresolved_fields: [],
}

const prior = [
  {
    kind: 'text' as const,
    annotation_id: 'staff-procedure',
    field: 'procedure',
    value: 'endovenous ablation',
    created_at: '2026-10-18T10:00:00Z',
  },
]

describe('buildClarificationAnnotations', () => {
  it('keeps prior annotations and replaces same-field ones', () => {
    const annotations = buildClarificationAnnotations(
      context,
      [...prior, { ...prior[0], annotation_id: 'staff-plan', field: 'plan', value: 'Old' }],
      [{ field: 'plan', value: 'New plan' }],
      '2026-10-18T12:00:00Z',
    )
    const fields = annotations.map((item) => item.field).sort()
    expect(fields).toEqual(['plan', 'procedure'])
    const plan = annotations.find((item) => item.field === 'plan')!
    expect(plan.value).toBe('New plan')
    expect(plan.resolves_conflict).toBeUndefined()
    expect(plan.original_sources).toBeUndefined()
  })

  it('requires a resolution reason when the field has documented sources', () => {
    expect(() =>
      buildClarificationAnnotations(context, [], [{ field: 'payer', value: 'Other' }]),
    ).toThrow(/resolution reason/i)
  })

  it('builds a conflict-resolution annotation with original sources', () => {
    const [annotation] = buildClarificationAnnotations(
      context,
      [],
      [{ field: 'payer', value: 'Other payer', reason: 'Documented value was stale.' }],
      '2026-10-18T12:00:00Z',
    )
    expect(annotation.resolves_conflict).toBe(true)
    expect(annotation.resolution_reason).toBe('Documented value was stale.')
    expect(annotation.original_sources).toEqual([SPAN])
    expect(annotation.annotation_id).toBe('staff-payer')
  })

  it('produces date-kind annotations for date fields', () => {
    const [annotation] = buildClarificationAnnotations(
      context,
      [],
      [{ field: 'service_date', value: '2026-09-01' }],
    )
    expect(annotation.kind).toBe('date')
  })
})
