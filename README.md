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

## Integrations (native plugins + MCP)

Two ways to reach the engine, per host:

- **Native skills** for Claude Code, Codex, Cursor, Antigravity — and **Claude
  Desktop** (via a plugin; 2026 plugin-bundled skills work in Desktop chat /
  claude.ai / Cowork). The `yt` / `yt-manager` skills drive the `yt-ai` CLI via
  `uvx yt-mem-ai <cmd>` (zero-install) and auto-trigger on "summarize this video".
- **The `yt-ai-mcp` MCP server** is an optional typed-tool surface on any host
  (Cursor, Antigravity, Claude Code/Desktop config, headless). The plugin/skills
  is the recommended path; MCP is there if you want the raw tools.

One interactive installer wires up whichever you pick — arrow-key checkbox UI,
pre-checks already-installed targets, untick to uninstall:

```bash
sh integrations/install.sh                      # checkbox picker (Windows: install.ps1)
# non-interactive:
sh integrations/install.sh --cursor=skills,mcp --claude-desktop=mcp
```

See [`integrations/README.md`](integrations/README.md) (and
[`integrations/PROMPT.md`](integrations/PROMPT.md) for a paste-into-any-agent
installer).

### Install as an MCP plugin (any host)

The engine ships one MCP server — `yt-ai-mcp`, stdio transport — so any
MCP-capable host (Claude Desktop/Code, Cursor, Antigravity, Codex, Zed,
Continue, LibreChat, your own client…) can use it with a single config entry.

```bash
# persistent binary (recommended for GUI hosts — no uvx cold start)
uv tool install 'yt-mem-ai[mcp]'
which yt-ai-mcp        # → absolute path used in the config below

# or run it zero-install (fine for CLI hosts)
uvx --from 'yt-mem-ai[mcp]' yt-ai-mcp
```

Generic `mcpServers` entry — the shape every host accepts (file location
differs: `~/.cursor/mcp.json`, `~/.gemini/config/mcp_config.json`,
`claude_desktop_config.json`, `.mcp.json`, …):

```json
{
  "mcpServers": {
    "yt-mem-ai": {
      "command": "/absolute/path/to/yt-ai-mcp",
      "args": [],
      "env": { "YT_STORE_PATH": "/absolute/path/to/.yt-mem-ai/lance" }
    }
  }
}
```

Zero-install variant (no `uv tool install`): `"command": "uvx"`,
`"args": ["--from", "yt-mem-ai[mcp]", "yt-ai-mcp"]`.

Use **absolute paths** — GUI hosts launch the server with an arbitrary cwd and a
minimal `PATH`. No `env` block is required: settings are read from
`~/.yt-mem-ai/config.env`, which the agent itself can write via the `config_set`
tool (or you via `yt-ai config set`).

**Tools:** `fetch`, `show`, `status`, `list_videos`, `search`, `save_summary`,
`discover`, `fetch_pending`, `channel_list`, `like`, `dislike`, `recommend`,
`compile`, `supercut`, `frame`, `reembed`, `config_list`, `config_get`,
`config_set`, `config_unset`.
**Prompts:** `yt_summarize`, `yt_highlights`, `yt_qa`, `yt_presentation`,
`yt_digest`, `yt_review`, `yt_group` — the same playbooks as the skills, so
hosts without skill support still get the full workflows.

Details: [`integrations/mcp/README.md`](integrations/mcp/README.md).

## Use as a Python package

`yt-mem-ai` is a normal library — the CLI is a thin Typer shell over `run_*`
cores you can call directly. Everything is local: no server, no API key (unless
you pick the `openai` embedding backend).

```bash
pip install yt-mem-ai     # or: uv add yt-mem-ai
```

```python
from dataclasses import replace
from pathlib import Path

from yt_mem_ai.config import load_config
from yt_mem_ai.cli import open_store, run_fetch, run_search, run_list, run_save_summary
from yt_mem_ai.store import db as store

# Config comes from ~/.yt-mem-ai/config.env < ./.env < process env.
# Override any field in code (Config is a frozen dataclass):
cfg = replace(load_config(), store_path=Path("~/.yt-mem-ai/lance").expanduser())

db = open_store(cfg)          # opens LanceDB + creates tables/indexes once
                              # pass db=... to every run_* call to reuse it

# 1. Ingest: download → transcribe (captions → whisper) → chunk → embed → store
video_id = run_fetch("https://www.youtube.com/watch?v=dQw4w9WgXcQ", cfg, db=db)
# captions only (no audio download, no whisper):
# video_id = run_fetch(url, cfg, db=db, captions_only=True)

# 2. Read what was stored
video = store.get_video(db, video_id)
text = store.get_transcript_text(db, video_id)
print(video.title, video.channel, video.duration_s, len(text or ""))

for c in store.list_chunks(db, video_id)[:3]:
    print(f"[{c['start_s']:.0f}s] {c['text'][:80]}")

# 3. Semantic search across the whole library (hybrid | vector | fts)
for hit in run_search(cfg, "retrieval augmented generation", mode="hybrid", k=5, db=db):
    print(hit["video_id"], hit["start_s"], hit["text"][:100])

# 4. Bring your own LLM: summarize the transcript however you like, then persist
summary_md = my_llm(text)                       # any model / provider
run_save_summary(
    cfg, video_id, summary_md,
    highlights_json='[{"t": 42, "text": "key moment"}]',
    qa_json='[{"q": "What is it about?", "a": "..."}]',
    db=db,
)
print(store.get_summary(db, video_id))

# 5. Library queries
for v in run_list(cfg, status="transcribed", since="2026-01-01", db=db):
    print(v.video_id, v.published_at, v.title)
```

Other cores, same shape (`run_x(cfg, ..., db=db)`): `run_discover`,
`run_fetch_pending`, `run_channel_list`, `run_recommend`, `run_feedback`,
`run_compile`, `run_supercut`, `run_frame`, `run_reembed`. Lower-level pieces
are importable too — `yt_mem_ai.download.download`, `yt_mem_ai.transcript.get_transcript`,
`yt_mem_ai.store.embeddings.build_embedder` / `chunk_segments`,
`yt_mem_ai.store.db` (LanceDB CRUD + `search_chunks`).

The store is plain LanceDB, so you can also open it directly:

```python
import lancedb
from pathlib import Path
tbl = lancedb.connect(Path("~/.yt-mem-ai/lance").expanduser()).open_table("chunks")
df = tbl.to_pandas()      # video_id, start_s, end_s, text, vector
```

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
