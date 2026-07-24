# SP9 — Desktop UI: subscription history, durable async jobs, embedded player

Design spec. Builds on SP4 (local API + React/Electron shell). Turns the desktop
app's first page into a paged subscription-history feed with per-video async
summary jobs that survive restart, an in-app YouTube player that seeks to
highlight timestamps, and hourly auto-sync of subscriptions.

## Goals

1. **First page = subscription history.** All discovered videos, newest-first,
   grouped by day ("Today", then dated sections), **paged**.
2. **Per-video "Generate summary" button** → an **async job** (summary +
   highlights + Q&A). Fire many; they run **bounded-parallel** (≤N), the rest
   queue. Live progress shown by **polling**.
3. **Jobs survive restart.** A durable `jobs` table is the source of truth; on
   `serve` startup, unfinished jobs are re-enqueued.
4. **Embedded YouTube player** in the detail/watch view; clicking a highlight
   **seeks** the embed to that timestamp (no reload).
5. **Refresh button** = discover on demand; **auto-sync every 1h** in the
   backend (runs whenever `serve` is up, even with the window closed).

## Non-goals

- Real YouTube account changes (see BACKLOG channel subscribe/unsubscribe).
- Recommend/Digest pages (still deferred from SP4).
- Replacing the Claude Code skills path; UI summaries use OpenRouter (below).

## Key constraint: summarization path

The running app cannot invoke Claude Code skills (those need Claude Code, not a
server). The UI's "Generate summary" therefore uses the **existing OpenRouter
path**: `POST /jobs/summarize` → `api/summarize.py` (`OPENROUTER_API_KEY` +
`YT_OPENROUTER_MODEL`). It writes the same `summaries` table as the skills path
(last-write-wins), snapping highlight timestamps to chunk anchors. No new
summarizer is built. If the key is unset, the button is disabled with a hint.

## Architecture

### Backend

**1. Durable `jobs` table (new LanceDB table).**
```
JobSchema: id: str, kind: str, video_id: str | None,
           status: str, progress: float | None, error: str | None,
           created_at: str, updated_at: str
```
- `kind ∈ {summarize, fetch, discover, fetch-pending}`.
- `status ∈ {queued, running, done, error}`.
- Created in `store/db.py init_db` (create-if-absent + `_ensure_columns`, same
  pattern as SP8 video meta). CRUD helpers: `insert_job`, `update_job`,
  `get_job`, `list_jobs(status=?, limit=?)`, using `_safe` on interpolated ids.

**2. Worker: bounded thread pool + write-through persistence.**
- `api/jobs.py` `Worker` gains `concurrency: int` (default `cfg` /
  `YT_JOB_CONCURRENCY`, ~3). `start()` spawns N daemon loop threads all draining
  the same `queue.Queue`. `run_one` unchanged in shape.
- A `persist` seam (callback) is invoked on each transition (queued/running/
  done/error) → writes the `jobs` row. Injectable so offline tests stay in
  memory (default no-op persist; the app wires the DB-backed one).
- The in-memory `JobRegistry` stays the live view; the DB is the durable mirror.
  After startup recovery the registry holds all still-active jobs, so the UI's
  live view reads the registry. Historical (`done`/`error`) jobs from before a
  restart live only in the DB: `GET /jobs?status=done` (history) reads the DB;
  the default active view reads the registry. No merge ambiguity — active from
  registry, history from DB.

