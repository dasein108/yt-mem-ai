import { useParams } from 'react-router-dom'
import { useVideo, useFeedback, useSummarize } from '@/api/hooks'
import { Button } from './ui/button'
import { fmtTs } from '@/lib/utils'
import type { Highlight, QA } from '@/api/types'

function parse<T>(s: string | null | undefined): T[] {
  if (!s) return []
  try { const v = JSON.parse(s); return Array.isArray(v) ? (v as T[]) : [] } catch { return [] }
}

export function VideoDetail() {
  const { id } = useParams()
  const { data: v, isLoading, error } = useVideo(id)
  const feedback = useFeedback()
  const summarize = useSummarize()

  if (!id) return <p className="text-slate-500">Select a video.</p>
  if (isLoading) return <p className="text-slate-500">loading…</p>
  if (error || !v) return <p className="text-red-600">not found</p>

  const highlights = parse<Highlight>(v.summary?.highlights)
  const qa = parse<QA>(v.summary?.qa)

  return (
    <article className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold">{v.title ?? v.video_id}</h1>
        <a href={v.url ?? '#'} className="text-sm text-blue-600" target="_blank" rel="noreferrer">{v.url}</a>
      </header>
      <div className="flex gap-2">
        <Button size="sm" variant="outline" onClick={() => feedback.mutate({ video_id: v.video_id, signal: 1 })}>👍 Like</Button>
        <Button size="sm" variant="outline" onClick={() => feedback.mutate({ video_id: v.video_id, signal: -1 })}>👎 Dislike</Button>
        {!v.summary && (
          <Button size="sm" disabled={summarize.isPending || summarize.isSuccess} onClick={() => summarize.mutate(v.video_id)}>
            {summarize.isPending ? 'Summarizing…' : 'Summarize'}
          </Button>
        )}
      </div>
      {v.summary && (
        <section className="space-y-3">
          <div>
            <h2 className="font-medium">Summary</h2>
            <p className="whitespace-pre-wrap text-sm">{v.summary.summary_md}</p>
          </div>
          {highlights.length > 0 && (
            <div>
              <h2 className="font-medium">Highlights</h2>
              <ul className="text-sm">
                {highlights.map((h, i) => (
                  <li key={i}><span className="font-mono text-slate-500">{fmtTs(h.start_s)}</span> — {h.label}</li>
                ))}
              </ul>
            </div>
          )}
          {qa.length > 0 && (
            <div>
              <h2 className="font-medium">Q&amp;A</h2>
              <dl className="space-y-1 text-sm">
                {qa.map((x, i) => (<div key={i}><dt className="font-medium">{x.q}</dt><dd className="text-slate-600">{x.a}</dd></div>))}
              </dl>
            </div>
          )}
        </section>
      )}
      {v.transcript && (
        <details><summary className="cursor-pointer text-sm text-slate-500">Transcript</summary>
          <p className="mt-2 whitespace-pre-wrap text-sm text-slate-700">{v.transcript}</p></details>
      )}
    </article>
  )
}
