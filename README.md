# yt_summary — YouTube AI CLI

Download YouTube audio, transcribe (captions → faster-whisper fallback), store
everything in an embedded **LanceDB** with per-chunk embeddings, discover
subscription uploads, and search your library semantically. Summaries,
highlights, and Q&A are produced by Claude Code skills, not an API.

## Setup

```bash
uv sync --extra dev
cp .env.example .env   # fill WEBSHARE_* + YT_COOKIES_BROWSER; pick embedding backend
```

Config (`.env`): `YT_STORE_PATH` (LanceDB dir), `YT_EMBEDDING_BACKEND=local|openai`,
`YT_EMBEDDING_MODEL`, `YT_CHUNK_TARGET_S`, `OPENAI_API_KEY` (openai backend),
`WEBSHARE_PROXY_*`, `YT_COOKIES_BROWSER`.

**Proxy / VLESS:** `YT_USE_WEBSHARE` defaults **off**. If you already run a
system-level proxy/VPN (VLESS/Xray etc.), leave it off — traffic rides that
tunnel. Stacking the Webshare proxy on top breaks the authenticated
subscription feed (its CONNECT tunnel returns `405`). Only set
`YT_USE_WEBSHARE=true` if you have no other proxy and YouTube rate-limits your
raw IP. Discover tuning: `YT_DISCOVER_FEED_LIMIT` (newest-N cap, default 60),
`YT_DISCOVER_OVERLAP_S` (incremental overlap, default 3600), `YT_DISCOVER_TIMEOUT_S`.

## Commands

```bash
yt-ai fetch <url>            # download + transcribe + embed + store one video
yt-ai fetch <url> --captions-only  # captions only: no audio download / no whisper (fails if none)
yt-ai transcript <url>       # same pipeline
yt-ai discover               # new subscription uploads (--after/--deep/--min-duration/--json); incremental by default
yt-ai fetch-pending          # batch-fetch pending 'discovered' videos (since --since, default today; --limit)
yt-ai list                   # list stored videos (--status/--since/--json)
yt-ai show <video_id>        # metadata + transcript (--json)
yt-ai status                 # counts by status
yt-ai search "<query>"       # semantic search (--hybrid/--fts/--vector, -k N)
yt-ai save-summary <id> "<summary>" --highlights '<json>' --qa '<json>'  # persist a summary (used by skills)
yt-ai like <video_id>        # mark liked (feeds recommendations)
yt-ai dislike <video_id>     # mark disliked
yt-ai recommend              # rank your unrated fetched videos by taste (--limit/--json)
yt-ai compile                 # deep-linked highlights doc, budget-bounded (--since/--max-minutes/--json/--out)
yt-ai supercut                 # video reel of highlights, re-downloaded + labeled (--since/--max-minutes/--out/--keep-clips)
```

## Rate & recommend

Like/dislike videos you've fetched (`yt-ai like <id>` / `dislike <id>`), then
`yt-ai recommend` ranks your other fetched-but-unrated videos by similarity to
what you liked (minus what you disliked), using their transcript embeddings.
Before you've liked anything, it falls back to most-recently-published.

## Daily routine

```bash
yt-ai discover               # find new subscription uploads → 'discovered'
yt-ai fetch-pending          # download+transcribe+embed today's batch (robust, skips failures)
# then in Claude Code:
/daily-digest                # per-video summaries + digests/YYYY-MM-DD.md
yt-ai compile                # compile the day's highlights into a deep-linked markdown you can click into
```

`yt-ai discover` is **incremental**: it pulls the newest feed entries (one flat
call, capped by `YT_DISCOVER_FEED_LIMIT`), stamps each with an approximate
`timestamp` (yt-dlp `youtubetab:approximate_date`), and keeps only those newer
than the last run's stored high-water mark minus a 1h overlap
(`YT_DISCOVER_OVERLAP_S`) — so hour-rounded dates never miss a boundary video,
and already-processed videos (`is_seen`) are filtered out. Pass `--after
YYYY-MM-DD` to override the cutoff manually. Full per-video metadata
(description, tags, exact time) is fetched later at ingest, not during discover.

`yt-ai compile` builds `compilations/<DATE>.md`: each highlight from the day's
summarized videos becomes a deep link (`watch?v=ID&t=<start>s`) that jumps
straight to its moment, newest-video-first and budget-bounded by
`--max-minutes` (default 20). Fast — no downloading, just the same
`compile_highlights` selection rendered as markdown.

`yt-ai supercut` renders that same highlight selection as an actual video
reel instead of a doc: it **re-downloads** each highlight's section (720p,
`yt-dlp --download-sections`), burns a label onto each clip (title/timestamp),
and concats them into one mp4 — so it needs network access and a local
`ffmpeg`, and is much slower than `compile`. Output is
`supercuts/<since-or-today>.mp4` plus a sidecar `supercuts/<...>.mp4.refs.md`
listing each rendered clip's source link (and any clips skipped because their
download/render failed). Use `compile` for a quick clickable digest; use
`supercut` when you want a shareable video.

