# CLAUDE.md — yt-mem-ai

Guidance for Claude Code (and any LLM) working in this repo.

## What this is

A local-first YouTube AI CLI (`yt-ai`): download audio, transcribe (captions →
faster-whisper fallback), store everything in an embedded LanceDB with per-chunk
embeddings, discover subscription uploads, and produce summaries/highlights/Q&A.
Heavy IO lives in the CLI; summarization is **skills-primary** (Claude Code skills,
not an API) to keep it free and high-quality.

## Architecture (module map)

- `config.py` — `.env` loading (`Config`). Secrets only from `.env` (gitignored).
  `use_webshare` (`YT_USE_WEBSHARE`, default **off**) gates the Webshare proxy;
  `discover_feed_limit`/`discover_overlap_s` tune incremental discovery.
- `obs.py` — unified logging. `log_event(source, event, level="info", msg="", *,
  log_file=None, **ctx)` never raises (append fails silently); `blog(...)` is the
  `source="backend"` shorthand used across `cli.py`. Writes one JSON line
  (`{ts, source, level, event, msg, ...ctx}`) to `Config.log_file`
  (`YT_LOG_FILE` env, default `logs/common.jsonl`; gitignored).
- `proxy.py` / `cookies.py` — Webshare rotating proxy + Chrome cookies for yt-dlp.
  Both `ytdlp_proxy_url` and `webshare_config` return `None` unless
  `cfg.use_webshare` **and** creds are set — so a system-level VLESS/VPN carries
  traffic by default (stacking Webshare on the authed subscription feed 405s).
- `download.py` — yt-dlp download + metadata; `build_opts(cfg, download_audio)`.
  `download_metadata(url, cfg)` fetches metadata only (no audio) for the
  captions-only path; uses `process=False` so meta survives the missing JS
  challenge solver (which otherwise fails format selection).
- `transcript/` — `captions.py` (youtube-transcript-api) → `whisper.py` (faster-whisper)
  fallback, orchestrated by `get_transcript`. `fetch_captions` tries `cfg.caption_langs`
  (`YT_CAPTION_LANGS`, default `en`) then falls back to ANY available track (manual
  over auto-generated), so non-English videos ingest via the fast captions path; the
  source language is stored in `transcripts.lang` (exposed as `transcript_lang` in
  `show --json`). Skills produce artifacts in the video's original language by
  default (user preference); translate only when a target language is requested.
- `discovery.py` — subscription feed extraction (`discover`), injectable `extract_fn` seam.
  Flat feed pull is capped (`playlistend=discover_feed_limit`) and stamped with
  approximate per-entry `timestamp` via `youtubetab:approximate_date` — dates in
  one call, no per-video N+1. Cutoff is epoch-based: `after_ts` (incremental
  high-water) beats `after` (YYYY-MM-DD), minus `overlap_s`; newest-first with an
  early break. `Video.published_ts` (epoch, **not** persisted — absent from
  `VideoSchema`) carries the high-water back to `run_discover`. Per-video date
  fallback (`_published_ts`, `process=False`) only fires for entries lacking an
  inline timestamp (e.g. live premieres).
- `store/` — `models.py` (dataclasses + LanceModel schemas + `chunk_schema`),
  `embeddings.py` (`build_embedder`, `chunk_segments`), `db.py` (LanceDB CRUD + search).
