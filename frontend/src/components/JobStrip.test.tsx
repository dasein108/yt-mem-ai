import { describe, it, expect, vi } from 'vitest'
import { screen, act, render, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { server } from '../mocks/node'
import { renderWithProviders } from '../test/utils'
import { JobStrip } from './JobStrip'
import type { Job } from '../api/types'

const job = (overrides: Partial<Job>): Job => ({
  id: 'j1', kind: 'fetch', status: 'running', progress: null, result: null, error: null, created_at: 't0',
  ...overrides,
})

describe('JobStrip', () => {
  it('shows a running job', async () => {
    server.use(http.get('/api/jobs', () => HttpResponse.json([
      { id: 'j1', kind: 'fetch', status: 'running', progress: null, result: null, error: null, created_at: 't0' }])))
    renderWithProviders(<JobStrip />)
    expect(await screen.findByText('fetch')).toBeInTheDocument()
  })

  it('invalidates the video query when a job transitions to done', async () => {
    server.use(http.get('/api/jobs', () => HttpResponse.json([])))
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    qc.setQueryData(['video', 'v1'], { video_id: 'v1' })
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries')

    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter><JobStrip /></MemoryRouter>
      </QueryClientProvider>,
    )

    // Let the initial fetch settle before we start driving the cache manually.
    await screen.findByText('No jobs')

    act(() => {
      qc.setQueryData(['jobs'], [job({ status: 'running' })])
    })
    await screen.findByText('fetch')

    act(() => {
      qc.setQueryData(['jobs'], [job({ status: 'done' })])
    })

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: ['video'] }),
      )
    })
  })
})
