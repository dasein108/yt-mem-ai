import { describe, it, expect, afterEach } from 'vitest'
import { server } from '../mocks/node'
import { http, HttpResponse } from 'msw'
import { api, ApiError } from './client'

describe('api client', () => {
  it('lists videos', async () => {
    const vids = await api.listVideos()
    expect(vids.items.map((v) => v.video_id)).toEqual(['v1', 'v2'])
    expect(vids.total).toBe(2)
  })
  it('throws ApiError with detail on non-2xx', async () => {
    server.use(http.get('/api/status', () =>
      HttpResponse.json({ detail: 'boom' }, { status: 500 })))
    await expect(api.getStatus()).rejects.toMatchObject({ status: 500, message: 'boom' })
    await expect(api.getStatus()).rejects.toBeInstanceOf(ApiError)
  })
  it('204 feedback resolves to undefined', async () => {
    await expect(api.sendFeedback('v1', 1)).resolves.toBeUndefined()
  })

  describe('in Electron (window.electron.apiBase set)', () => {
    afterEach(() => {
      delete (window as unknown as { electron?: unknown }).electron
    })

    it('uses the absolute apiBase instead of the /api proxy path', async () => {
      ;(window as unknown as { electron: { apiBase: string } }).electron = {
        apiBase: 'http://127.0.0.1:9999',
      }
      server.use(http.get('http://127.0.0.1:9999/status', () =>
        HttpResponse.json({ counts: {} })))
      await expect(api.getStatus()).resolves.toEqual({ counts: {} })
    })
  })
})
