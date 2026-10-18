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

function verificationLine(readiness: ReadinessResponse | null): string | null {
  const provider = readiness?.provider
  if (!provider) return null
  const when = provider.checked_at
    ? new Date(provider.checked_at).toLocaleString()
    : null
  switch (provider.status) {
    case 'verified':
      return `Model access verified for ${provider.model_id} at ${when}.`
    case 'failed':
      return `Last model access check failed at ${when}: ${provider.detail}`
    default:
      return 'Model access not yet verified — run the preflight (see README).'
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
  const verification = verificationLine(readiness)
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
        {verification && <p className="provider-note">{verification}</p>}
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
