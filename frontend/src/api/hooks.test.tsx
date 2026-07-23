import { describe, it, expect } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useVideos, useSearch } from './hooks'

const wrap = () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}

describe('hooks', () => {
  it('useVideos returns fixture data', async () => {
    const { result } = renderHook(() => useVideos(), { wrapper: wrap() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.length).toBe(2)
  })
  it('useSearch is disabled for empty query', () => {
    const { result } = renderHook(() => useSearch(''), { wrapper: wrap() })
    expect(result.current.fetchStatus).toBe('idle')
  })
})