Single video on demand: `yt-ai fetch <url>` then the `/summarize-video` skill.

## Desktop UI (dev)

One command starts the whole dev stack — the local API plus the Vite dev server
(which proxies `/api` to the API) — and Ctrl-C stops both:

```bash
./dev.sh                    # UI at http://localhost:5173, API at :8000
YT_API_PORT=8010 ./dev.sh   # API on a different port (Vite proxy follows)
```

## Local API (SP4)

```bash
yt-ai serve [--host 127.0.0.1] [--port 8000]   # localhost-only FastAPI server
```

Backend for the desktop UI. Wraps the same `run_*` cores as the CLI. Jobs run on
a bounded thread pool, are persisted in a `jobs` table, and unfinished ones are
re-enqueued on restart; subscriptions auto-sync hourly (`YT_DISCOVER_INTERVAL_S`).

Read endpoints:

```
GET /videos                # paged {items,total} (?status=&since=&limit=30&offset=0)
GET /videos/{video_id}     # metadata + transcript + summary
GET /status                # counts by status
GET /search                # semantic search (?q=&mode=hybrid|fts|vector&k=10)
GET /recommend             # ranked unrated videos (?limit=20)
```

Write / job endpoints:

```
POST /feedback              # like/dislike a video ({video_id, signal})
POST /jobs/fetch            # download+transcribe+embed one video ({url, force})
POST /jobs/discover         # find new subscription uploads ({after, deep, min_duration})
POST /jobs/fetch-pending    # batch-fetch pending 'discovered' videos ({since, limit})
POST /jobs/summarize        # summarize a fetched video via OpenRouter ({video_id})
GET  /jobs/{job_id}         # poll a job's status/result
GET  /jobs                  # list all jobs
POST /log                   # ingest a frontend log line ({event, level, msg, ctx}) -> logs/common.jsonl
```

`POST /jobs/summarize` is the API's summarization path (distinct from the
`/summarize-video` skill): it calls OpenRouter using `OPENROUTER_API_KEY` and
`YT_OPENROUTER_MODEL` (`.env`) and writes the same `summaries` table.

## Desktop UI (SP4b)

A browser-first React UI over the local API lives in `frontend/`:

```bash
yt-ai serve             # local API, in one terminal
cd frontend
npm install
npm run dev             # Vite on http://localhost:5173, proxies /api -> 127.0.0.1:8000
```

MVP scope: Library, Detail (summary/highlights/Q&A + like/dislike/Summarize),
Search, and a Jobs strip. Recommend/Digest views are not part of this UI yet.
See `frontend/README.md` for details and dev scripts
(`test`/`build`/`typecheck`/`lint`).

## Desktop app (SP4c)

The frontend can also run as a native Electron app instead of a browser tab.
The Electron shell wraps the SP4b UI above and manages the SP4a API as a
sidecar process (auto-spawns `uv run yt-ai serve`, waits for it to come up,
and stops it on quit); the API now allows CORS so the packaged renderer
(loaded from `file://` / a custom scheme) can reach it. Minimizing hides to
the system tray; a video's **Watch** button plays it in-app.

```bash
cd frontend
npm run electron:dev     # dev: auto-starts the sidecar + opens the window
npm run electron:build   # package a current-OS installer into frontend/release/
```

See `frontend/README.md` → "Electron desktop app" for the full env-var
overrides, tray behavior, and the manual smoke-test checklist. Cross-platform
installers, code signing, and bundling Python into the package are deferred.

## Debugging

Backend (`obs.log_event`/`blog`), Electron main process (`logLine`), and the
frontend (`log()` + an auto-capture bridge over `console.error`/`warn` and
uncaught errors/rejections, POSTing to `POST /log`) all append to one unified,
append-only log: **`logs/common.jsonl`** — one JSON object per line,
`{ts, source, level, event, msg, ...ctx}` with `source ∈ backend|electron|frontend`.
Path defaults to `logs/common.jsonl`, overridable via `YT_LOG_FILE` (backend only;
Electron/frontend always write to the repo's `logs/common.jsonl`). It's
gitignored — delete/rotate it manually if it grows.

Use the **`yt-debugger`** skill (`skills/yt-debugger/SKILL.md`) to diagnose an
issue end-to-end: it runs the backend, introspects `/openapi.json`, probes
endpoints, and gives jq recipes to filter the log by source/level/event/job_id.
Two starter one-liners:

```bash
jq -c 'select(.level=="error")' logs/common.jsonl              # every error, any runtime
tail -f logs/common.jsonl | jq -c '{ts,source,event,msg}'       # live tail, compact
```

## Tests

```bash
uv run pytest -q                       # offline unit tests (fake embedder)
YT_RUN_INTEGRATION=1 uv run pytest -q  # + real sentence-transformers integration
```
