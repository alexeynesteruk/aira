import { useCallback, useEffect, useState } from 'react'

import {
  ApiRequestError,
  getDocument,
  getRun,
  type OperationalError,
  type RunRecord,
  type SourceSpan,
  submitAssessment,
} from '../api'
import {
  APPLICABILITY_LABELS,
  fieldLabel,
  outcomeLabel,
  phaseLabel,
  READINESS_DISCLAIMER,
  runStatusLabel,
} from '../labels'
import { Checklist } from './Checklist'
import { Citations } from './Citations'
import { Clarification } from './Clarification'
import { SourceViewer } from './SourceViewer'

const TERMINAL = new Set(['completed', 'needs_input', 'failed', 'interrupted'])

function ErrorNotice({ error }: { error: OperationalError }) {
  return (
    <div className="error-card" role="alert">
      <p>
        <strong>{error.message}</strong>
      </p>
      <p>
        {error.action} <code>{error.code}</code>
        {error.stage ? ` — ${phaseLabel(error.stage)}` : ''}
      </p>
    </div>
  )
}

function RunDocuments({
  run,
  names,
}: {
  run: RunRecord
  names: Record<string, string>
}) {
  return (
    <p className="note">
      Policy: {names[run.policy_document_id] ?? '…'} · Chart:{' '}
      {names[run.chart_document_id] ?? '…'}
    </p>
  )
}

