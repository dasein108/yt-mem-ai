import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../test/utils'
import { SearchView } from './SearchView'

describe('SearchView', () => {
  it('renders hits for a query', async () => {
    renderWithProviders(<SearchView query="matched" />)
    expect(await screen.findByText('matched snippet')).toBeInTheDocument()
  })
})