**3. Startup recovery (`api/app.py` `lifespan`).**
- On start: `list_jobs(status in {queued, running})`.
- `running` → reset to `queued` (interrupted; we can't know progress).
- Re-submit each to the pool. Safe because job fns are idempotent:
  summarize=`upsert_summary`, fetch=`is_seen` retry-safe, discover=insert-only +
  high-water. "Resume" == "re-run", which is correct and cheap here.
- **Retry policy:** retries happen **only at startup** (the recovery above).
  There is **no runtime auto-retry**. Jobs that ended in `error` are **left as
  `error`** (not re-enqueued on start — a genuinely failing summarize would just
  loop/cost); the user clicks **Retry** to re-submit one.

**4. Auto-sync scheduler (`lifespan`).**
- **On by default.** A daemon timer thread runs `discover` **once on startup**,
  then every `YT_DISCOVER_INTERVAL_S` (default 3600; `0` disables). Uses the
  incremental discover (cheap: one feed call + high-water). Submitted as a normal
  `discover` job so it shows in `/jobs` and is deduped against a manual refresh
  (skip if a discover job is already active).

**5. API changes (`api/app.py`, `app_jobs.py`, `schemas.py`).**
- `GET /videos` gains `limit`, `offset`, `since` (newest-first already). Response
  adds `total` (for the pager). Reuses `run_list`-style filtering.
- `GET /jobs` returns `{id, kind, video_id, status, progress, error,
  created_at, updated_at}[]`; supports `?status=` and `?video_id=`.
- `POST /jobs/summarize {video_id}` (exists) → returns `{job_id}`.
- `POST /jobs/discover` (exists) = the Refresh button.
- No SSE/WebSocket — the UI **polls** `/jobs`.

### Frontend

**1. First page — `HistoryView` (route `/`).**
- Replaces the current list root. Fetches `GET /videos?limit=&offset=` via
  TanStack Query; renders **date-grouped** sections (Today first), newest-first.
- **Pager** (prev/next), **page size 30** (default; `limit=30`), not infinite scroll.
- Header: **Refresh** button (`POST /jobs/discover`, then invalidate `/videos`)
  and a "last synced / next sync" hint.
- Each row (extend `VideoList`/card): thumbnail, title, channel, duration,
  published date, **status badge**, **Generate summary** button, **Watch** link.

**2. Async summary button + job overlay (polling).**
- Click → `POST /jobs/summarize {video_id}` → optimistic "queued" badge.
- A `useJobs()` hook polls `GET /jobs` on a **~2s `refetchInterval`**, but only
  while any job is `queued|running` (interval → `false` when idle to avoid
  constant polling). Badges derived by **joining jobs to videos by `video_id`**
  (option A — no denormalized column). On a job → `done`, invalidate that
  video + `/videos` so the summary appears.
- `JobStrip` (exists) shows the global queue: running/queued counts + per-job
  progress; supports **many concurrent** jobs.

**3. Embedded player + highlight seek — `WatchPlayer`/`VideoDetail`.**
- Load `https://www.youtube.com/embed/<id>?enablejsapi=1` and attach the
  **YouTube IFrame Player API**. Highlights listed beside the player; clicking
  one calls `player.seekTo(startSeconds, true)` — smooth, no reload.
- Fallback if the API can't load (e.g. strict CSP in packaged Electron): reload
  the iframe with `?start=<s>`. (Note: embeds use `start=`, not the watch-page
  `t=`.)
- Highlights come from the video's `summaries.highlights` (already stored).

## Data flow

```
serve start
  ├─ lifespan: init_db (jobs table), recover queued/running jobs → pool
  └─ auto-sync timer: discover job every 1h
UI /  (HistoryView)
  ├─ GET /videos?limit&offset  → date-grouped pager
  ├─ GET /jobs (poll ~2s while active) → overlay "summarizing…" badges
  ├─ Refresh → POST /jobs/discover → invalidate /videos
  └─ Generate summary → POST /jobs/summarize → badge → (done) show summary
UI /videos/:id (VideoDetail + WatchPlayer)
  └─ embed + IFrame API; click highlight → player.seekTo(t)
```

## Error handling

- Job failure → `status=error` + message; row shows a **Retry** (re-submit).
- OpenRouter key missing → summarize button disabled with tooltip; `/jobs/
  summarize` returns a clear 4xx.
- Auto-sync failure (network/feed) → logged via `obs`, surfaced as an errored
  `discover` job; never crashes the worker (existing try/except).
- Restart mid-job → recovered as queued and re-run (idempotent).
- Polling stops when no active jobs (interval=false) to avoid needless load.

## Testing

- **Backend (offline, existing seams):** jobs-table CRUD; Worker with
  `concurrency>1` runs N in parallel (fake `run_one`); write-through persist
  called on each transition; startup recovery re-enqueues queued+running and
  resets running→queued; auto-sync timer submits a discover job (injected
  clock/tick, no real network); `/videos` pagination (limit/offset/total);
  `/jobs` filtering. Reuse `FakeEmbedder`, injected `run_one`, monkeypatched
  discover/summarize.
- **Frontend (MSW):** HistoryView paging + date grouping; Generate-summary
  posts and shows a badge; job polling flips badge queued→running→done and
  reveals the summary; Refresh invalidates; WatchPlayer seekTo called on
  highlight click (mock IFrame API).
- Concurrency bound respected (≤N running); idempotent re-run leaves one summary.

## Config (new)

- `YT_JOB_CONCURRENCY` (default 3) — max parallel jobs.
- `YT_DISCOVER_INTERVAL_S` (default 3600, 0=off) — auto-sync period.
- Existing: `OPENROUTER_API_KEY`, `YT_OPENROUTER_MODEL` (summaries).

## Rollout / sequencing

1. `jobs` table + CRUD + Worker thread-pool + write-through persist (backend, tested).
2. Startup recovery + auto-sync timer in `lifespan`.
3. `/videos` pagination + `/jobs` shape.
4. Frontend: HistoryView (paged, grouped, Refresh) + summary button + job polling.
5. WatchPlayer IFrame-API seek.

Each step ships behind the existing MVP; nothing here changes the CLI or the
skills summarization path.
