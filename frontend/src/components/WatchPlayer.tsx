import { isElectron } from '@/lib/electron'
import { Button } from './ui/button'

export function WatchPlayer({ videoId, url, onClose }: { videoId: string; url: string | null; onClose: () => void }) {
  const watchUrl = url ?? `https://www.youtube.com/watch?v=${videoId}`
  return (
    <div className="relative mb-4 aspect-video w-full overflow-hidden rounded-md border bg-black">
      <Button size="icon" variant="ghost" aria-label="close player"
        className="absolute right-1 top-1 z-10 bg-white/80" onClick={onClose}>✕</Button>
      {isElectron() ? (
        <webview src={watchUrl} className="h-full w-full" />
      ) : (
        <iframe className="h-full w-full" src={`https://www.youtube.com/embed/${videoId}`}
          title="player" allow="autoplay; encrypted-media" allowFullScreen />
      )}
    </div>
  )
}
