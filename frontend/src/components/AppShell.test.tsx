import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../mocks/node'
import { renderWithProviders } from '../test/utils'
import { AppShell } from './AppShell'

describe('AppShell', () => {
  it('renders the title and search box', () => {
    renderWithProviders(<AppShell />)
    expect(screen.getByText('yt_summary')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Search…')).toBeInTheDocument()
  })

  it('Fetch pending button starts a fetch-pending job', async () => {
    let called = false
    server.use(http.post('/api/jobs/fetch-pending', async ({ request }) => {
      called = true
      const body = await request.json() as { since?: string; limit?: number }
      expect(body).toEqual({})
      return HttpResponse.json({ id: 'j1', kind: 'fetch-pending', status: 'queued', progress: null, result: null, error: null, created_at: 't0' })
    }))
    renderWithProviders(<AppShell />)
    await userEvent.click(screen.getByText('Fetch pending'))
    await new Promise((r) => setTimeout(r, 20))
    expect(called).toBe(true)
  })
})
