import { useEffect, useState } from 'react'

import { ApiRequestError, getPage, type PageResponse, type SourceSpan } from '../api'

export function BlockText({
  text,
  start,
  end,
}: {
  text: string
  start: number
  end: number
}) {
  // Backend SourceSpan offsets are Unicode code points; slice by code point
  // so astral characters cannot shift the highlight.
  const characters = Array.from(text)
  return (
    <p className="cited-block">
      {characters.slice(0, start).join('')}
      <mark>{characters.slice(start, end).join('')}</mark>
      {characters.slice(end).join('')}
    </p>
  )
}

export function SourceViewer({
  source,
  documentName,
  onClose,
}: {
  source: SourceSpan
  documentName: string
  onClose: () => void
}) {
  const [page, setPage] = useState<PageResponse | null>(null)
  const [error, setError] = useState<ApiRequestError | null>(null)

  // The parent remounts this viewer per source via `key`, so fresh state is
  // guaranteed for each new citation.
  useEffect(() => {
    let cancelled = false
    getPage(source.document_id, source.page, source.extraction_id)
      .then((response) => {
        if (!cancelled) setPage(response)
      })
      .catch((cause) => {
        if (!cancelled) {
          setError(
            cause instanceof ApiRequestError
              ? cause
              : new ApiRequestError(0, 'network', 'The page could not be loaded.'),
          )
        }
      })
    return () => {
      cancelled = true
    }
  }, [source.document_id, source.page, source.extraction_id])

  return (
    <aside className="source-viewer" role="complementary" aria-label="Source viewer">
      <header>
        <h3>
          {documentName} — Page {source.page}
        </h3>
        <button type="button" onClick={onClose} aria-label="Close source viewer">
          Close
        </button>
      </header>
      <p className="note">
        Extraction <code>{source.extraction_id}</code>
      </p>
      <a
        href={`/api/documents/${source.document_id}/file#page=${source.page}`}
        target="_blank"
        rel="noreferrer"
      >
        Open original PDF at page {source.page}
      </a>
      {error && (
        <p className="error-note" role="alert">
          {error.message}
        </p>
      )}
      {page && (
        <ol className="block-list">
          {page.page.blocks.map((block) => (
            <li key={block.block_id} data-block-id={block.block_id}>
              {block.block_id === source.block_id ? (
                <BlockText text={block.text} start={source.start} end={source.end} />
              ) : (
                <p>{block.text}</p>
              )}
            </li>
          ))}
        </ol>
      )}
    </aside>
  )
}
