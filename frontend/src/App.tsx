import { useEffect, useState } from 'react'

type Availability = 'checking' | 'unavailable' | 'ready' | 'disconnected'

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

export function App() {
  const [availability, setAvailability] = useState<Availability>('checking')
  const [missing, setMissing] = useState<string[]>([])

  useEffect(() => {
    const controller = new AbortController()
    fetch('/health/ready', { signal: controller.signal })
      .then(async (response) => {
        const body: unknown = await response.json()
        if (body !== null && typeof body === 'object' && 'ready' in body) {
          if (body.ready === false && response.status === 503) {
            const record = body as { missing_prerequisites?: unknown }
            setMissing(stringList(record.missing_prerequisites))
            setAvailability('unavailable')
          } else if (body.ready === true && response.status === 200) {
            setAvailability('ready')
          } else {
            setAvailability('disconnected')
          }
        } else {
          setAvailability('disconnected')
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setAvailability('disconnected')
      })
    return () => controller.abort()
  }, [])

  return (
    <div className="workspace">
      <header className="topbar">
        <a className="brand" href="/" aria-label="Aira home"><span className="brand-mark">a</span>aira</a>
        <span className="workspace-label">Evidence workspace</span>
      </header>
      <main>
        <p className="eyebrow">Prior authorization</p>
        <h1>Every requirement.<br />Connected to its evidence.</h1>
        <p className="introduction">Review policy requirements alongside the patient chart,
          with clear sources and documentation gaps.</p>
        <section className="setup-card" aria-labelledby="availability-heading">
          <div className="document-icon" aria-hidden="true">↗</div>
          <div>
            <h2 id="availability-heading">Your assessment workspace</h2>
            <p role="status" aria-live="polite">
              {availability === 'checking' && 'Checking assessment availability…'}
              {availability === 'unavailable' && 'Assessment processing is not available.'}
              {availability === 'ready' && 'Ready to assess documents.'}
              {availability === 'disconnected' && 'Unable to check availability. Check the server connection and refresh.'}
            </p>
            {availability === 'unavailable' && missing.length > 0 && (
              <ul className="missing-prerequisites">
                {missing.map((item) => <li key={item}>{item}</li>)}
              </ul>
            )}
            <p className="note">No documents have been processed.</p>
          </div>
        </section>
      </main>
      <footer>Source-based review · Human judgment at every decision</footer>
    </div>
  )
}
