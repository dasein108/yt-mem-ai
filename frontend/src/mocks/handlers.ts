import { http, HttpResponse } from 'msw'

export const videosFixture = [
  { video_id: 'v1', title: 'First Video', url: 'https://y/v1', status: 'summarized',
    published_at: '2026-07-22', duration_s: 600 },
  { video_id: 'v2', title: 'Second', url: 'https://y/v2', status: 'transcribed',
    published_at: '2026-07-21', duration_s: 300 },
]

export const handlers = [
  http.get('/api/videos', () => HttpResponse.json(videosFixture)),
  http.get('/api/videos/:id', ({ params }) => {
    const v = videosFixture.find((x) => x.video_id === params.id)
    if (!v) return new HttpResponse(null, { status: 404 })
    return HttpResponse.json({
      ...v, transcript: 'hello world',
      summary: { video_id: v.video_id, summary_md: 'A summary.',
        highlights: JSON.stringify([{ start_s: 10, label: 'key point' }]),
        qa: JSON.stringify([{ q: 'what?', a: 'this.' }]), model: 'test', created_at: 't0' },
    })
  }),
  http.get('/api/status', () => HttpResponse.json({ counts: { transcribed: 1, summarized: 1 } })),
  http.get('/api/search', () => HttpResponse.json([
    { video_id: 'v1', start_s: 10, end_s: 20, text: 'matched snippet' }])),
  http.post('/api/feedback', () => new HttpResponse(null, { status: 204 })),
  http.get('/api/jobs', () => HttpResponse.json([])),
  http.post('/api/jobs/:kind', ({ params }) => HttpResponse.json({
    id: 'job1', kind: String(params.kind), status: 'queued', progress: null,
    result: null, error: null, created_at: 't0' })),
  http.get('/api/jobs/:id', ({ params }) => HttpResponse.json({
    id: String(params.id), kind: 'fetch', status: 'done', progress: null,
    result: { video_id: 'vX' }, error: null, created_at: 't0' })),
]
