import { useEffect, useState } from 'react'

type Availability = 'checking' | 'unavailable' | 'disconnected'

export function App() {
  const [availability, setAvailability] = useState<Availability>('checking')

  useEffect(() => {
    const controller = new AbortController()
    fetch('/health/ready', { signal: controller.signal })
      .then(async (response) => {
        const body: unknown = await response.json()
        if (response.status === 503 && body !== null && typeof body === 'object' &&
            'status' in body && body.status === 'not_ready') {
          setAvailability('unavailable')
        } else {
          // A future workflow changes this branch with its contract and browser tests.
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
              {availability === 'unavailable' && 'Assessment processing is not available in this build.'}
              {availability === 'disconnected' && 'Unable to check availability. Check the server connection and refresh.'}
            </p>
            <p className="note">No documents have been processed.</p>
          </div>
        </section>
      </main>
      <footer>Source-based review · Human judgment at every decision</footer>
    </div>
  )
}
