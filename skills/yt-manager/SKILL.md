---
name: yt-manager
description: Use when the user wants to run any yt-ai operation from Claude Code — ingest a video, discover subscription uploads, batch-fetch pending, search the library, rate/recommend, compile highlights, build a supercut, check status, or run a full pipeline (daily routine or single-video). The umbrella entry point for the yt_summary CLI; delegates deep per-video analysis to [[summarize-video]] and [[daily-digest]].
---

# yt-manager

Single entry point for driving the `yt-ai` CLI (the yt_summary YouTube pipeline)
from Claude Code. Every data operation goes through the CLI — never touch the
LanceDB store directly.

## Prereqs

- Run all commands from the repo root: `/Users/dasein/dev/yt_summary`.
- Invoke via uv: `uv run yt-ai <cmd>` (the `yt-ai` entry point after `uv sync`).
- `.env` must be filled (Webshare proxy + cookies for yt-dlp, embedding backend).
- Video lifecycle status: `discovered → downloaded → transcribed → summarized`.

```bash
cd /Users/dasein/dev/yt_summary
uv run yt-ai <command> [args]
```

## Decide what the user wants, then run

### Ingest one video
```bash
uv run yt-ai fetch <url>        # download audio + transcribe + embed + store
uv run yt-ai transcript <url>   # same pipeline (alias intent)
```

### Discover + batch ingest (subscriptions)
```bash
uv run yt-ai discover [--after <DATE>] [--deep] [--min-duration <s>] [--json]
uv run yt-ai fetch-pending [--since <DATE>] [--limit <N>]   # ingest 'discovered' videos
```

### Read / query the library
```bash
uv run yt-ai list [--status <s>] [--since <DATE>] [--json]
uv run yt-ai show <video_id> [--json]     # metadata + full transcript
uv run yt-ai status                        # counts by status
uv run yt-ai search "<query>" [--hybrid|--fts|--vector] [-k <N>]
```

### Summaries (skills generate the analysis; CLI persists it)
```bash
uv run yt-ai save-summary <video_id> "<summary_md>" \
  --highlights '<json>' --qa '<json>'
```
Do **not** write summaries free-hand here. For the model-generated analysis
(summary + timestamped highlights + Q&A), hand off:
- one video → invoke **[[summarize-video]]**
- a day's batch + combined digest → invoke **[[daily-digest]]**

### Taste / recommendations
```bash
uv run yt-ai like <video_id>      # feedback table (latest signal per video wins)
uv run yt-ai dislike <video_id>
uv run yt-ai recommend [--limit <N>] [--json]   # rank unrated fetched videos by taste
```

### Compile / video output
```bash
uv run yt-ai compile [--since <DATE>] [--max-minutes <N>] [--out <path>] [--json]
# → deep-linked highlights doc compilations/<DATE>.md. Fast, no download.

uv run yt-ai supercut [--since <DATE>] [--max-minutes <N>] [--out <path>] [--keep-clips]
# → actual video reel supercuts/<date>.mp4 + .refs.md sidecar.
# Slow: re-downloads each clip (720p) + ffmpeg concat. Needs network + local ffmpeg.
```

### Local API (desktop UI backend)
```bash
uv run yt-ai serve [--host 127.0.0.1] [--port 8000]   # localhost-only FastAPI
```

## Pipelines

**Daily routine** (subscriptions → digest → clickable highlights):
```bash
uv run yt-ai discover          # new uploads → 'discovered'
uv run yt-ai fetch-pending     # download+transcribe+embed today's batch (skips failures)
```
then invoke **[[daily-digest]]** (per-video summaries + `digests/<DATE>.md`), then:
```bash
uv run yt-ai compile           # deep-linked highlights doc for the day
# optionally: uv run yt-ai supercut   # shareable video reel
```

**Single video on demand:**
```bash
uv run yt-ai fetch <url>
```
then invoke **[[summarize-video]]**.

## Conventions

- Skills-primary summarization: the CLI stores data; skills read via
  `show --json` / `search` and write via `save-summary`. Never invent
  highlight timestamps — anchor them with `uv run yt-ai search "<phrase>" --vector -k 3`.
- Dates are `YYYY-MM-DD` strings; string comparison is date comparison.
- `is_seen` is status-based (`transcribed`/`summarized`), so ingest is retry-safe;
  re-running `fetch`/`fetch-pending` is safe.
- Always report what ran + the resulting file paths (digests/compilations/supercuts) in chat.

## Notes

- If `show` prints `not found`, the video isn't ingested — run `fetch <url>` first.
- If `fetch-pending`/`list` finds nothing for a day, run `discover` first.
- `supercut` continues past a clip whose download/render fails (logged in the
  `.refs.md` sidecar's skipped list) rather than aborting.
- Related: [[summarize-video]] (one video), [[daily-digest]] (a day + cross-video digest).
```
