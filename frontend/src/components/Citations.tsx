import type { SourceSpan } from '../api'

/** A clickable citation chip; opening the source viewer is the parent's job. */
export function Citation({
  source,
  label,
  onOpen,
}: {
  source: SourceSpan
  label: string
  onOpen: (source: SourceSpan) => void
}) {
  return (
    <button
      type="button"
      className="citation"
      onClick={() => onOpen(source)}
      title={source.excerpt}
    >
      {label}, page {source.page}
    </button>
  )
}

export function Citations({
  sources,
  label,
  onOpen,
}: {
  sources: SourceSpan[]
  label: string
  onOpen: (source: SourceSpan) => void
}) {
  if (sources.length === 0) return null
  return (
    <p className="citations">
      {sources.map((source, index) => (
        <Citation
          key={`${source.block_id}-${source.start}-${index}`}
          source={source}
          label={label}
          onOpen={onOpen}
        />
      ))}
    </p>
  )
}
