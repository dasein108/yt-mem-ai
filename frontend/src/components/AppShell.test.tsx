import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../test/utils'
import { AppShell } from './AppShell'

describe('AppShell', () => {
  it('renders the title and search box', () => {
    renderWithProviders(<AppShell />)
    expect(screen.getByText('yt_summary')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Search…')).toBeInTheDocument()
  })
})
