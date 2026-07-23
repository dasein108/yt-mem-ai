import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../mocks/node'
import { renderWithProviders } from '../test/utils'
import { Routes, Route } from 'react-router-dom'
import { VideoDetail } from './VideoDetail'

const renderAt = (id: string) =>
  renderWithProviders(<Routes><Route path="/videos/:id" element={<VideoDetail />} /></Routes>, { route: `/videos/${id}` })

describe('VideoDetail', () => {
  it('shows summary, highlights, Q&A', async () => {
    renderAt('v1')
    expect(await screen.findByText('A summary.')).toBeInTheDocument()
    expect(screen.getByText(/key point/)).toBeInTheDocument()
    expect(screen.getByText('00:10')).toBeInTheDocument()
  })
  it('like sends feedback', async () => {
    let posted = false
    server.use(http.post('/api/feedback', async ({ request }) => {
      const b = await request.json() as { signal: number }
      posted = b.signal === 1
      return new HttpResponse(null, { status: 204 })
    }))
    renderAt('v1')
    await userEvent.click(await screen.findByText('👍 Like'))
    await new Promise((r) => setTimeout(r, 20))
    expect(posted).toBe(true)
  })
  it('shows Summarize only when no summary', async () => {
    server.use(http.get('/api/videos/:id', ({ params }) => HttpResponse.json({
      video_id: params.id, title: 'No Sum', url: 'u', status: 'transcribed',
      published_at: '2026-07-20', duration_s: 100, transcript: 't', summary: null })))
    renderAt('v9')
    expect(await screen.findByText('Summarize')).toBeInTheDocument()
  })
})
