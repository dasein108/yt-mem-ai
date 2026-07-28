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

**Configure from the CLI or an agent** — instead of editing `.env` by hand, use
`yt-ai config` (or the MCP `config_*` tools, so an agent can reconfigure itself
from chat):

```bash
yt-ai config list                  # every setting, value, and source
yt-ai config set WEBSHARE_PROXY_USERNAME <user>
yt-ai config set WEBSHARE_PROXY_PASSWORD <pass>
yt-ai config set YT_EMBEDDING_MODEL paraphrase-multilingual-MiniLM-L12-v2
yt-ai config get OPENAI_API_KEY    # secrets masked (--reveal to show)
```

`set` writes the global config file (`~/.yt-mem-ai/config.env`) by default so the
MCP server picks it up regardless of its working directory; `--project` writes
`./.env`. Precedence: process env > project `.env` > global config file, and
`config list` shows which one each value comes from.

**Embeddings:** `YT_EMBEDDING_BACKEND=local|openai`. Local uses
sentence-transformers (`YT_EMBEDDING_MODEL`, default `all-MiniLM-L6-v2`) — for
non-English libraries set `paraphrase-multilingual-MiniLM-L12-v2` (384-d, 50+
languages) so semantic search works cross-language. `openai` uses
`text-embedding-3-small|large` (needs `OPENAI_API_KEY`). After changing the model,
run `yt-ai reembed` to migrate the existing library (re-embeds all chunks; no
re-fetch).

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
yt-ai frame <video_id> --at <ts>  # still frame at a timestamp (seconds or H:M:S) → frames/<id>_<s>s.png
yt-ai reembed                # re-embed all chunks with the current YT_EMBEDDING_* config
yt-ai channel-list <url>     # list a channel's recent uploads (--limit/--from/--to/--json); enumerate only
yt-ai config list            # get/set any .env setting: config get/set/unset/path (reconfigure from CLI or chat)
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
/yt process subscriptions    # per-video summaries + digests/YYYY-MM-DD.md
yt-ai compile --out compilations/$(date +%F).md   # save the day's highlights as clickable deep links
```

`yt-ai discover` is **incremental**: it pulls the newest feed entries (one flat
call, capped by `YT_DISCOVER_FEED_LIMIT`), stamps each with an approximate
`timestamp` (yt-dlp `youtubetab:approximate_date`), and keeps only those newer
than the last run's stored high-water mark minus a 1h overlap
(`YT_DISCOVER_OVERLAP_S`) — so hour-rounded dates never miss a boundary video,
and already-processed videos (`is_seen`) are filtered out. Pass `--after
YYYY-MM-DD` to override the cutoff manually. Full per-video metadata
(description, tags, exact time) is fetched later at ingest, not during discover.

`yt-ai compile` renders a deep-linked highlights doc: each highlight from the
day's summarized videos becomes a deep link (`watch?v=ID&t=<start>s`) that jumps
straight to its moment, newest-video-first and budget-bounded by `--max-minutes`
(default 20). Fast — no downloading, just the `compile_highlights` selection as
markdown. It **prints to stdout** by default; pass `--out compilations/<DATE>.md`
to save a file.

`yt-ai supercut` renders that same highlight selection as an actual video
reel instead of a doc: it **re-downloads** each highlight's section (720p,
`yt-dlp --download-sections`), burns a label onto each clip (title/timestamp),
and concats them into one mp4 — so it needs network access and a local
`ffmpeg`, and is much slower than `compile`. Output is
`supercuts/<since-or-today>.mp4` plus a sidecar `supercuts/<...>.mp4.refs.md`
listing each rendered clip's source link (and any clips skipped because their
download/render failed). Use `compile` for a quick clickable digest; use
`supercut` when you want a shareable video.

Single video on demand: `yt-ai fetch <url>` then the `/yt` skill (summarize / highlights / qa / presentation).

## Integrations (MCP + plugins)

The whole engine is exposed as an MCP server (`yt-ai-mcp`) so **any** agentic
host can drive it — Claude Code, Claude Desktop, Codex, Gemini CLI, Cursor, …
One interactive installer wires up whichever hosts you pick (as a plugin or as a
bare MCP, in any combination):

```bash
sh integrations/install.sh                      # checkbox picker (Windows: install.ps1)
# non-interactive:
sh integrations/install.sh --claude-desktop=plugin --codex=mcp
```

Run the server directly with `uvx --from 'yt-mem-ai[mcp]' yt-ai-mcp`. Tools mirror
the CLI (`fetch`, `search`, `discover`, `compile`, …) and the `yt`/`yt-manager`
scenarios ship as MCP prompts. See [`integrations/README.md`](integrations/README.md)
(and [`integrations/PROMPT.md`](integrations/PROMPT.md) for a paste-into-any-agent
installer).

## Logging

The CLI writes structured JSON events to **`logs/common.jsonl`** (via
`obs.log_event`/`blog`) — one object per line, `{ts, source, level, event, msg,
...ctx}`. Override the path with `YT_LOG_FILE`; it's gitignored. Inspect with jq:

```bash
jq -c 'select(.level=="error")' logs/common.jsonl   # every error
tail -f logs/common.jsonl | jq -c '{ts,event,msg}'  # live tail, compact
```

## Tests

```bash
uv run pytest -q                       # offline unit tests (fake embedder)
YT_RUN_INTEGRATION=1 uv run pytest -q  # + real sentence-transformers integration
```

## Releasing (maintainers)

Version comes from the git tag (hatch-vcs). Tag, build, and publish:

```bash
git tag -a vX.Y.Z -m "vX.Y.Z" && git push origin vX.Y.Z
uv build                                # → dist/ (sdist + wheel)
sh scripts/publish.sh dist/yt_mem_ai-X.Y.Z*   # uploads to PyPI
```

`scripts/publish.sh` loads `UV_PUBLISH_TOKEN` from `.env` (gitignored) on demand,
so you don't export it each time — add `UV_PUBLISH_TOKEN=pypi-…` to `.env` once
(see `.env.example`). Equivalently: `set -a; . ./.env; set +a; uv publish dist/*`.
Rotate the token on PyPI if it's ever exposed.
