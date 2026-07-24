import { describe, it, expect } from 'vitest'
import { screen, waitFor, fireEvent } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '../mocks/node'
import { renderWithProviders } from '../test/utils'
import { HistoryView } from './HistoryView'
import type { Job } from '../api/types'

describe('HistoryView', () => {
  it('lists videos grouped by day and shows a summary button/badge', async () => {
    renderWithProviders(<HistoryView />)
    expect(await screen.findByText('First Video')).toBeInTheDocument()
    expect(screen.getByText(/2026-07-22|Today/)).toBeInTheDocument()
    // Already-summarized video shows a badge, not a button.
    expect(screen.getByText('summarized')).toBeInTheDocument()
    // Transcribed-but-not-summarized video gets a Summarize button.
    expect(screen.getByRole('button', { name: /^summarize$/i })).toBeInTheDocument()
  })

  it('summarize posts a job carrying the video_id, which then shows as a badge', async () => {
    let activeJob: Job | null = null
    server.use(
      http.get('/api/jobs', () => HttpResponse.json(activeJob ? [activeJob] : [])),
      http.post('/api/jobs/summarize', async ({ request }) => {
        const body = (await request.json()) as { video_id: string }
        activeJob = {
          id: 'j1', kind: 'summarize', status: 'queued', progress: null, result: null,
          error: null, created_at: 't0', video_id: body.video_id,
        }
        return HttpResponse.json(activeJob)
      }),
    )
    renderWithProviders(<HistoryView />)
    const btn = await screen.findByRole('button', { name: /^summarize$/i })
    fireEvent.click(btn)
    await waitFor(() => expect(screen.getByText(/summarizing/i)).toBeInTheDocument())
  })

  it('Refresh triggers a discover job', async () => {
    let called = false
    server.use(
      http.post('/api/jobs/discover', async ({ request }) => {
        called = true
        await request.json()
        return HttpResponse.json({
          id: 'j2', kind: 'discover', status: 'queued', progress: null, result: null,
          error: null, created_at: 't0', video_id: null,
        })
      }),
    )
    renderWithProviders(<HistoryView />)
    await screen.findByText('First Video')
    fireEvent.click(screen.getByRole('button', { name: /refresh/i }))
    await waitFor(() => expect(called).toBe(true))
  })
})
