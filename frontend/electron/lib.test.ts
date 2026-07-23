import { describe, it, expect } from 'vitest'
import { resolveApiCommand, waitForApi } from './lib'

describe('resolveApiCommand', () => {
  it('defaults to uv run yt-ai serve', () => {
    const c = resolveApiCommand({}, '/repo')
    expect(c).toEqual({ command: 'uv', args: ['run', 'yt-ai', 'serve', '--port', '8000'], cwd: '/repo' })
  })
  it('honors YT_API_PORT', () => {
    expect(resolveApiCommand({ YT_API_PORT: '9001' }, '/repo').args).toContain('9001')
  })
  it('honors YT_API_CMD override', () => {
    const c = resolveApiCommand({ YT_API_CMD: 'python -m x' }, '/repo')
    expect(c).toEqual({ command: 'python', args: ['-m', 'x'], cwd: '/repo' })
  })
})

describe('waitForApi', () => {
  it('returns true on first ok response', async () => {
    const ok = (async () => ({ ok: true })) as unknown as typeof fetch
    expect(await waitForApi('u', ok, { attempts: 3, delayMs: 0 })).toBe(true)
  })
  it('returns false after attempts exhaust', async () => {
    let calls = 0
    const fail = (async () => { calls++; throw new Error('down') }) as unknown as typeof fetch
    expect(await waitForApi('u', fail, { attempts: 3, delayMs: 0 })).toBe(false)
    expect(calls).toBe(3)
  })
})
