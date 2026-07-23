import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '../mocks/node'
import { renderWithProviders } from '../test/utils'
import { JobStrip } from './JobStrip'

describe('JobStrip', () => {
  it('shows a running job', async () => {
    server.use(http.get('/api/jobs', () => HttpResponse.json([
      { id: 'j1', kind: 'fetch', status: 'running', progress: null, result: null, error: null, created_at: 't0' }])))
    renderWithProviders(<JobStrip />)
    expect(await screen.findByText('fetch')).toBeInTheDocument()
  })
})