function RequestSummary({
  run,
  onCite,
}: {
  run: RunRecord
  onCite: (source: SourceSpan) => void
}) {
  const context = run.request_context
  return (
    <section aria-labelledby="request-heading">
      <h3 id="request-heading">Request summary</h3>
      {context ? (
        <dl className="request-fields">
          {(
            [
              'procedure',
              'procedure_code',
              'anatomical_target',
              'laterality',
              'payer',
              'plan',
              'service_date',
              'assessment_cutoff',
            ] as const
          ).map((field) => (
            <div key={field}>
              <dt>{fieldLabel(field)}</dt>
              <dd>{context[field] ?? 'Unresolved'}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="note">Request context remains unresolved.</p>
      )}
      {context?.field_sources.map((item) => (
        <div key={item.field}>
          <p className="note">Sources for {fieldLabel(item.field)}:</p>
          <Citations sources={item.sources} label="Source" onOpen={onCite} />
        </div>
      ))}
      {run.annotations.length > 0 && (
        <ul className="annotations">
          {run.annotations.map((annotation) => (
            <li key={annotation.annotation_id}>
              {fieldLabel(annotation.field)}: {annotation.value}
              {annotation.resolution_reason
                ? ` — resolved: ${annotation.resolution_reason}`
                : ''}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function Provenance({ run }: { run: RunRecord }) {
  const configuration = run.configuration
  return (
    <details className="provenance">
      <summary>Processing provenance</summary>
      <dl>
        <dt>Model</dt>
        <dd>{configuration.model_id}</dd>
        <dt>Provider</dt>
        <dd>{configuration.provider}</dd>
        <dt>Prompts</dt>
        <dd>
          {configuration.prompts
            .map((prompt) => `${prompt.name}@${prompt.version}`)
            .join(', ')}
        </dd>
        <dt>Parser</dt>
        <dd>
          {configuration.parser.name} {configuration.parser.version}
        </dd>
        <dt>SDK</dt>
        <dd>{configuration.sdk_version}</dd>
      </dl>
      {run.usage.length > 0 && (
        <table className="usage">
          <thead>
            <tr>
              <th>Phase</th>
              <th>Attempts</th>
              <th>Duration (ms)</th>
              <th>Input tokens</th>
              <th>Output tokens</th>
              <th>Model</th>
            </tr>
          </thead>
          <tbody>
            {run.usage.map((usage, index) => (
              <tr key={`${usage.phase}-${index}`}>
                <td>{phaseLabel(usage.phase)}</td>
                <td>{usage.attempts}</td>
                <td>{usage.duration_ms}</td>
                <td>{usage.input_tokens ?? '—'}</td>
                <td>{usage.output_tokens ?? '—'}</td>
                <td>{usage.model_id ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </details>
  )
}

function Issues({ run }: { run: RunRecord }) {
  const issues = [
    ...(run.result?.policy?.issues ?? []),
    ...(run.result?.issues ?? []),
    ...(run.result?.policy?.sections.filter(
      (section) => section.disposition === 'unresolved',
    ) ?? []),
  ]
  if (issues.length === 0) return null
  return (
    <section aria-labelledby="issues-heading">
      <h3 id="issues-heading">Issues</h3>
      <ul>
        {issues.map((issue, index) => (
          <li key={'issue_id' in issue ? issue.issue_id : `section-${index}`}>
            {'message' in issue ? (
              <>
                {issue.message}
                {issue.blocks_readiness && <strong> — blocks readiness</strong>}
                {` Action: ${issue.action}.`}
              </>
            ) : (
              <>Unresolved section: {issue.heading}</>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

function ExportLinks({ runId }: { runId: string }) {
  return (
    <p className="exports">
      <a href={`/api/assessments/${runId}/export?format=json`} download>
        Download JSON
      </a>{' '}
      <a href={`/api/assessments/${runId}/export?format=markdown`} download>
        Download Markdown
      </a>
    </p>
  )
}

export function RunView({
  runId,
  onOpenRun,
  onNewRun,
}: {
  runId: string
  onOpenRun: (runId: string) => void
  onNewRun: () => void
}) {
  const [run, setRun] = useState<RunRecord | null>(null)
  const [error, setError] = useState<ApiRequestError | null>(null)
  const [source, setSource] = useState<{ span: SourceSpan; documentName: string } | null>(
    null,
  )
  const [docNames, setDocNames] = useState<Record<string, string>>({})

  useEffect(() => {
    let cancelled = false
    let timerId: number | undefined
    async function load() {
      try {
        const next = await getRun(runId)
        if (cancelled) return
        setRun(next)
        if (!TERMINAL.has(next.status)) {
          timerId = window.setTimeout(() => void load(), 1000)
        }
      } catch (cause) {
        if (!cancelled) {
          setError(
            cause instanceof ApiRequestError
              ? cause
              : new ApiRequestError(0, 'network', 'The run could not be loaded.'),
          )
        }
      }
    }
    void load()
    return () => {
      cancelled = true
      if (timerId !== undefined) window.clearTimeout(timerId)
    }
  }, [runId])

  const openSource = useCallback(
    (span: SourceSpan) => {
      setSource({ span, documentName: docNames[span.document_id] ?? 'Source document' })
    },
    [docNames],
  )

  // Fetch each document's name once per ID — the run object changes on every
  // poll but the bound document IDs do not.
  const documentIds = run
    ? `${run.policy_document_id}|${run.chart_document_id}`
    : ''
  useEffect(() => {
    if (!documentIds) return
    let cancelled = false
    for (const id of documentIds.split('|')) {
      void getDocument(id)
        .then((response) => {
          if (!cancelled) {
            setDocNames((current) => ({ ...current, [id]: response.document.filename }))
          }
        })
        .catch(() => undefined)
    }
    return () => {
      cancelled = true
    }
  }, [documentIds])

  async function startNewRun() {
    if (!run) return
    try {
      const accepted = await submitAssessment({
        policy_document_id: run.policy_document_id,
        chart_document_id: run.chart_document_id,
        parent_run_id: run.run_id,
        annotations: run.annotations,
      })
      onOpenRun(accepted.run_id)
    } catch (cause) {
      setError(
        cause instanceof ApiRequestError
          ? cause
          : new ApiRequestError(0, 'network', 'The new run could not be started.'),
      )
    }
  }

  if (error && !run) {
    return (
      <section>
        <p className="error-note" role="alert">
          {error.message} {error.action ?? ''}
        </p>
        <button type="button" onClick={onNewRun}>
          Back to uploads
        </button>
      </section>
    )
  }
  if (!run) {
    return <p role="status">Loading run {runId}…</p>
  }

  return (
    <div className="run-view">
      <header>
        <h2>
          Assessment run <code>{run.run_id}</code>
        </h2>
        <p>
          <strong>{runStatusLabel(run.status)}</strong>
          {run.phase ? ` — ${phaseLabel(run.phase)}` : ''}
        </p>
        {run.parent_run_id && (
          <p>
            <a href={`/?run=${run.parent_run_id}`} onClick={(event) => {
              event.preventDefault()
              onOpenRun(run.parent_run_id!)
            }}>
              Previous attempt
            </a>
          </p>
        )}
        <RunDocuments run={run} names={docNames} />
        {run.progress.total_pages != null && (
          <p className="note">
            Pages processed: {run.progress.completed_pages} of {run.progress.total_pages}
          </p>
        )}
        {run.progress.completed_phases.length > 0 && (
          <p className="note">
            Completed: {run.progress.completed_phases.map(phaseLabel).join(' · ')}
          </p>
        )}
      </header>

      {(run.status === 'failed' || run.status === 'interrupted') && (
        <>
          {run.error && <ErrorNotice error={run.error} />}
          <button type="button" className="primary" onClick={() => void startNewRun()}>
            Start a new run
          </button>
        </>
      )}

      {run.status === 'needs_input' && (
        <>
          {run.applicability && (
            <>
              <p>{run.applicability.rationale}</p>
              <Citations sources={run.applicability.sources} label="Source" onOpen={openSource} />
            </>
          )}
          <Clarification run={run} onSubmit={onOpenRun} onCite={openSource} />
          <ExportLinks runId={run.run_id} />
        </>
      )}

      {run.status === 'completed' && run.result && (
        <>
          <section className="outcome" aria-label="Assessment outcome" data-outcome={run.result.outcome}>
            <h3>{outcomeLabel(run.result.outcome)}</h3>
            <p className="note">{READINESS_DISCLAIMER}</p>
          </section>
          <section aria-labelledby="applicability-heading">
            <h3 id="applicability-heading">Applicability</h3>
            <p>
              <strong>{APPLICABILITY_LABELS[run.result.applicability.status]}</strong> —{' '}
              {run.result.applicability.rationale}
            </p>
            <Citations
              sources={run.result.applicability.sources}
              label="Source"
              onOpen={openSource}
            />
          </section>
          <RequestSummary run={run} onCite={openSource} />
          {run.result.policy && (
            <section aria-labelledby="checklist-heading">
              <h3 id="checklist-heading">Requirements checklist</h3>
              <p className="note">
                {run.result.policy.title}
                {run.result.policy.revision_date
                  ? ` — revision ${run.result.policy.revision_date}`
                  : ''}
              </p>
              <Checklist
                policy={run.result.policy}
                findings={run.result.findings}
                facts={run.result.facts}
                onCite={openSource}
              />
            </section>
          )}
          <Issues run={run} />
          <Provenance run={run} />
          <ExportLinks runId={run.run_id} />
        </>
      )}

      {source && (
        <SourceViewer
          key={`${source.span.document_id}-${source.span.page}-${source.span.block_id}`}
          source={source.span}
          documentName={source.documentName}
          onClose={() => setSource(null)}
        />
      )}
    </div>
  )
}
