import { render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Policy, SourceSpan } from '../api'
import { Checklist } from './Checklist'

const SPAN: SourceSpan = {
  block_id: 'block-1',
  document_id: 'doc-1',
  document_sha256: 'a'.repeat(64),
  extraction_id: 'ext-1',
  page: 3,
  start: 0,
  end: 10,
  excerpt: 'cited wording',
}

const CHART_SPAN: SourceSpan = { ...SPAN, document_id: 'doc-2', block_id: 'block-9' }

const policy: Policy = {
  policy_id: 'policy-1',
  document_id: 'doc-1',
  document_sha256: 'a'.repeat(64),
  title: 'Fixture policy',
  scope_summary: 'scope',
  criteria: [
    { criterion_id: 'crit-a', wording: 'Criterion A wording', interpretation: 'interp A', sources: [SPAN], context: [] },
    { criterion_id: 'crit-b', wording: 'Criterion B wording', interpretation: 'interp B', sources: [SPAN], context: [] },
    { criterion_id: 'crit-c', wording: 'Criterion C wording', interpretation: 'interp C', sources: [SPAN], context: [] },
  ],
  nodes: [
    { kind: 'all', node_id: 'root', children: ['node-a', 'group-any'], sources: [SPAN] },
    { kind: 'criterion', node_id: 'node-a', criterion_id: 'crit-a', sources: [SPAN] },
    { kind: 'any', node_id: 'group-any', children: ['node-b', 'node-c'], sources: [SPAN] },
    { kind: 'criterion', node_id: 'node-b', criterion_id: 'crit-b', sources: [SPAN] },
    { kind: 'criterion', node_id: 'node-c', criterion_id: 'crit-c', sources: [SPAN] },
  ],
  root_id: 'root',
  sections: [
    {
      section_id: 'requirements',
      heading: 'Requirements',
      sources: [SPAN],
      disposition: 'requirements',
      criterion_ids: ['crit-a', 'crit-b', 'crit-c'],
      explanation: 'explanation',
    },
  ],
  issues: [],
}

const findings = [
  { criterion_id: 'crit-a', status: 'met' as const, rationale: 'found', evidence: [], unresolved_reasons: [] },
  { criterion_id: 'crit-b', status: 'missing' as const, rationale: 'absent', evidence: [], unresolved_reasons: ['no documentation'] },
  { criterion_id: 'crit-c', status: 'needs_review' as const, rationale: 'unclear', evidence: [], unresolved_reasons: [] },
]

describe('Checklist', () => {
  it('renders all/any nesting in node order from the root', () => {
    render(<Checklist policy={policy} findings={findings} facts={[]} onCite={vi.fn()} />)
    expect(screen.getByText('All of the following')).toBeVisible()
    expect(screen.getByText('Any one of the following')).toBeVisible()
    const root = screen.getByText('All of the following').closest('section')!
    const ordered = [...root.querySelectorAll('article code')].map((node) => node.textContent)
    expect(ordered).toEqual(['crit-a', 'crit-b', 'crit-c'])
  })

  it('a missing finding shows Documentation needed and no chart citation', () => {
    render(<Checklist policy={policy} findings={findings} facts={[]} onCite={vi.fn()} />)
    const card = screen.getByLabelText('Finding: crit-b')
    expect(within(card).getByText('Missing')).toBeVisible()
    expect(within(card).getByText('Documentation needed')).toBeVisible()
    expect(within(card).getByText('no documentation')).toBeVisible()
    // Policy citation present, but no chart citations for a missing finding.
    expect(within(card).getAllByRole('button', { name: /Policy, page 3/ }).length).toBe(1)
    expect(within(card).queryByRole('button', { name: /Chart/ })).not.toBeInTheDocument()
  })

  it('lists supporting evidence facts with chart citations', () => {
    const facts = [
      {
        fact_id: 'fact-1',
        proposition: 'Documented heart rate.',
        sources: [CHART_SPAN],
        polarity: 'affirmed',
        provenance: 'direct',
      },
    ]
    const met = [
      {
        criterion_id: 'crit-a',
        status: 'met' as const,
        rationale: 'found',
        evidence: [{ fact_id: 'fact-1', relation: 'supporting' as const }],
        unresolved_reasons: [],
      },
      findings[1],
      findings[2],
    ]
    render(<Checklist policy={policy} findings={met} facts={facts} onCite={vi.fn()} />)
    const card = screen.getByLabelText('Finding: crit-a')
    expect(within(card).getByText(/Supporting:/)).toBeVisible()
    expect(within(card).getByText('Documented heart rate.')).toBeVisible()
    expect(within(card).getByRole('button', { name: /Chart, page 3/ })).toBeVisible()
  })
})
