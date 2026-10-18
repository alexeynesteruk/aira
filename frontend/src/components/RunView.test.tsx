import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { RunRecord } from '../api'
import { RunView } from './RunView'

function run(overrides: Partial<RunRecord>): RunRecord {
  return {
    run_id: 'run-1',
    policy_document_id: 'doc-policy',
    chart_document_id: 'doc-chart',
    policy_sha256: 'a'.repeat(64),
    chart_sha256: 'b'.repeat(64),
    input_fingerprint: 'c'.repeat(64),
    configuration: {
      parser: { name: 'pdfplumber', version: '0.11.9' },
      parser_configuration_sha256: 'd'.repeat(64),
      prompts: [{ name: 'scope', version: '1' }],
      provider: 'openai',
      model_id: 'fixture-model',
      sdk_version: 'fixture',
      inference: { max_output_tokens: 4096 },
    },
    annotations: [],
    created_at: '2026-10-18T10:00:00Z',
    updated_at: '2026-10-18T10:01:00Z',
    status: 'completed',
    progress: { completed_phases: [], completed_pages: 0 },
    usage: [],
    ...overrides,
  }
}

function stubRun(body: RunRecord) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      if (url.startsWith('/api/assessments/')) {
        return Promise.resolve(
          new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } }),
        )
      }
      return Promise.resolve(
        new Response(JSON.stringify({ document: { filename: 'doc.pdf' }, extractions: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    }),
  )
}

describe('RunView', () => {
  it('shows the failure action and a Start a new run button for failed runs', async () => {
    stubRun(
      run({
        status: 'failed',
        phase: 'extracting',
        error: {
          code: 'extraction_failed',
          message: 'The chart has no extractable text.',
          retryable: false,
          action: 'Upload a text-based PDF or a corrected scan.',
          stage: 'extracting',
        },
      }),
    )
    render(<RunView runId="run-1" onOpenRun={vi.fn()} onNewRun={vi.fn()} />)
    expect(await screen.findByText('The chart has no extractable text.')).toBeVisible()
    expect(screen.getByText(/Upload a text-based PDF or a corrected scan/)).toBeVisible()
    expect(screen.getByRole('button', { name: 'Start a new run' })).toBeVisible()
    expect(screen.queryByText('Documentation readiness only — not an insurer decision.')).not.toBeInTheDocument()
  })

  it('never labels a review_required outcome as satisfied', async () => {
    stubRun(
      run({
        status: 'completed',
        result: {
          outcome: 'review_required',
          applicability: {
            status: 'applicable',
            rationale: 'Scope applies.',
            sources: [],
            unresolved_fields: [],
          },
          facts: [],
          findings: [],
          issues: [],
        },
      }),
    )
    render(<RunView runId="run-1" onOpenRun={vi.fn()} onNewRun={vi.fn()} />)
    const outcome = await screen.findByRole('heading', { name: 'Review required' })
    expect(outcome).toBeVisible()
    expect(screen.queryByText(/satisfied/i)).not.toBeInTheDocument()
    expect(screen.getByText('Documentation readiness only — not an insurer decision.')).toBeVisible()
  })
})

describe('ErrorNotice', () => {
  it('lists the failing pages of the bound document', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            document: {
              document_id: 'doc-1',
              filename: 'scan.pdf',
              page_count: 3,
              sha256: 'a'.repeat(64),
              role: 'chart',
              byte_count: 10,
              created_at: '2026-10-18T10:00:00Z',
            },
            extractions: [
              {
                extraction_id: 'ext-1',
                pages: [
                  { page: 1, quality: 'needs_ocr', blocks: [], issues: ['raster scan'] },
                  { page: 2, quality: 'usable', blocks: [], issues: [] },
                ],
              },
            ],
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    )
    const { ErrorNotice } = await import('./RunView')
    render(
      <ErrorNotice
        error={{
          code: 'extraction_failed',
          message: 'The complete document is not usable for native-text assessment.',
          retryable: false,
          action: 'Upload a complete native-text PDF.',
          stage: 'extracting',
          document_id: 'doc-1',
          page: 1,
        }}
      />,
    )
    expect(await screen.findByText('Document: scan.pdf')).toBeVisible()
    expect(screen.getByText(/Page 1 — Needs OCR/)).toBeVisible()
    expect(screen.getByText(/— page 1/)).toBeVisible()
    expect(screen.queryByText(/Page 2/)).not.toBeInTheDocument()
  })
})
