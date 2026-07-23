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
```

## Daily routine

```bash
yt-ai discover               # find new subscription uploads → 'discovered'
yt-ai fetch-pending          # download+transcribe+embed today's batch (robust, skips failures)
# then in Claude Code:
/daily-digest                # per-video summaries + digests/YYYY-MM-DD.md
```

Single video on demand: `yt-ai fetch <url>` then the `/summarize-video` skill.

## Tests

```bash
uv run pytest -q                       # offline unit tests (fake embedder)
YT_RUN_INTEGRATION=1 uv run pytest -q  # + real sentence-transformers integration
```
