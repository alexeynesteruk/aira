import { useState } from 'react'

import {
  ApiRequestError,
  type RunRecord,
  submitAssessment,
} from '../api'
import {
  buildClarificationAnnotations,
  fieldSources,
  isRequestField,
  type ClarificationEntry,
} from '../clarify'
import { fieldLabel } from '../labels'
import { Citations } from './Citations'
import type { SourceSpan } from '../api'

/**
 * Staff clarification for unresolved request/policy-scope fields. Sourced
 * fields require a resolution reason; policy-scope fields are listed for
 * review only and cannot be answered here.
 */
export function Clarification({
  run,
  onSubmit,
  onCite,
}: {
  run: RunRecord
  onSubmit: (runId: string) => void
  onCite: (source: SourceSpan) => void
}) {
  const unresolved = run.applicability?.unresolved_fields ?? []
  const requestFields = unresolved.filter(isRequestField)
  const scopeFields = unresolved.filter((field) => !isRequestField(field))
  const [values, setValues] = useState<Record<string, string>>({})
  const [reasons, setReasons] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  function needsReason(field: string): boolean {
    return (fieldSources(run.request_context, field)?.sources.length ?? 0) > 0
  }

  function canSubmit(): boolean {
    if (busy || requestFields.length === 0) return false
    return requestFields.every(
      (field) =>
        values[field]?.trim() && (!needsReason(field) || reasons[field]?.trim()),
    )
  }

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      const entries: ClarificationEntry[] = requestFields.map((field) => ({
        field,
        value: values[field],
        reason: reasons[field],
      }))
      const annotations = buildClarificationAnnotations(
        run.request_context,
        run.annotations,
        entries,
      )
      const accepted = await submitAssessment({
        policy_document_id: run.policy_document_id,
        chart_document_id: run.chart_document_id,
        parent_run_id: run.run_id,
        annotations,
      })
      onSubmit(accepted.run_id)
    } catch (cause) {
      setError(
        cause instanceof ApiRequestError
          ? `${cause.message}${cause.action ? ` ${cause.action}` : ''}`
          : cause instanceof Error
            ? cause.message
            : 'The clarification could not be submitted.',
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="clarification" aria-labelledby="clarify-heading">
      <h3 id="clarify-heading">Staff clarification</h3>
      {scopeFields.length > 0 && (
        <ul className="scope-fields">
          {scopeFields.map((field) => (
            <li key={field}>
              {fieldLabel(field)} — needs staff review; it cannot be answered from this form.
            </li>
          ))}
        </ul>
      )}
      {requestFields.map((field) => {
        const sources = fieldSources(run.request_context, field)?.sources ?? []
        return (
          <fieldset key={field} className="clarify-field">
            <legend>{fieldLabel(field)}</legend>
            {sources.length > 0 && (
              <>
                <p className="note">Documented value found in the sources:</p>
                <Citations sources={sources} label="Source" onOpen={onCite} />
              </>
            )}
            <label>
              Value
              <input
                type="text"
                value={values[field] ?? ''}
                onChange={(event) =>
                  setValues((current) => ({ ...current, [field]: event.target.value }))
                }
              />
            </label>
            {sources.length > 0 && (
              <label>
                Resolution reason
                <input
                  type="text"
                  value={reasons[field] ?? ''}
                  onChange={(event) =>
                    setReasons((current) => ({ ...current, [field]: event.target.value }))
                  }
                />
              </label>
            )}
          </fieldset>
        )
      })}
      <button type="button" className="primary" disabled={!canSubmit()} onClick={() => void submit()}>
        Submit clarification
      </button>
      {error && (
        <p className="error-note" role="alert">
          {error}
        </p>
      )}
    </section>
  )
}
