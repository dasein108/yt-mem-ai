import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import { Input } from './ui/input'
import { Button } from './ui/button'
import { VideoList } from './VideoList'
import { SearchView } from './SearchView'
import { JobStrip } from './JobStrip'
import { AddDialog } from './AddDialog'
import { DiscoverDialog } from './DiscoverDialog'
import { useStartFetchPending } from '@/api/hooks'

export function AppShell() {
  const [query, setQuery] = useState('')
  const [addOpen, setAddOpen] = useState(false)
  const [discoverOpen, setDiscoverOpen] = useState(false)
  const fetchPending = useStartFetchPending()
  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center gap-2 border-b px-4 py-2">
        <span className="font-semibold">yt_summary</span>
        <Input placeholder="Search…" value={query}
          onChange={(e) => setQuery(e.target.value)} className="max-w-md" />
        <Button variant="outline" onClick={() => setAddOpen(true)}>+ Add</Button>
        <Button variant="outline" onClick={() => setDiscoverOpen(true)}>Discover</Button>
        <Button variant="outline" onClick={() => fetchPending.mutate({})}>Fetch pending</Button>
      </header>
      <div className="flex min-h-0 flex-1">
        <aside className="w-80 overflow-y-auto border-r">
          {query.trim() ? <SearchView query={query} /> : <VideoList />}
        </aside>
        <main className="min-w-0 flex-1 overflow-y-auto p-4"><Outlet /></main>
      </div>
      <JobStrip />
      <AddDialog open={addOpen} onOpenChange={setAddOpen} />
      <DiscoverDialog open={discoverOpen} onOpenChange={setDiscoverOpen} />
    </div>
  )
}
