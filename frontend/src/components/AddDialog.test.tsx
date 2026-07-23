import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../mocks/node'
import { renderWithProviders } from '../test/utils'
import { AddDialog } from './AddDialog'

describe('AddDialog', () => {
  it('submitting a URL posts a fetch job', async () => {
    let gotUrl = ''
    server.use(http.post('/api/jobs/fetch', async ({ request }) => {
      gotUrl = (await request.json() as { url: string }).url
      return HttpResponse.json({ id: 'j1', kind: 'fetch', status: 'queued', progress: null, result: null, error: null, created_at: 't0' })
    }))
    renderWithProviders(<AddDialog open onOpenChange={() => {}} />)
    await userEvent.type(screen.getByPlaceholderText(/youtube.com/), 'https://y/abc')
    await userEvent.click(screen.getByText('Fetch'))
    await new Promise((r) => setTimeout(r, 20))
    expect(gotUrl).toBe('https://y/abc')
  })
})
