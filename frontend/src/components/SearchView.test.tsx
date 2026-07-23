import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '../mocks/node'
import { renderWithProviders } from '../test/utils'
import { SearchView } from './SearchView'

describe('SearchView', () => {
  it('renders hits for a query', async () => {
    renderWithProviders(<SearchView query="matched" />)
    expect(await screen.findByText('matched snippet')).toBeInTheDocument()
  })

  it('shows a no-results message for zero hits', async () => {
    server.use(http.get('/api/search', () => HttpResponse.json([])))
    renderWithProviders(<SearchView query="nothing-matches" />)
    expect(await screen.findByText('No results.')).toBeInTheDocument()
  })
})
