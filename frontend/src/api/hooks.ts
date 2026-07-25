import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type { Job } from './types'
import { useDebounce } from '@/lib/useDebounce'

export function useVideos(
  filters: { status?: string; since?: string; limit?: number; offset?: number } = {},
) {
  return useQuery({ queryKey: ['videos', filters], queryFn: () => api.listVideos(filters) })
}
export function useVideo(id: string | undefined) {
  return useQuery({ queryKey: ['video', id], queryFn: () => api.getVideo(id!), enabled: !!id })
}
export function useStatus() {
  return useQuery({ queryKey: ['status'], queryFn: api.getStatus })
}
export function useSearch(q: string, mode = 'hybrid') {
  const debouncedQ = useDebounce(q, 300)
  return useQuery({
    queryKey: ['search', debouncedQ, mode],
    queryFn: () => api.search(debouncedQ, mode),
    enabled: debouncedQ.trim().length > 0,
  })
}
const active = (j: Job) => j.status === 'queued' || j.status === 'running'
export function useJobs() {
  return useQuery({
    queryKey: ['jobs'],
    queryFn: api.listJobs,
    refetchInterval: (query) => (query.state.data?.some(active) ? 1000 : false),
  })
}

function useJobMutation<V>(fn: (v: V) => Promise<Job>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['jobs'] }),
  })
}
export const useStartFetch = () => useJobMutation((url: string) => api.startFetch(url))
export const useStartDiscover = () =>
  useJobMutation((b: { after?: string; deep?: boolean; min_duration?: number }) => api.startDiscover(b))
export const useStartFetchPending = () =>
  useJobMutation((b: { since?: string; limit?: number }) => api.startFetchPending(b))
export const useSummarize = () => useJobMutation((id: string) => api.startSummarize(id))

export function useFeedback() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ video_id, signal }: { video_id: string; signal: number }) =>
      api.sendFeedback(video_id, signal),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['videos'] }),
  })
}
