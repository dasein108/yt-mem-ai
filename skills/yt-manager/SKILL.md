---
name: yt-manager
description: Use when the user wants to run any yt-ai operation from Claude Code — ingest a video, discover subscription uploads, batch-fetch pending, search the library, rate/recommend, compile highlights, build a supercut, check status, or run a full pipeline (daily routine or single-video). The umbrella entry point for the yt-mem-ai CLI; delegates per-video analysis, digests, and reviews to [[yt]].
---

# yt-manager

Single entry point for driving the `yt-ai` CLI (the yt-mem-ai YouTube pipeline)
from Claude Code. Every data operation goes through the CLI — never touch the
LanceDB store directly.

## Prereqs

- The `yt-ai` command ships in the **yt-mem-ai** package. **Every `yt-ai <cmd>`
  example below runs equivalently as `uvx yt-mem-ai <cmd>`** — zero-install,
  cached, always latest. If `yt-ai` isn't on PATH (the native plugins don't
  install a package, they run the CLI via uvx), just prefix with `uvx`:
  `uvx yt-mem-ai fetch <url>`, `uvx yt-mem-ai search "<q>"`, etc. (A source
  checkout can also use `uv run yt-ai <cmd>`.)
- `.env` must be filled (Webshare proxy + cookies for yt-dlp, embedding backend).
  You don't have to hand-edit it: inspect and set any setting from here with
  `yt-ai config list` / `yt-ai config set KEY VALUE` (see **Configure & maintain**).
- Video lifecycle status: `discovered → transcribed → summarized` (live streams
  get a terminal `stream` and skip transcription).

```bash
yt-ai <command> [args]        # (or: uvx yt-mem-ai <command> [args])
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

### Enumerate a channel (does not ingest)
```bash
uv run yt-ai channel-list <url> [--limit <N>] [--from <DATE>] [--to <DATE>] [--json]
# newest uploads for a channel URL/@handle; feed the URLs to `fetch` to ingest a group.
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
(summary + timestamped highlights + Q&A + presentation, a subscription digest, or
a cross-video review), hand off to **[[yt]]**.

[[yt]] produces the analysis with **this agent** (Claude Code) reading the stored
transcript — no API key, no OpenRouter, no external LLM call. (The desktop app has
a separate OpenRouter-based summarize path; it is not used here.)

### Taste / recommendations
```bash
uv run yt-ai like <video_id>      # feedback table (latest signal per video wins)
uv run yt-ai dislike <video_id>
uv run yt-ai recommend [--limit <N>] [--json]   # rank unrated fetched videos by taste
```

### Configure & maintain
```bash
uv run yt-ai config list                     # every setting, value, and source
uv run yt-ai config set KEY VALUE            # e.g. WEBSHARE_PROXY_USERNAME, YT_EMBEDDING_MODEL
uv run yt-ai config get KEY [--reveal]       # secrets masked unless --reveal
uv run yt-ai config unset KEY                # remove from the config file
```
Use this to reconfigure the engine on request — set Webshare proxy creds, switch
the embedding model/backend, point at a cookies browser, change caption languages
— without hand-editing `.env`. `set` writes the global config
(`~/.yt-mem-ai/config.env`) by default; add `--project` for `./.env`. Only known
`.env` keys are accepted. After changing the embedding model/backend, migrate the
existing library:
```bash
uv run yt-ai reembed                          # re-embed all chunks with the current YT_EMBEDDING_* config
```

### Compile / video output
```bash
uv run yt-ai compile [--since <DATE>] [--max-minutes <N>] [--out <path>] [--json]
# Deep-linked highlights doc from summarized videos. Fast, no download. Prints the
# markdown to stdout by default; pass --out compilations/<DATE>.md to save a file.

uv run yt-ai supercut [--since <DATE>] [--max-minutes <N>] [--out <path>] [--keep-clips]
# → actual video reel supercuts/<date>.mp4 + .refs.md sidecar.
# Slow: re-downloads each clip (720p) + ffmpeg concat. Needs network + local ffmpeg.

uv run yt-ai frame <video_id> --at <seconds|H:M:S> [--out <path>]
# Grab one still frame from an ingested video (needs yt-dlp + ffmpeg).
# → frames/<id>_<s>s.png by default.
```

> The REST API / `serve` command moved to the **yt-mem-ai-desktop** repo
> (`yt-ai-desktop-serve`); it is not part of this engine CLI.

## Pipelines

**Daily routine** (subscriptions → digest → clickable highlights):
```bash
uv run yt-ai discover          # new uploads → 'discovered'
uv run yt-ai fetch-pending     # download+transcribe+embed today's batch (skips failures)
```
then invoke **[[yt]]** (process subscriptions → per-video summaries + `digests/<DATE>.md`), then:
```bash
uv run yt-ai compile           # deep-linked highlights doc for the day
# optionally: uv run yt-ai supercut   # shareable video reel
```

**Single video on demand:**
```bash
uv run yt-ai fetch <url>
```
then invoke **[[yt]]** (single-video summary / highlights / Q&A / presentation).

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
- Related: [[yt]] (analysis scenarios: single video, subscription digest, cross-video review).
```
