import { useState } from 'react'
import { Dialog, DialogTitle } from './ui/dialog'
import { Input } from './ui/input'
import { Button } from './ui/button'
import { useStartDiscover } from '@/api/hooks'

export function DiscoverDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [after, setAfter] = useState('')
  const [minDuration, setMinDuration] = useState('120')
  const [deep, setDeep] = useState(false)
  const start = useStartDiscover()
  const submit = () => start.mutate(
    { after: after || undefined, deep, min_duration: Number(minDuration) || 120 },
    { onSuccess: () => onOpenChange(false) },
  )
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTitle className="mb-3 text-lg font-semibold">Discover subscriptions</DialogTitle>
      <label className="block text-sm">After (YYYY-MM-DD)
        <Input value={after} onChange={(e) => setAfter(e.target.value)} placeholder="optional" /></label>
      <label className="mt-2 block text-sm">Min duration (s)
        <Input value={minDuration} onChange={(e) => setMinDuration(e.target.value)} /></label>
      <label className="mt-2 flex items-center gap-2 text-sm">
        <input type="checkbox" checked={deep} onChange={(e) => setDeep(e.target.checked)} /> Deep (enumerate channels)</label>
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
        <Button disabled={start.isPending} onClick={submit}>Discover</Button>
      </div>
    </Dialog>
  )
}
