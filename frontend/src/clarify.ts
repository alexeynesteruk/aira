/**
 * Build staff annotations from clarification form input — pure and testable.
 *
 * Unresolved fields with extracted field_sources produce conflict-resolution
 * annotations (original_sources + required resolution reason); fields without
 * sources produce plain annotations. Policy-scope fields are not resolvable
 * from this form and are surfaced separately by the view.
 */

import type { FieldSources, MetadataAnnotation, RequestContext } from './api'

export const REQUEST_FIELDS = [
  'procedure',
  'procedure_code',
  'anatomical_target',
  'laterality',
  'payer',
  'plan',
  'service_date',
  'assessment_cutoff',
] as const

export type RequestField = (typeof REQUEST_FIELDS)[number]

const DATE_FIELDS: ReadonlySet<string> = new Set(['service_date', 'assessment_cutoff'])

export function isRequestField(field: string): field is RequestField {
  return (REQUEST_FIELDS as readonly string[]).includes(field)
}

export function annotationKind(field: string): 'text' | 'date' {
  return DATE_FIELDS.has(field) ? 'date' : 'text'
}

export function fieldSources(context: RequestContext | null | undefined, field: string): FieldSources | undefined {
  return context?.field_sources.find((item) => item.field === field)
}

export interface ClarificationEntry {
  field: string
  value: string
  reason?: string
}

/**
 * Returns the annotations to submit for a clarification run: preserved prior
 * annotations (same-field ones replaced) plus one annotation per entry.
 * Throws when a sourced field is resolved without a resolution reason.
 */
export function buildClarificationAnnotations(
  context: RequestContext | null | undefined,
  existing: MetadataAnnotation[],
  entries: ClarificationEntry[],
  createdAt: string = new Date().toISOString(),
): MetadataAnnotation[] {
  const replaced = new Set(entries.map((entry) => entry.field))
  const annotations: MetadataAnnotation[] = existing.filter(
    (annotation) => !replaced.has(annotation.field),
  )
  for (const entry of entries) {
    const sources = fieldSources(context, entry.field)?.sources ?? []
    if (sources.length > 0 && !entry.reason?.trim()) {
      throw new Error('A resolution reason is required when resolving a documented value.')
    }
    annotations.push({
      kind: annotationKind(entry.field),
      annotation_id: `staff-${entry.field}`,
      field: entry.field,
      value: entry.value.trim(),
      created_at: createdAt,
      ...(sources.length > 0
        ? {
            original_sources: sources,
            resolves_conflict: true,
            resolution_reason: entry.reason!.trim(),
          }
        : {}),
    })
  }
  return annotations
}
