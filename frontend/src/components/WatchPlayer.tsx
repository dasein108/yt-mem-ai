import { useEffect, useRef, useState } from 'react'
import { isElectron } from '@/lib/electron'
import { Button } from './ui/button'

type Props = {
  videoId: string
  url: string | null
  onClose: () => void
  onReady?: (seek: (s: number) => void) => void
}

export function WatchPlayer({ videoId, url, onClose, onReady }: Props) {
  const watchUrl = url ?? `https://www.youtube.com/watch?v=${videoId}`
  const [start, setStart] = useState(0)
  // Real YouTube IFrame Player API attachment (playerRef.current.seekTo) isn't wired up
  // yet, so this stays null and every seek falls back to reloading the iframe with a
  // new `start=` param below.
  const playerRef = useRef<{ seekTo: (s: number, allow: boolean) => void } | null>(null)

  useEffect(() => {
    const seek = (s: number) => {
      if (playerRef.current) playerRef.current.seekTo(s, true)
      else setStart(Math.floor(s)) // fallback: reload iframe with start=
    }
    onReady?.(seek)
  }, [onReady])

  return (
    <div className="relative mb-4 aspect-video w-full overflow-hidden rounded-md border bg-black">
      <Button size="icon" variant="ghost" aria-label="close player"
        className="absolute right-1 top-1 z-10 bg-white/80" onClick={onClose}>✕</Button>
      {isElectron() ? (
        <webview src={watchUrl} className="h-full w-full" />
      ) : (
        <iframe className="h-full w-full"
          src={`https://www.youtube.com/embed/${videoId}?enablejsapi=1&start=${start}`}
          title="player" allow="autoplay; encrypted-media" allowFullScreen />
      )}
    </div>
  )
}
