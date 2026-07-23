import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useVideos } from '@/api/hooks'
import { Badge } from './ui/badge'
import { cn } from '@/lib/utils'

const STATUSES = ['', 'discovered', 'downloaded', 'transcribed', 'summarized']

export function VideoList() {
  const [status, setStatus] = useState('')
  const { data, isLoading, error } = useVideos(status ? { status } : {})
  const navigate = useNavigate()
  const { id } = useParams()

  return (
    <div>
      <div className="border-b p-2">
        <select className="w-full rounded border px-2 py-1 text-sm"
          value={status} onChange={(e) => setStatus(e.target.value)} aria-label="status filter">
          {STATUSES.map((s) => <option key={s} value={s}>{s || 'all statuses'}</option>)}
        </select>
      </div>
      {isLoading && <p className="p-3 text-sm text-slate-500">loading…</p>}
      {error && <p className="p-3 text-sm text-red-600">API not reachable — run `yt-ai serve`</p>}
      <ul>
        {data?.map((v) => (
          <li key={v.video_id}>
            <button
              onClick={() => navigate(`/videos/${v.video_id}`)}
              className={cn('flex w-full flex-col items-start gap-1 border-b px-3 py-2 text-left hover:bg-slate-50',
                id === v.video_id && 'bg-slate-100')}
            >
              <span className="text-sm font-medium">{v.title ?? v.video_id}</span>
              <span className="flex items-center gap-2 text-xs text-slate-500">
                {v.published_at ?? '—'} <Badge>{v.status ?? '?'}</Badge>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
