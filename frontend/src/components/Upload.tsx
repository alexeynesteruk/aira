import { useRef, useState } from 'react'

import {
  ApiRequestError,
  type DocumentRecord,
  submitAssessment,
  uploadDocument,
} from '../api'
import { DocumentBuild } from './DocumentBuild'
import type { Availability } from './Readiness'
import { annotationKind, REQUEST_FIELDS } from '../clarify'
import { fieldLabel } from '../labels'

interface Uploaded {
  record: DocumentRecord
  file: File
}

function DocumentSlot({
  role,
  label,
  onUploaded,
  enabled,
  onBuildSelected,
}: {
  role: 'policy' | 'chart'
  label: string
  enabled: boolean
  onBuildSelected: (id: string | undefined) => void
  onUploaded: (uploaded: Uploaded | null) => void
}) {
  const input = useRef<HTMLInputElement>(null)
  const [uploaded, setUploaded] = useState<Uploaded | null>(null)
  const [error, setError] = useState<ApiRequestError | null>(null)
  const [busy, setBusy] = useState(false)

  async function upload(file: File) {
    setBusy(true)
    setError(null)
    setUploaded(null)
    onUploaded(null)
    onBuildSelected(undefined)
    try {
      const response = await uploadDocument(file, role)
      const next = { record: response.document, file }
      setUploaded(next)
      onUploaded(next)
    } catch (cause) {
      setError(cause instanceof ApiRequestError ? cause : new ApiRequestError(0, 'network', 'The upload failed.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <fieldset className="upload-slot">
      <legend>{label}</legend>
      <input
        ref={input}
        type="file"
        accept="application/pdf"
        aria-label={label}
        onChange={(event) => {
          const file = event.target.files?.[0]
          if (file) void upload(file)
        }}
      />
      {busy && <p className="note">Uploading…</p>}
      {uploaded && (
        <p className="note" role="note">
          {uploaded.record.filename} — {uploaded.record.page_count} pages, SHA{' '}
          <code>{uploaded.record.sha256.slice(0, 12)}</code>
        </p>
      )}
      {uploaded && <DocumentBuild key={uploaded.record.document_id} documentId={uploaded.record.document_id} enabled={enabled} onSelected={onBuildSelected} />}
      {error && (
        <p className="error-note" role="alert">
          {error.message}
          {error.action ? ` ${error.action}` : ''}
        </p>
      )}
    </fieldset>
  )
}

export function Upload({
  availability,
  onStarted,
}: {
  availability: Availability
  onStarted: (runId: string) => void
}) {
  const [policy, setPolicy] = useState<Uploaded | null>(null)
  const [chart, setChart] = useState<Uploaded | null>(null)
  const [policyBuild, setPolicyBuild] = useState<string>()
  const [chartBuild, setChartBuild] = useState<string>()
  const [fields, setFields] = useState<Record<string, string>>({})
  const [error, setError] = useState<ApiRequestError | null>(null)
  const [busy, setBusy] = useState(false)

  const ready = availability === 'ready'
  const canStart = ready && policy !== null && chart !== null && !busy

  async function start() {
    if (!policy || !chart) return
    setBusy(true)
    setError(null)
    try {
      const annotations = REQUEST_FIELDS.filter((field) => fields[field]?.trim()).map(
        (field) => ({
          kind: annotationKind(field),
          annotation_id: `staff-${field}`,
          field,
          value: fields[field].trim(),
          created_at: new Date().toISOString(),
        }),
      )
      const accepted = await submitAssessment({
        policy_document_id: policy.record.document_id,
        chart_document_id: chart.record.document_id,
        annotations,
        policy_build_id: policyBuild,
        chart_build_id: chartBuild,
      })
      onStarted(accepted.run_id)
    } catch (cause) {
      setError(
        cause instanceof ApiRequestError
          ? cause
          : new ApiRequestError(0, 'network', 'Could not start the assessment.'),
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <section aria-labelledby="upload-heading">
      <h2 id="upload-heading">New assessment</h2>
      <div className="upload-grid">
        <DocumentSlot role="policy" label="Policy PDF" onUploaded={setPolicy} enabled={ready} onBuildSelected={setPolicyBuild} />
        <DocumentSlot role="chart" label="Chart PDF" onUploaded={setChart} enabled={ready} onBuildSelected={setChartBuild} />
      </div>
      <fieldset className="metadata-fields">
        <legend>Request metadata (optional)</legend>
        <div className="metadata-grid">
          {REQUEST_FIELDS.map((field) => (
            <label key={field}>
              {fieldLabel(field)}
              <input
                type={annotationKind(field) === 'date' ? 'date' : 'text'}
                value={fields[field] ?? ''}
                onChange={(event) =>
                  setFields((current) => ({ ...current, [field]: event.target.value }))
                }
              />
            </label>
          ))}
        </div>
      </fieldset>
      <button
        type="button"
        className="primary"
        disabled={!canStart}
        onClick={() => void start()}
      >
        Start assessment
      </button>
      {!ready && (
        <p className="note">
          {availability === 'checking'
            ? 'Checking whether assessments can start…'
            : 'Starting an assessment requires the configured prerequisites.'}
        </p>
      )}
      {error && (
        <p className="error-note" role="alert">
          {error.message}
          {error.action ? ` ${error.action}` : ''}
        </p>
      )}
    </section>
  )
}
