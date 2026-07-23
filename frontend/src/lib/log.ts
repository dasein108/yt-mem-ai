import { apiBase } from './apiBase'

export function log(event: string, level = 'info', msg = '',
                    ctx: Record<string, unknown> = {}): void {
  try {
    void fetch(`${apiBase()}/log`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ event, level, msg, ctx }),
    }).catch(() => {})
  } catch {
    /* never throw */
  }
}

function _str(a: unknown): string {
  if (typeof a === 'string') return a
  try { return JSON.stringify(a) } catch { return String(a) }
}

const BRIDGE_FLAG = '__ytLogBridge'

/** Patch console.error/warn (keep original + forward to /log) and hook uncaught
 *  errors + unhandled rejections. Idempotent. NOT console.log/info (too noisy). */
export function installLogBridge(): void {
  if (typeof window === 'undefined') return
  const w = window as unknown as Record<string, unknown>
  if (w[BRIDGE_FLAG]) return
  w[BRIDGE_FLAG] = true

  const wrap = (level: 'error' | 'warn', orig: (...a: unknown[]) => void) =>
    (...args: unknown[]) => {
      orig(...args)
      log(`console.${level}`, level, args.map(_str).join(' ').slice(0, 2000))
    }
  console.error = wrap('error', console.error.bind(console))
  console.warn = wrap('warn', console.warn.bind(console))

  window.addEventListener('error', (e) =>
    log('ui.uncaught', 'error', String(e.message), { stack: (e.error as Error | undefined)?.stack }))
  window.addEventListener('unhandledrejection', (e) =>
    log('ui.unhandledrejection', 'error', _str(e.reason)))
}
