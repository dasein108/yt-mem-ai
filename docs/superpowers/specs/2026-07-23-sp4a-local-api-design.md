# SP4a — Local FastAPI Design

**Date:** 2026-07-23
**Status:** Approved (brainstorming complete)
**Part of:** SP4 Frontend (SP4a API → SP4b React UI → SP4c Electron shell).
**Builds on:** all prior SPs — wraps the existing `yt_summary` service layer.

## Vision

A local FastAPI server (bound to `127.0.0.1`) that exposes the yt_summary
pipeline over HTTP so the React UI (SP4b) — and eventually the Electron app
(SP4c) — can drive it. It wraps the existing `run_*` cores and store reads,
adds a background-job system for the multi-minute operations (fetch / discover /
whisper), and an automated OpenRouter summarizer so a standalone GUI can produce
summaries without Claude Code.

## Locked Decisions

| Concern | Choice |
|---|---|
| Framework | FastAPI + uvicorn, bound `127.0.0.1` (local only) |
| Long jobs | background jobs + polling: `POST /jobs/*` → `job_id`; `GET /jobs/{id}` |
| Job storage | in-memory registry (does not survive server restart; `run_fetch` is resumable) |
| Job execution | a single worker thread draining a queue (serializes heavy whisper work) |
| Job store access | each job opens its own store connection (LanceDB write-thread safety) |
| GUI summaries | automated **OpenRouter** summarizer endpoint (writes `summaries`, marks `summarized`); the skill stays for power users |
| Auth | none for now (localhost-bound); token can be added later |
| Scope | backend only — no React (SP4b) |

## Architecture

```
yt_summary/
  api/
    __init__.py
    app.py       FastAPI app + lifespan (shared read store) + routes
    jobs.py      JobRegistry (in-memory), Worker (single thread + queue), Job
    summarize.py automated OpenRouter summarizer
    schemas.py   pydantic request/response models
  cli.py         + serve command (runs uvicorn)
pyproject.toml   + fastapi, uvicorn
```

The API is a thin HTTP layer over the existing service functions:
`run_fetch`, `run_search`, `run_discover`, `run_list`, `run_fetch_pending`,
`run_feedback`, `run_recommend`, and store reads (`get_video`,
`get_transcript_text`, `get_summary`, `count_by_status`, `list_chunks`).

### jobs.py

- `Job` dataclass: `id: str`, `kind: str`, `status: Literal["queued","running","done","error"]`,
  `progress: float | None`, `result: dict | None`, `error: str | None`, `created_at: str`.
- `JobRegistry`: thread-safe dict of `Job`s; `create(kind, fn) -> Job`, `get(id)`, `list()`.
- `Worker`: a single daemon thread consuming a `queue.Queue`. For each job: mark
  `running`, call `fn(job)` (which may set `job.progress` and returns a result dict),
  mark `done`/`error`. Serializes all heavy work so two whisper runs never overlap.
- Job functions open their own store: `db = open_store(cfg)` inside the job, not the
  shared request-scoped handle.
- Job IDs are `uuid4` hex at runtime; tests assert on job structure/transitions, not exact IDs.

### summarize.py

- `summarize_video(cfg, db, video_id, client=None) -> dict` — the automated twin of the
  `summarize-video` skill:
  1. Load transcript (`get_transcript_text`) + chunks (`list_chunks`) for timestamps.
     If no transcript → raise a clear error.
  2. Build a prompt: transcript + a compact list of `(start_s, text)` chunk anchors;
     ask for JSON `{summary_md, highlights: [{start_s, label}], qa: [{q, a}]}`.
  3. Call OpenRouter via the OpenAI-compatible client (`base_url=https://openrouter.ai/api/v1`,
     `api_key=cfg.openrouter_api_key`), JSON-mode / parse the response.
  4. Snap each highlight `start_s` to the nearest real chunk `start_s` (never invent).
  5. Persist: `upsert_summary(..., model=<openrouter-model>)` + `mark_status(summarized)`.
  6. Return the summary dict.
- `client` is injectable (defaults to the OpenRouter client) so tests pass a fake that
  returns canned JSON — no network.
- Missing `openrouter_api_key` → clear error before any call.

### schemas.py

