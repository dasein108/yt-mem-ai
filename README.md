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

## Commands

```bash
yt-ai fetch <url>            # download + transcribe + embed + store one video
yt-ai transcript <url>       # same pipeline
yt-ai discover               # list new subscription uploads (--after/--deep/--min-duration/--json)
yt-ai fetch-pending          # batch-fetch pending 'discovered' videos (since --since, default today; --limit)
yt-ai list                   # list stored videos (--status/--since/--json)
yt-ai show <video_id>        # metadata + transcript (--json)
yt-ai status                 # counts by status
yt-ai search "<query>"       # semantic search (--hybrid/--fts/--vector, -k N)
yt-ai save-summary <id> "<summary>" --highlights '<json>' --qa '<json>'  # persist a summary (used by skills)
yt-ai like <video_id>        # mark liked (feeds recommendations)
yt-ai dislike <video_id>     # mark disliked
yt-ai recommend              # rank your unrated fetched videos by taste (--limit/--json)
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
```

Single video on demand: `yt-ai fetch <url>` then the `/summarize-video` skill.

## Local API (SP4)

```bash
yt-ai serve [--host 127.0.0.1] [--port 8000]   # localhost-only FastAPI server
```

Backend for the future desktop UI. Wraps the same `run_*` cores as the CLI over
an in-memory job queue (jobs run in a background thread, not persisted).

Read endpoints:

```
GET /videos                # list stored videos (?status=&since=)
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

## Tests

```bash
uv run pytest -q                       # offline unit tests (fake embedder)
YT_RUN_INTEGRATION=1 uv run pytest -q  # + real sentence-transformers integration
```
