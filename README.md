# yt-mem-ai — YouTube AI CLI

## Install

```bash
# zero-install run (recommended)
uvx yt-mem-ai --help

# or bootstrap uv + warm the cache
curl -LsSf https://raw.githubusercontent.com/dasein108/yt-mem-ai/main/install.sh | sh
```

The desktop UI lives in a separate repo: **[yt-mem-ai-desktop](https://github.com/dasein108/yt-mem-ai-desktop)**.
It depends on this `yt-mem-ai` package and runs its own local REST API.

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

## REST API & desktop app

The local REST API and the desktop UI live in the companion repo
**[yt-mem-ai-desktop](https://github.com/dasein108/yt-mem-ai-desktop)** — a full-stack app
(FastAPI backend + React/Electron UI) that depends on this `yt-mem-ai` package and
reuses its CLI cores. Install `yt-mem-ai` (`uvx yt-mem-ai` / `pip install yt-mem-ai`) and see
that repo to run the API and UI.

## Debugging

Backend (`obs.log_event`/`blog`), Electron main process (`logLine`), and the
frontend (`log()` + an auto-capture bridge over `console.error`/`warn` and
uncaught errors/rejections, POSTing to `POST /log`) all append to one unified,
append-only log: **`logs/common.jsonl`** — one JSON object per line,
`{ts, source, level, event, msg, ...ctx}` with `source ∈ backend|electron|frontend`.
Path defaults to `logs/common.jsonl`, overridable via `YT_LOG_FILE` (backend only;
Electron/frontend always write to the repo's `logs/common.jsonl`). It's
gitignored — delete/rotate it manually if it grows.

The **`yt-debugger`** skill (end-to-end backend/electron/frontend log
correlation) moved with the REST API to the
[yt-mem-ai-desktop](https://github.com/dasein108/yt-mem-ai-desktop) repo. Two starter
one-liners for filtering the log directly:

```bash
jq -c 'select(.level=="error")' logs/common.jsonl              # every error, any runtime
tail -f logs/common.jsonl | jq -c '{ts,source,event,msg}'       # live tail, compact
```

## Tests

```bash
uv run pytest -q                       # offline unit tests (fake embedder)
YT_RUN_INTEGRATION=1 uv run pytest -q  # + real sentence-transformers integration
```
