import { useState } from 'react'
import { Dialog, DialogTitle } from './ui/dialog'
import { Input } from './ui/input'
import { Button } from './ui/button'
import { useStartFetch } from '@/api/hooks'

export function AddDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [url, setUrl] = useState('')
  const start = useStartFetch()
  const submit = () => {
    if (!url.trim()) return
    start.mutate(url.trim(), { onSuccess: () => { setUrl(''); onOpenChange(false) } })
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTitle className="mb-3 text-lg font-semibold">Add a video</DialogTitle>
      <Input placeholder="https://youtube.com/watch?v=…" value={url} onChange={(e) => setUrl(e.target.value)} />
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
        <Button disabled={start.isPending} onClick={submit}>Fetch</Button>
      </div>
    </Dialog>
  )
}
