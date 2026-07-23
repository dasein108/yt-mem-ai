import { describe, it, expect } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../test/utils'
import { VideoList } from './VideoList'

describe('VideoList', () => {
  it('renders rows from the API', async () => {
    renderWithProviders(<VideoList />)
    expect(await screen.findByText('First Video')).toBeInTheDocument()
    expect(screen.getByText('Second')).toBeInTheDocument()
  })
  it('has a status filter', async () => {
    renderWithProviders(<VideoList />)
    await screen.findByText('First Video')
    const select = screen.getByLabelText('status filter')
    await userEvent.selectOptions(select, 'transcribed')
    await waitFor(() => expect((select as HTMLSelectElement).value).toBe('transcribed'))
  })
})
