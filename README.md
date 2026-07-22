# yt_summary — YouTube AI CLI

Download YouTube audio, transcribe (captions → faster-whisper fallback), store
everything in an embedded **LanceDB** with per-chunk embeddings, and search your
library semantically. Summaries/highlights/Q&A are produced by a Claude Code skill.

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
yt-ai fetch <url>            # download + transcribe + embed + store
yt-ai transcript <url>       # same pipeline
yt-ai show <video_id>        # metadata + transcript ( --json for machine output )
yt-ai status                 # counts by status
yt-ai search "<query>"       # semantic search ( --hybrid | --fts | --vector, -k N )
yt-ai save-summary <id> ...  # used by the summarize-video skill
```

## Summaries

After `fetch`, invoke the **summarize-video** Claude Code skill with a `video_id`;
it reads the transcript via `yt-ai show --json`, anchors highlights with
`yt-ai search`, and writes results back with `yt-ai save-summary`.

## Tests

```bash
uv run pytest -q                       # offline unit tests (fake embedder)
YT_RUN_INTEGRATION=1 uv run pytest -q  # + real sentence-transformers integration
```
