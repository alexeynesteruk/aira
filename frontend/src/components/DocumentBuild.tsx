import { useEffect, useState } from 'react'

import { actOnBuild, getBuild, listBuilds, startBuild, type BuildRecord, type SourceSpan } from '../api'
import { SourceViewer } from './SourceViewer'

export function DocumentBuild({ documentId, initialBuildId, enabled = true, onSelected }: {
  documentId?: string
  initialBuildId?: string
  enabled?: boolean
  onSelected?: (id: string | undefined) => void
}) {
  const [build, setBuild] = useState<BuildRecord | null>(null)
  const [versions, setVersions] = useState<BuildRecord[]>([])
  const [selected, setSelected] = useState(initialBuildId ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [source, setSource] = useState<SourceSpan | null>(null)
  const [showAll, setShowAll] = useState(false)
  const active = build?.status === 'queued' || build?.status === 'running'
  const id = documentId ?? build?.document_id

  useEffect(() => {
    if (!id) return
    let cancelled = false
    listBuilds(id).then((items) => { if (!cancelled) setVersions(items.builds) })
      .catch((cause: unknown) => { if (!cancelled) setError(String(cause)) })
    return () => { cancelled = true }
  }, [id, build?.status, selected])

  useEffect(() => {
    if (!selected) return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout>
    async function poll() {
      try {
        const next = await getBuild(selected)
        if (cancelled) return
        setBuild(next)
        if (next.status === 'running' || next.status === 'queued') timer = setTimeout(() => void poll(), 700)
      } catch (cause) {
        if (!cancelled) setError(String(cause))
      }
    }
    void poll()
    return () => { cancelled = true; clearTimeout(timer) }
  }, [selected])

  useEffect(() => {
    onSelected?.(build?.status === 'completed' && build.review_status !== 'rejected' ? build.build_id : undefined)
  }, [build, onSelected])

  async function action(kind: 'prepare' | 'retry' | 'rebuild' | 'approve' | 'reject') {
    if (!id) return
    setBusy(true)
    setError('')
    try {
      const next = kind === 'prepare' ? await startBuild(id) : await actOnBuild(build!.build_id, kind)
      setBuild(next)
      setSelected(next.build_id)
    } catch (cause) { setError(String(cause)) }
    finally { setBusy(false) }
  }

  return <section className="document-build" aria-label="Document preparation">
    <p className="note">Prepare this document independently. Assessments reuse its saved version.</p>
    {documentId && <button type="button" disabled={!enabled || busy || active} onClick={() => void action('prepare')}>Prepare document</button>}
    {versions.length > 0 && <label>Saved version
      <select aria-label="Saved version" value={selected} disabled={busy || active} onChange={(event) => {
        setBuild(null); setSelected(event.target.value); onSelected?.(undefined)
      }}>
        <option value="">Choose a saved build</option>
        {versions.map((item) => <option key={item.build_id} value={item.build_id}>{item.build_id} · {item.status} · {item.review_status}</option>)}
      </select>
    </label>}
    {error && <p role="alert" className="error-note">{error}</p>}
    {build && <>
      <p role="status">Build {build.status} · {build.phase.replaceAll('_', ' ')} · {build.completed_sections}/{build.total_sections} sections</p>
      <p className="note"><code>{build.build_id}</code> · {build.review_status}{build.cached ? ' · Reused saved extraction (no new inference)' : ''}</p>
      <p><a href={`/?build=${build.build_id}`}>Open saved build</a>{' · '}<a href={`/api/builds/${build.build_id}`} target="_blank" rel="noreferrer">Build JSON</a>{' · '}<a href={`/api/documents/${build.document_id}/file`} target="_blank" rel="noreferrer">Original PDF</a></p>
      {build.parent_build_id && <p>Previous attempt: <a href={`/?build=${build.parent_build_id}`}>{build.parent_build_id}</a></p>}
      <p className="note">Model: {build.configuration.model_id} · Source SHA <code>{build.document_sha256}</code></p>
      {build.error && <p role="alert" className="error-note">{build.error.message} {build.error.action}</p>}
      {build.status === 'completed' && <>
        <p>{build.policy?.criteria.length ?? build.chart?.facts.length ?? 0} {build.role === 'policy' ? 'requirements' : 'chart facts'} saved. Human review: {build.review_status}.</p>
        <p className="note">Source coverage records processing; it does not certify that every rule was interpreted correctly. Approval retains all interpretation blockers.</p>
        <button type="button" disabled={busy || !enabled} onClick={() => void action('approve')}>Approve build</button>{' '}
        <button type="button" disabled={busy || !enabled} onClick={() => void action('reject')}>Reject build</button>{' '}
      </>}
      {(build.status === 'failed' || build.status === 'interrupted') && <button type="button" disabled={busy || !enabled} onClick={() => void action('retry')}>Retry build</button>}
      {!active && <button type="button" disabled={busy || !enabled} onClick={() => void action('rebuild')}>Rebuild new version</button>}
      {build.steps.length > 0 && <details><summary>Extraction steps ({build.steps.length})</summary><ol>{build.steps.map((step, index) => <li key={index}>
        <a href={`/api/builds/${build.build_id}/steps/${step.checkpoint_key}`} target="_blank" rel="noreferrer">{step.name}</a>{step.cached ? ' · Reused checkpoint' : ''}
      </li>)}</ol></details>}
      {build.issues.length > 0 && <details open><summary>Interpretation issues ({build.issues.length})</summary><ul>{build.issues.map((issue, index) => <li key={index}>{issue}</li>)}</ul></details>}
      {build.policy && <details><summary>Compiled rule set and procedure paths</summary><pre className="build-json">{JSON.stringify(build.policy, null, 2)}</pre></details>}
      {build.chart && <details><summary>Sourced chart facts</summary><pre className="build-json">{JSON.stringify(build.chart, null, 2)}</pre></details>}
      {build.coverage.length > 0 && <details><summary>Source coverage ({build.coverage.length} blocks)</summary>
        <ol>{(showAll ? build.coverage : build.coverage.slice(0, 30)).map((entry) => <li key={entry.unit_id}>
          <button type="button" onClick={() => setSource(entry.source)}>Page {entry.source.page} · {entry.unit_id}</button>{' '}
          {entry.disposition} · {entry.audited ? 'audited' : 'pending'} — {entry.explanation}
        </li>)}</ol>
        {!showAll && build.coverage.length > 30 && <button type="button" onClick={() => setShowAll(true)}>Show all coverage</button>}
      </details>}
      {source && <SourceViewer key={`${source.extraction_id}:${source.block_id}`} source={source} documentName="Prepared document" onClose={() => setSource(null)} />}
    </>}
  </section>
}
