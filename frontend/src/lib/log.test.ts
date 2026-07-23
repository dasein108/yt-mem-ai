import { describe, it, expect, afterEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../mocks/node'
import { log, installLogBridge } from './log'

const sleep = (ms = 20) => new Promise((r) => setTimeout(r, ms))

describe('log', () => {
  it('POSTs the event to /log', async () => {
    let got: unknown = null
    server.use(http.post('/api/log', async ({ request }) => {
      got = await request.json()
      return new HttpResponse(null, { status: 204 })
    }))
    log('ui.start', 'info', 'hello', { a: 1 })
    await sleep()
    expect(got).toMatchObject({ event: 'ui.start', level: 'info', ctx: { a: 1 } })
  })
  it('never throws when the endpoint fails', async () => {
    server.use(http.post('/api/log', () => new HttpResponse(null, { status: 500 })))
    expect(() => log('x')).not.toThrow()
    await sleep()
  })
})

describe('installLogBridge', () => {
  const origError = console.error
  const origWarn = console.warn
  afterEach(() => {
    console.error = origError
    console.warn = origWarn
    delete (window as unknown as Record<string, unknown>).__ytLogBridge
  })

  it('forwards console.error to /log and still calls the original', async () => {
    const posts: Record<string, unknown>[] = []
    server.use(http.post('/api/log', async ({ request }) => {
      posts.push(await request.json() as Record<string, unknown>)
      return new HttpResponse(null, { status: 204 })
    }))
    let origCalled = false
    console.error = () => { origCalled = true }
    installLogBridge()
    console.error('boom', { x: 1 })
    await sleep()
    expect(origCalled).toBe(true)                                   // original preserved
    expect(posts.some((p) => p.event === 'console.error' && p.level === 'error')).toBe(true)
  })

  it('is idempotent (second install does not re-wrap)', () => {
    installLogBridge()
    const wrapped = console.error
    installLogBridge()
    expect(console.error).toBe(wrapped)
  })
})