- `reembed` (CLI) — `run_reembed` rebuilds the `chunks` table with the current
  `build_embedder(cfg)` (via `store.rebuild_chunks`), migrating the library to a
  new embedding model without re-fetching.
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
- `frame.py` — single still-frame grab: `grab_frame(db, video_id, at_s, out_path,
  cfg=, workdir=, download_fn=, ffmpeg_fn=)` downloads a 1s 720p section at the
  timestamp (reusing `supercut`'s `_FORMAT` + `download_range_func`) and extracts
  the first frame via ffmpeg. `parse_timestamp` accepts seconds or `H:M:S`.
  Injectable seams keep it offline-testable; real yt-dlp/ffmpeg is manual smoke.
- `cli.py` — Typer app; thin `run_*` cores are the testable seam.
  `fetch --captions-only` runs the metadata+captions path
  (no audio/whisper). `run_discover` is incremental: cutoff precedence is
  explicit `--after` > stored epoch `last_discover_ts` (−`overlap_s`) > legacy
  `last_discover_at` date > 7-day default; it drops `is_seen` videos and advances
  `last_discover_ts` (never regressing) from the discovered `published_ts`.
- REST API — **moved out** to the [`yt-mem-ai-desktop`](https://github.com/dasein108/yt-mem-ai-desktop)
  repo (FastAPI backend that imports this package and reuses `cli.py`'s `run_*`/
  `open_store` cores). This repo is the engine: library + data/pipeline CLI only.
- `frontend/` — **moved out** to the standalone repo
  [`yt-mem-ai-desktop`](https://github.com/dasein108/yt-mem-ai-desktop) (React+TS
  desktop UI + Electron wrapper). It consumes this engine as a Python package
  (its FastAPI backend imports `yt_mem_ai`'s CLI cores directly) and the
  packaged app bundles the engine. This repo is the engine: library + CLI +
  skills, published to PyPI as `yt-mem-ai`.

## Store (LanceDB)

Tables: `videos`, `channels`, `transcripts`, `chunks` (embedded + FTS), `summaries`,
`feedback`, `app_state`. Video lifecycle `status`: `discovered → downloaded →
transcribed → summarized`. Live streams get a terminal `status=stream`: batch
ingestion (`fetch-pending`) detects them via yt-dlp `live_status` (`is_live`/
`is_upcoming`/`post_live`/`was_live`, see `models.is_stream`), marks them, and
**skips transcription** (they're long + usually caption-less). A direct
`yt-ai fetch <url>` transcribes a stream on demand (`run_fetch(include_streams=True)`).

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
- **Logging convention** — every runtime writes to the same file,
  `logs/common.jsonl` (one JSON object per line, gitignored, never edit by
  hand): backend via `obs.log_event`/`blog`, the frontend via
  yt-mem-ai-desktop's `src/lib/log.ts`'s `log()` (fire-and-forget `POST /log`, plus
  `installLogBridge()` auto-forwarding `console.error`/`warn` and uncaught
  errors/rejections), and Electron's main process via
  yt-mem-ai-desktop's `electron/lib.ts`'s `logLine()`/`logsPath()`. Every line has
  `{ts, source, level, event, msg, ...ctx}` with `source ∈
  backend|electron|frontend`; logging never raises. See the `yt-mem-ai-desktop`
  repo for the `yt-debugger`-style tooling to trace an issue across all three.

## Recommendations

`like`/`dislike` write the `feedback` table (latest signal per video wins); `recommend`
builds like/dislike centroids from liked/disliked videos' chunk vectors and ranks unrated
transcribed/summarized videos.

## Skills

Canonical skills live in `skills/<name>/SKILL.md` (checked in, any-LLM usable).
Claude Code only discovers skills under `.claude/skills/`, so each is surfaced
via a symlink `.claude/skills/<name> -> ../../skills/<name>` (thin ref, no drift).

- `yt-manager` — umbrella entry point for any `yt-ai` CLI op + both pipelines;
  delegates per-video analysis, digests, and reviews to `yt`.
- `yt` — scenario skill: one video → summary/highlights/Q&A/presentation
  (`slides/<id>.md`); process subscriptions → `digests/<DATE>.md`; cross-video
  subscriptions review → `reviews/<DATE>.md`. Persists via `save-summary`.

The `yt-debugger` skill (backend/electron/frontend log correlation) **moved
out** with the REST API to the `yt-mem-ai-desktop` repo.

There are two independent summarization paths, both writing the same `summaries`
table via `store.upsert_summary`: the skills-primary path above (free, via Claude
Code) and the `yt-mem-ai-desktop` backend's summarize job (OpenRouter, for the
desktop UI). Neither is authoritative over the other — last write wins.

## Commands & daily routine

See README.md. Pipeline: `discover → fetch-pending → /yt (process subscriptions) → compile`;
single video: `fetch → /yt (summarize/highlights/qa/presentation)`.

## Dev

```bash
uv sync --extra dev
uv run pytest -q                        # offline unit suite (fake embedder)
YT_RUN_INTEGRATION=1 uv run pytest -q   # + real sentence-transformers integration
uv run --with ruff ruff check .         # lint
```

TDD: tests live in `tests/`, one per module; keep them offline via the injectable seams.
Design docs in `docs/superpowers/specs/`, plans in `docs/superpowers/plans/`.
