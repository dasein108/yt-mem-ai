import { useNavigate } from 'react-router-dom'
import { useSearch } from '@/api/hooks'
import { fmtTs } from '@/lib/utils'

export function SearchView({ query }: { query: string }) {
  const { data, isLoading } = useSearch(query)
  const navigate = useNavigate()
  return (
    <div>
      <p className="border-b p-2 text-xs text-slate-500">Search: “{query}”</p>
      {isLoading && <p className="p-3 text-sm text-slate-500">searching…</p>}
      {!isLoading && data?.length === 0 && <p className="p-3 text-sm text-slate-500">No results.</p>}
      <ul>
        {data?.map((h, i) => (
          <li key={i}>
            <button onClick={() => navigate(`/videos/${h.video_id}`)}
              className="flex w-full flex-col items-start border-b px-3 py-2 text-left hover:bg-slate-50">
              <span className="font-mono text-xs text-slate-500">{fmtTs(h.start_s ?? 0)} · {h.video_id}</span>
              <span className="text-sm">{h.text}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
