import type { ReadinessResponse } from '../api'

export type Availability = 'checking' | 'unavailable' | 'ready' | 'disconnected'

function readinessMessage(availability: Availability): string {
  switch (availability) {
    case 'checking':
      return 'Checking assessment availability…'
    case 'unavailable':
      return 'Assessment processing is not available.'
    case 'ready':
      return 'Ready to assess documents.'
    case 'disconnected':
      return 'Unable to check availability. Check the server connection and refresh.'
  }
}

export function Readiness({
  availability,
  readiness,
}: {
  availability: Availability
  readiness: ReadinessResponse | null
}) {
  const missing = readiness?.missing_prerequisites ?? []
  const detail = readiness?.provider?.detail
  return (
    <section className="setup-card" aria-labelledby="availability-heading">
      <div className="document-icon" aria-hidden="true">↗</div>
      <div>
        <h2 id="availability-heading">Your assessment workspace</h2>
        <p role="status" aria-live="polite">{readinessMessage(availability)}</p>
        {availability === 'unavailable' && missing.length > 0 && (
          <ul className="missing-prerequisites">
            {missing.map((item) => <li key={item}>{item}</li>)}
          </ul>
        )}
        {detail && <p className="provider-note">{detail}</p>}
        <p className="note">
          {availability === 'unavailable'
            ? 'You can still review uploads; starting an assessment stays disabled.'
            : 'Upload a policy and a chart to begin.'}
        </p>
      </div>
    </section>
  )
}
