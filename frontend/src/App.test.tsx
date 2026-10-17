import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { App } from './App'

describe('workspace availability', () => {
  it('explains unavailable processing without inventing an assessment', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ status: 'not_ready', reasons: ['Not implemented'], provider_verification: 'unverified' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } },
    )))
    render(<App />)
    expect(screen.getByRole('status')).toHaveTextContent('Checking')
    expect(await screen.findByText('Assessment processing is not available in this build.')).toBeVisible()
    expect(screen.getByText('No documents have been processed.')).toBeVisible()
    expect(screen.queryByRole('button', { name: /assess|approve/i })).not.toBeInTheDocument()
  })

  it.each(['network', 'invalid-json', 'unexpected-status'])(
    'makes a %s failure actionable', async (failure) => {
      const fetchMock = failure === 'network'
        ? vi.fn().mockRejectedValue(new Error('offline'))
        : vi.fn().mockResolvedValue(new Response(failure === 'invalid-json' ? '<html>' : '{}'))
      vi.stubGlobal('fetch', fetchMock)
      render(<App />)
      expect(await screen.findByText(/Check the server connection and refresh/)).toBeVisible()
    },
  )
})
