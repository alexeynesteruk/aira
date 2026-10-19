import { useCallback, useEffect, useState } from 'react'

import { getReadiness, type ReadinessResponse } from './api'
import { Readiness, type Availability } from './components/Readiness'
import { RunView } from './components/RunView'
import { DocumentBuild } from './components/DocumentBuild'
import { Upload } from './components/Upload'

function runFromLocation(): string | null {
  return new URLSearchParams(window.location.search).get('run')
}

export function App() {
  const [availability, setAvailability] = useState<Availability>('checking')
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null)
  const [buildId, setBuildId] = useState(() => new URLSearchParams(window.location.search).get('build'))
  const [runId, setRunId] = useState<string | null>(runFromLocation)

  useEffect(() => {
    const controller = new AbortController()
    getReadiness()
      .then((body) => {
        if (controller.signal.aborted) return
        if (body && typeof body.ready === 'boolean') {
          setReadiness(body)
          setAvailability(body.ready ? 'ready' : 'unavailable')
        } else {
          setAvailability('disconnected')
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setAvailability('disconnected')
      })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    const onPop = () => { setRunId(runFromLocation()); setBuildId(new URLSearchParams(window.location.search).get('build')) }
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  const openRun = useCallback((id: string) => {
    window.history.pushState({}, '', `/?run=${id}`)
    setRunId(id)
  }, [])

  const goHome = useCallback(() => {
    window.history.pushState({}, '', '/')
    setRunId(null)
    setBuildId(null)
  }, [])

  return (
    <div className="workspace">
      <header className="topbar">
        <a className="brand" href="/" aria-label="Aira home"><span className="brand-mark">a</span>aira</a>
        <span className="workspace-label">Evidence workspace</span>
      </header>
      <main>
        {buildId ? (
          <>
            <h1>Saved document build</h1>
            <button type="button" onClick={goHome}>New assessment</button>
            <DocumentBuild key={buildId} initialBuildId={buildId} enabled={availability === 'ready'} />
          </>
        ) : runId ? (
          <RunView key={runId} runId={runId} onOpenRun={openRun} onNewRun={goHome} />
        ) : (
          <>
            <p className="eyebrow">Prior authorization</p>
            <h1>Every requirement.<br />Connected to its evidence.</h1>
            <p className="introduction">Review policy requirements alongside the patient chart,
              with clear sources and documentation gaps.</p>
            <Readiness availability={availability} readiness={readiness} />
            <Upload availability={availability} onStarted={openRun} />
          </>
        )}
      </main>
      <footer>Source-based review · Human judgment at every decision</footer>
    </div>
  )
}
