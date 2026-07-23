# CLAUDE.md — yt_summary

Guidance for Claude Code (and any LLM) working in this repo.

## What this is

A local-first YouTube AI CLI (`yt-ai`): download audio, transcribe (captions →
faster-whisper fallback), store everything in an embedded LanceDB with per-chunk
embeddings, discover subscription uploads, and produce summaries/highlights/Q&A.
Heavy IO lives in the CLI; summarization is **skills-primary** (Claude Code skills,
not an API) to keep it free and high-quality.

## Architecture (module map)

- `config.py` — `.env` loading (`Config`). Secrets only from `.env` (gitignored).
- `proxy.py` / `cookies.py` — Webshare rotating proxy + Chrome cookies for yt-dlp.
- `download.py` — yt-dlp download + metadata; `build_opts(cfg, download_audio)`.
- `transcript/` — `captions.py` (youtube-transcript-api) → `whisper.py` (faster-whisper)
  fallback, orchestrated by `get_transcript`.
- `discovery.py` — subscription feed extraction (`discover`), injectable `extract_fn` seam.
- `store/` — `models.py` (dataclasses + LanceModel schemas + `chunk_schema`),
  `embeddings.py` (`build_embedder`, `chunk_segments`), `db.py` (LanceDB CRUD + search).
- `memory.py` — status-based `is_seen` / `mark_status`.
- `recommend.py` — taste-centroid ranking over chunk embeddings (like − dislike).
- `compile.py` — `compile_highlights` builds a deep-linked highlights doc from
  summarized videos' `summaries.highlights` + `chunks` spans (`chunk_span`
  snaps each highlight to its containing/nearest chunk, falling back to a
  fixed window), newest-video-first and budget-bounded by `--max-minutes`
  (`accumulate`). `render_markdown` emits `watch?v=ID&t=<start>s` links per
  clip; no media rendering here.
