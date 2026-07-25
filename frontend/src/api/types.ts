export interface VideoOut {
  video_id: string
  title: string | null
  url: string | null
  status: string | null
  published_at: string | null
  duration_s: number | null
}
export interface Summary {
  video_id: string
  summary_md: string
  highlights: string | null // JSON string
  qa: string | null // JSON string
  model: string | null
  created_at: string | null
}
export interface VideoDetail extends VideoOut {
  transcript: string | null
  summary: Summary | null
}
export interface SearchHit {
  video_id: string
  start_s: number | null
  end_s: number | null
  text: string | null
}
export interface Job {
  id: string
  kind: string
  status: 'queued' | 'running' | 'done' | 'error'
  progress: number | null
  result: Record<string, unknown> | null
  error: string | null
  created_at: string
  video_id: string | null
  updated_at?: string
}
export interface VideoPage { items: VideoOut[]; total: number }
export interface StatusCounts { counts: Record<string, number> }
export interface Highlight { start_s: number; label: string }
export interface QA { q: string; a: string }
