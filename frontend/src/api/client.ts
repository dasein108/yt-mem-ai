import type { VideoOut, VideoDetail, SearchHit, Job, StatusCounts } from './types'
import { apiBase } from '@/lib/apiBase'
import { log } from '@/lib/log'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = (body as { detail?: string }).detail ?? detail
    } catch { /* non-json */ }
    log('ui.api_error', 'error', detail, { status: res.status, path })
    throw new ApiError(res.status, detail)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

const qs = (params: Record<string, string | number | undefined>) => {
  const u = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== '') u.set(k, String(v))
  const s = u.toString()
  return s ? `?${s}` : ''
}

export const api = {
  listVideos: (f: { status?: string; since?: string } = {}) =>
    req<VideoOut[]>(`/videos${qs(f)}`),
  getVideo: (id: string) => req<VideoDetail>(`/videos/${id}`),
  getStatus: () => req<StatusCounts>('/status'),
  search: (q: string, mode = 'hybrid', k = 10) =>
    req<SearchHit[]>(`/search${qs({ q, mode, k })}`),
  sendFeedback: (video_id: string, signal: number) =>
    req<void>('/feedback', { method: 'POST', body: JSON.stringify({ video_id, signal }) }),
  startFetch: (url: string, force = false) =>
    req<Job>('/jobs/fetch', { method: 'POST', body: JSON.stringify({ url, force }) }),
  startDiscover: (body: { after?: string; deep?: boolean; min_duration?: number }) =>
    req<Job>('/jobs/discover', { method: 'POST', body: JSON.stringify(body) }),
  startFetchPending: (body: { since?: string; limit?: number }) =>
    req<Job>('/jobs/fetch-pending', { method: 'POST', body: JSON.stringify(body) }),
  startSummarize: (video_id: string) =>
    req<Job>('/jobs/summarize', { method: 'POST', body: JSON.stringify({ video_id }) }),
  listJobs: () => req<Job[]>('/jobs'),
  getJob: (id: string) => req<Job>(`/jobs/${id}`),
}