- `supercut.py` — renders `compile_highlights`' clip selection as an actual
  video reel instead of a doc: pure command-builders (`download_section_opts`
  — 720p `download_range_func` section + `build_opts` proxy/cookies;
  `normalize_label_cmd` — scale/pad/fps + `drawtext=textfile=<label_file>`,
  which sidesteps drawtext text-escaping entirely; `concat_cmd` — concat
  demuxer; `label_text`/`refs_markdown` — clip label/sidecar refs text) plus
  the orchestrator `build_supercut(db, since, max_minutes, out_path, cfg=,
  workdir=, download_fn=, ffmpeg_fn=)`, which takes injectable
  `download_fn`/`ffmpeg_fn` so the whole flow is unit-tested offline, and
  continues past a clip whose download/render fails (recorded in the
  `.refs.md` sidecar's skipped list) rather than aborting the run. Real
  rendering (actual yt-dlp downloads + ffmpeg) is manual smoke only, not in
  the test suite.
- `cli.py` — Typer app; thin `run_*` cores are the testable seam. `serve` runs the
  local API (below).
- `api/` — local FastAPI server (SP4), localhost-only, backend for the future
  desktop UI:
  - `app.py` — `create_app(cfg, *, store_opener, summarize_client, start_worker)`
    factory + read routes (`/videos`, `/videos/{id}`, `/status`, `/search`,
    `/recommend`, `POST /feedback`); wires up the in-memory job registry/worker
    via `lifespan` and delegates job routes to `app_jobs.register_jobs`.
  - `app_jobs.py` — `POST /jobs/{fetch,discover,fetch-pending,summarize}` +
    `GET /jobs/{id}`, `GET /jobs`; each job closure reopens the store via
    `app.state.store_opener()` and runs on `jobs.py`'s in-memory `Worker`
    (jobs live in a process-local dict — nothing persisted across restarts).
  - `jobs.py` — `JobRegistry`/`Job`/`Worker`, a queue + background thread with
    an injectable `run_one()` seam for offline tests.
  - `summarize.py` — `summarize_video(cfg, db, video_id, client)`: the API's
    summarization path, calling OpenRouter (`OPENROUTER_API_KEY` +
    `YT_OPENROUTER_MODEL`) and snapping highlight timestamps to chunk anchors.
  - `schemas.py` — pydantic request/response models for the above.
- `frontend/` — SP4b desktop UI: browser-first React (Vite+React+TS) over the
  SP4a local API, built with TanStack Query for data fetching and MSW for
  offline tests. MVP scope: Library/Detail/Search/Jobs; Recommend/Digest are
  deferred. Vite proxies `/api` to `127.0.0.1:8000` (see
  `frontend/vite.config.ts`); `VITE_API_BASE` overrides the client's base URL.
  `frontend/electron/` (SP4c) wraps this UI in Electron: `main.ts` spawns
  `uv run yt-ai serve` as a sidecar (via `lib.ts`'s `resolveApiCommand`/
  `waitForApi`, overridable with `YT_API_CMD`/`YT_API_PORT`), waits for
  `/status`, minimizes to a tray (`preload.ts`, `tray-icon.ts`), and kills the
  sidecar tree on quit; a video's Watch view uses `<webview>`/`<iframe>`
  (`WatchPlayer`). The API's CORS (`api/app.py`) was opened up for this
  packaged renderer. `frontend/electron-builder.json` packages a current-OS
  installer to `frontend/release/` via `npm run electron:build`;
  cross-platform installers/signing and bundling Python into the package are
  deferred. See `frontend/README.md` for setup and scripts.

## Store (LanceDB)

Tables: `videos`, `channels`, `transcripts`, `chunks` (embedded + FTS), `summaries`,
`feedback`, `app_state`. Video lifecycle `status`: `discovered → downloaded →
transcribed → summarized`.

## Conventions (follow these)

- **skills-primary summarization** — the CLI stores data; skills read it via
  `yt-ai show --json` / `search` / `save-summary` and never touch the store engine.
- **`_safe(...)`** guards every LanceDB `where/delete/update` clause that interpolates
  an id/key/status. Always use it for new filters.
- **`is_seen` is status-based** (`transcribed`/`summarized`) → ingest is retry-safe.
- **insert-only discovery** (`insert_discovered_video`) never downgrades a fetched video.
- **Injectable seams for offline tests**: `ydl_factory`, `extract_fn`, `model_factory`,
  and monkeypatched `cli.run_fetch`/`cli.discover_videos`. Unit tests must not hit the
  network or download models — the registered `FakeEmbedder` (tests/support.py) covers
  embeddings.
- Dates are `YYYY-MM-DD` strings; string comparison is date comparison.

## Recommendations

`like`/`dislike` write the `feedback` table (latest signal per video wins); `recommend`
builds like/dislike centroids from liked/disliked videos' chunk vectors and ranks unrated
transcribed/summarized videos.

## Skills

- `summarize-video` — one ingested video → summary/highlights/Q&A (`summaries` table).
- `daily-digest` — a day's transcribed videos → per-video summaries + `digests/<DATE>.md`.

There are two independent summarization paths, both writing the same `summaries`
table via `store.upsert_summary`: the skills-primary path above (free, via Claude
Code) and `POST /jobs/summarize` in `api/summarize.py` (OpenRouter, for the local
API/desktop UI). Neither is authoritative over the other — last write wins.

## Commands & daily routine

See README.md. Pipeline: `discover → fetch-pending → /daily-digest → compile`;
single video: `fetch → /summarize-video`.

## Dev

```bash
uv sync --extra dev
uv run pytest -q                        # offline unit suite (fake embedder)
YT_RUN_INTEGRATION=1 uv run pytest -q   # + real sentence-transformers integration
uv run --with ruff ruff check .         # lint
```

TDD: tests live in `tests/`, one per module; keep them offline via the injectable seams.
Design docs in `docs/superpowers/specs/`, plans in `docs/superpowers/plans/`.
