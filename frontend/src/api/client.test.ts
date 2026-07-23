import { describe, it, expect } from 'vitest'
import { server } from '../mocks/node'
import { http, HttpResponse } from 'msw'
import { api, ApiError } from './client'

describe('api client', () => {
  it('lists videos', async () => {
    const vids = await api.listVideos()
    expect(vids.map((v) => v.video_id)).toEqual(['v1', 'v2'])
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
})
