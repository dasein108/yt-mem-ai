import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useVideos, useJobs, useSummarize, useStartDiscover } from '@/api/hooks'
import { Button } from './ui/button'
import { Badge } from './ui/badge'
import { cn } from '@/lib/utils'
import type { VideoOut } from '@/api/types'

const PAGE = 30
const today = () => new Date().toISOString().slice(0, 10)

function groupByDay(items: VideoOut[]): [string, VideoOut[]][] {
  const groups: Record<string, VideoOut[]> = {}
  for (const v of items) (groups[v.published_at ?? 'Unknown'] ??= []).push(v)
  return Object.entries(groups)
}

export function HistoryView() {
  const [offset, setOffset] = useState(0)
  const videos = useVideos({ limit: PAGE, offset })
  const jobs = useJobs()
  const summarize = useSummarize()
  const discover = useStartDiscover()

  const activeFor = (id: string) =>
    jobs.data?.find((j) => j.video_id === id && (j.status === 'queued' || j.status === 'running'))
  const total = videos.data?.total ?? 0

  return (
    <div className="p-4">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Subscriptions</h1>
        <Button variant="outline" onClick={() => discover.mutate({})} disabled={discover.isPending}>
          Refresh
        </Button>
      </div>
      {videos.isLoading && <p className="text-sm text-slate-500">loading…</p>}
      {videos.error && <p className="text-sm text-red-600">API not reachable — run `yt-ai serve`</p>}
      {groupByDay(videos.data?.items ?? []).map(([day, rows]) => (
        <section key={day} className="mb-6">
          <h2 className="mb-2 text-sm font-medium text-slate-500">
            {day === today() ? 'Today' : day}
          </h2>
          <ul className="divide-y">
            {rows.map((v) => {
              const job = activeFor(v.video_id)
              const done = v.status === 'summarized'
              return (
                <li key={v.video_id} className="flex items-center gap-3 py-2">
                  <Link to={`/videos/${v.video_id}`} className="min-w-0 flex-1 hover:underline">
                    <span className="block truncate">{v.title ?? v.video_id}</span>
                    {v.channel && (
                      <span className="block truncate text-xs text-slate-500">{v.channel}</span>
                    )}
                  </Link>
                  {job ? (
                    <Badge className="bg-amber-100 text-amber-700">summarizing…</Badge>
                  ) : done ? (
                    <Badge className="bg-emerald-100 text-emerald-700">summarized</Badge>
                  ) : (
                    <Button size="sm" onClick={() => summarize.mutate(v.video_id)} disabled={summarize.isPending}>
                      Summarize
                    </Button>
                  )}
                </li>
              )
            })}
          </ul>
        </section>
      ))}
      <div className="mt-4 flex items-center gap-2">
        <Button
          variant="outline"
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - PAGE))}
        >
          Prev
        </Button>
        <span className={cn('text-sm text-slate-500')}>
          {total === 0 ? 0 : offset + 1}–{Math.min(offset + PAGE, total)} of {total}
        </span>
        <Button
          variant="outline"
          disabled={offset + PAGE >= total}
          onClick={() => setOffset(offset + PAGE)}
        >
          Next
        </Button>
      </div>
    </div>
  )
}
