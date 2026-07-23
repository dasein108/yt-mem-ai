import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useJobs } from '@/api/hooks'
import { Badge } from './ui/badge'

export function JobStrip() {
  const { data: jobs } = useJobs()
  const qc = useQueryClient()
  const prevDone = useRef(0)

  const doneCount = jobs?.filter((j) => j.status === 'done').length ?? 0
  useEffect(() => {
    if (doneCount > prevDone.current) {
      qc.invalidateQueries({ queryKey: ['videos'] })
      qc.invalidateQueries({ queryKey: ['status'] })
    }
    prevDone.current = doneCount
  }, [doneCount, qc])

  if (!jobs || jobs.length === 0) return <footer className="border-t px-4 py-1 text-xs text-slate-400">No jobs</footer>
  return (
    <footer className="flex items-center gap-3 border-t px-4 py-1 text-xs">
      <span className="font-medium">Jobs:</span>
      {jobs.slice(-5).map((j) => (
        <span key={j.id} className="flex items-center gap-1">
          {j.kind}
          {j.status === 'running' && <span className="animate-pulse">⏳</span>}
          {j.status === 'queued' && <Badge>queued</Badge>}
          {j.status === 'done' && <span className="text-green-600">✓</span>}
          {j.status === 'error' && <span className="text-red-600" title={j.error ?? ''}>✕</span>}
        </span>
      ))}
    </footer>
  )
}
