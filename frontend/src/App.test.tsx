import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { App } from './App'

describe('workspace availability', () => {
  it('explains unavailable processing with its missing prerequisites', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({
        ready: false,
        missing_prerequisites: ['Server configuration needs OPENAI_API_KEY and AIRA_MODEL.'],
        provider: { status: 'unverified' },
      }),
      { status: 503, headers: { 'Content-Type': 'application/json' } },
    )))
    render(<App />)
    expect(screen.getByRole('status')).toHaveTextContent('Checking')
    expect(await screen.findByText('Assessment processing is not available.')).toBeVisible()
    expect(screen.getByText('Server configuration needs OPENAI_API_KEY and AIRA_MODEL.')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Start assessment' })).toBeDisabled()
  })

  it('reports a ready application and labels the fixture provider', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({
        ready: true,
        missing_prerequisites: [],
        provider: {
          status: 'unverified',
          detail: 'Fixture interpreter for browser tests; no live model calls.',
        },
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    )))
    render(<App />)
    expect(await screen.findByText('Ready to assess documents.')).toBeVisible()
    expect(
      screen.getByText('Fixture interpreter for browser tests; no live model calls.'),
    ).toBeVisible()
    expect(screen.getByRole('button', { name: 'Start assessment' })).toBeDisabled()
  })

  it('names an OpenAI-compatible endpoint without calling it direct OpenAI', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({
        ready: true,
        missing_prerequisites: [],
        provider: {
          status: 'unverified',
          backend: 'litellm',
          transport: 'chat_completions',
          model_id: 'proxy-model',
        },
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    )))
    render(<App />)
    expect(await screen.findByText(/OpenAI-compatible API/)).toBeVisible()
    expect(screen.getByText(/proxy-model/)).toBeVisible()
    expect(screen.queryByText(/Direct OpenAI/)).toBeNull()
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