Pydantic models: `VideoOut`, `VideoDetailOut` (video + transcript + summary),
`SearchHit`, `RecommendItem`, `FeedbackIn`, `JobOut`, `StatusOut`, and job-start
request bodies (`FetchIn`, `DiscoverIn`, `FetchPendingIn`, `SummarizeIn`).

### app.py — endpoints

Reads (synchronous, fast):
- `GET /videos?status=&since=` → `run_list` → `list[VideoOut]`
- `GET /videos/{video_id}` → `get_video` + `get_transcript_text` + `get_summary` → `VideoDetailOut` (404 if unknown)
- `GET /status` → `count_by_status` → `StatusOut`
- `GET /search?q=&mode=hybrid&k=10` → `run_search` → `list[SearchHit]`
- `GET /recommend?limit=20` → `run_recommend` + `get_video` per id → `list[RecommendItem]`

Fast actions:
- `POST /feedback` `{video_id, signal}` → `run_feedback` → 204

Long jobs (enqueue → poll):
- `POST /jobs/fetch` `{url, force?}` → `JobOut` (runs `run_fetch`)
- `POST /jobs/discover` `{after?, deep?, min_duration?}` → `JobOut` (runs `run_discover`)
- `POST /jobs/fetch-pending` `{since?, limit?}` → `JobOut` (runs `run_fetch_pending`)
- `POST /jobs/summarize` `{video_id}` → `JobOut` (runs `summarize_video`)
- `GET /jobs/{id}` → `JobOut` (404 if unknown)
- `GET /jobs` → `list[JobOut]`

App lifespan: on startup, build `cfg = load_config()`, open a shared read-only store
handle for the sync read endpoints, and start the `Worker` thread; on shutdown, stop
the worker. The shared handle is used only by read endpoints; job threads open their own.

### CLI

`serve` command: `yt-ai serve [--host 127.0.0.1] [--port 8000]` → `uvicorn.run(app, ...)`.

### Data Flow

```
React (SP4b) ──HTTP──▶ FastAPI (127.0.0.1)
  GET reads          → run_list / search / recommend / get_video / count_by_status
  POST /feedback     → run_feedback
  POST /jobs/*       → enqueue → Worker thread → run_fetch/discover/fetch-pending/summarize
       GET /jobs/id  → poll status/progress/result
  summarize job      → OpenRouter → summaries table + status=summarized
```

### Error Handling

- Unknown `video_id` on detail/summarize → 404 / job `error`.
- Job function raising → job `status=error`, `error=<message>`; the worker continues to the next job (never dies).
- Missing `openrouter_api_key` on a summarize job → job `error` with an actionable message.
- LanceDB write from a job thread uses that job's own connection (no shared-handle contention).
- The server binds `127.0.0.1` only — not reachable off-host.

### Testing (offline)

- `TestClient` for all endpoints. Inject fakes for the `run_*` cores where a test would
  otherwise hit network/whisper (monkeypatch `app`-module names, mirroring the CLI test pattern).
- Reads: seed a temp-dir LanceDB (fake embedder) via the store, point the app at it, assert
  `GET /videos`, `/videos/{id}`, `/status`, `/search`, `/recommend` shapes.
- `POST /feedback` writes the feedback row.
- Jobs: enqueue a job whose `fn` is a fast fake; drain the queue **inline** in the test
  (call the worker's process-one step directly, no real thread sleeping), assert the job
  transitions `queued → running → done` with the expected result; a raising `fn` → `error`
  and the worker survives.
- `summarize_video`: inject a fake client returning canned JSON; assert it snaps highlights
  to real chunk `start_s`, writes the `summaries` row, and marks the video `summarized`.
  Missing key → error.
- No real uvicorn server, no OpenRouter call, no whisper in the unit suite.

## Documentation Updates

- README: add a "Local API (SP4)" section — `yt-ai serve`, the endpoint list, that it's localhost-only.
- `CLAUDE.md`: add the `api/` package to the module map + the jobs + OpenRouter-summarizer notes.
- Roadmap memory: mark SP4a done; note SP4b (React) consumes this API.

## Out of Scope

- React UI (SP4b), Electron shell / tray / embedded YouTube (SP4c).
- Persistent job storage / job cancellation / retries (in-memory, best-effort).
- SSE/streaming progress (the jobs model can gain it later).
- Auth/multi-user (localhost single-user).
- WebSocket, rate limiting, pagination beyond simple `limit`.
