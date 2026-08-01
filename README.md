# yt-mem-ai — a local YouTube memory for your AI assistant

Give Claude, Codex, Cursor, or any MCP host the ability to **watch YouTube for
you**: transcribe videos, remember them, follow your subscriptions, and turn all
of it into summaries, timestamped highlights, Q&A, digests, and video reels.
Everything runs on your machine — no cloud service, no API key.

![Installing the yt skills for Codex in one command](https://raw.githubusercontent.com/dasein108/yt-mem-ai/main/docs/demo/codex-install.gif)

<p align="center"><i>One command, two questions — here it's wiring the skills into Codex.</i></p>

**Example** — *"make a presentation from [this video](https://www.youtube.com/watch?v=96jN2OCOfLs)"*
(Andrej Karpathy: From Vibe Coding to Agentic Engineering, Sequoia, 30 min) →
**[13 slides, PDF](https://github.com/dasein108/yt-mem-ai/blob/main/docs/demo/karpathy-agentic-engineering.pdf)**,
every quote timestamped from the transcript. Ingest to deck in one request.

## Table of Contents

* [Features](#features)
* [How to install](#how-to-install)
* [Getting Started](#getting-started)
* [Usage](#usage)
* [Configuration](#configuration)
* [Under the hood](#under-the-hood)

## Features

* 🎧 **Transcribes any video** — YouTube captions when they exist (fast, any
  language), offline Whisper when they don't.
* 🧠 **Remembers what you watched** — every transcript is stored and indexed
  locally, so your library stays searchable forever. Nothing leaves your machine.
* 🔎 **Finds the moment** — ask "what did that video say about X" and get the
  answer with a timestamp you can jump to.
* 📡 **Follows your subscriptions** — picks up new uploads and turns the day into
  one digest.
* ✍️ **Your assistant does the writing** — summaries, highlights, Q&A, slide
  decks, all in the video's own language, using the model you already pay for.
* ❤️ **Learns your taste** — like or dislike videos and get recommendations from
  your own library.
* 🎬 **Makes media too** — clickable highlight docs, still frames, and rendered
  supercut reels.
* 🔌 **Works with your tools** — Claude Code, Claude Desktop, Codex, Cursor,
  Antigravity, OpenClaw, Hermes: skills or MCP, your pick.

## How to install

### 1. Connect your assistant ⭐

```bash
curl -LsSf https://raw.githubusercontent.com/dasein108/yt-mem-ai/main/install.sh | sh
```

An interactive wizard opens. Pick what you want, tick your apps, press enter:

```
step 1/2 — what (pick one)     step 2/2 — where (tick any)
> Plugin  skills + CLI         [x] Claude Code    [ ] Claude Desktop
  MCP     typed tools          [x] Codex          [ ] Cursor
                               [ ] Antigravity    [ ] OpenClaw   [ ] Hermes
```

**Plugin** teaches your assistant to act on plain requests — *"summarize this
video"*. **MCP** gives it a set of tools instead. Not sure? Start with Plugin;
you can run the wizard again for the other.

It installs everything it needs, ticks what you already have, and removes
anything you untick (it shows a plan and asks first). Then **restart the app**
and try: *summarize 'https://youtu.be/…'*.

Already know what you want? Skip the questions:

```bash
curl -LsSf https://raw.githubusercontent.com/dasein108/yt-mem-ai/main/install.sh \
  | sh -s -- --plugin --claude-code --codex
curl -LsSf https://raw.githubusercontent.com/dasein108/yt-mem-ai/main/install.sh \
  | sh -s -- --mcp --claude-desktop --cursor
```

Hosts: `--claude-code` `--claude-desktop` `--codex` `--cursor` `--antigravity`
`--openclaw` `--hermes`, or `--all`. Full flag list and uninstall notes:
[`integrations/README.md`](integrations/README.md). Rather have an agent do it?
Paste [`integrations/PROMPT.md`](integrations/PROMPT.md) into any assistant.

### 2. MCP by hand — one config entry, self-installing

No prior install needed: `uvx` fetches the package the first time the host
launches the server, and keeps it cached afterwards. Drop this into your host's
MCP config:

```json
{
  "mcpServers": {
    "yt-mem-ai": {
      "command": "uvx",
      "args": ["--from", "yt-mem-ai[mcp]", "yt-ai-mcp"]
    }
  }
}
```

That's the whole setup — no paths, no `env` block. Settings live in
`~/.yt-mem-ai/config.env` and the agent can write them itself with the
`config_set` tool (or you with `yt-ai config set`).

| Host | Where that JSON goes |
|---|---|
| **Claude Desktop** | macOS `~/Library/Application Support/Claude/claude_desktop_config.json` · Windows `%APPDATA%\Claude\claude_desktop_config.json` — restart the app |
| **Claude Code** | `claude mcp add -s user yt-mem-ai -- uvx --from 'yt-mem-ai[mcp]' yt-ai-mcp` |
| **Cursor** | `~/.cursor/mcp.json` (reload Cursor) |
| **Antigravity** | `~/.gemini/config/mcp_config.json` (restart) |
| **Codex** | `~/.codex/config.toml` — TOML, see below (or `codex mcp add yt-mem-ai -- uvx --from 'yt-mem-ai[mcp]' yt-ai-mcp`) |
| **OpenClaw** | `openclaw mcp add yt-mem-ai --command uvx --arg --from --arg 'yt-mem-ai[mcp]' --arg yt-ai-mcp` (or `~/.openclaw/openclaw.json` → `mcp.servers`) |
| **Hermes** | `~/.hermes/config.yaml` under `mcp_servers:` — YAML, see below |

```toml
# ~/.codex/config.toml
[mcp_servers.yt-mem-ai]
command = "uvx"
args = ["--from", "yt-mem-ai[mcp]", "yt-ai-mcp"]
```

```yaml
# ~/.hermes/config.yaml
mcp_servers:
  yt-mem-ai:
    command: "uvx"
    args: ["--from", "yt-mem-ai[mcp]", "yt-ai-mcp"]
    enabled: true
```

Restart the app and the tools show up — see [Usage](#mcp-tools) for what they do.

> **Nothing appeared, or the host timed out?** The first launch downloads
> dependencies and can outlast the host's startup check. Run
> `uvx --from 'yt-mem-ai[mcp]' yt-ai-mcp --help` once, then reopen the app. If
> the host still can't start it, give it absolute paths — `uv tool install
> 'yt-mem-ai[mcp]'` and use `which yt-ai-mcp` as `command` with `"args": []`
> (GUI apps often don't see `~/.local/bin` on their `PATH`).

### 3. Claude Desktop — skills (in the app)

Desktop stores plugins on your Claude **account**, not on disk, so nothing can
install them for you. It takes a minute in the app:

> **Customize** (left sidebar) → **Plugins** → *Personal plugins* → **+** →
> **Add marketplace** → **Add from a repository** →
> `https://github.com/dasein108/yt-mem-ai` → **Add** → **Install** `yt-mem-ai`

Then ask: *summarize 'https://youtu.be/…'*. Uninstall the same way. The same
plugin also works on **claude.ai** and **Cowork**. Prefer tools over skills? The
MCP setup above works for Desktop too — and that one *can* be scripted.

<details>
<summary><b>Skills by hand — Codex, Cursor, Antigravity, OpenClaw, Hermes</b></summary>

Each host loads `SKILL.md` files from a user-scope directory: Codex
`~/.codex/skills/` (CLI and IDE share it, v0.117.0+), Cursor `~/.cursor/skills/`,
Antigravity `~/.gemini/skills/`, OpenClaw `~/.agents/skills/`, Hermes
`~/.hermes/skills/` (where they become `/yt` and `/yt-agent`).

```bash
# from a checkout
cp -R skills/yt skills/yt-agent ~/.codex/skills/

# without a checkout
for s in yt yt-agent; do
  mkdir -p ~/.codex/skills/$s
  curl -LsSf "https://raw.githubusercontent.com/dasein108/yt-mem-ai/main/skills/$s/SKILL.md" \
    -o ~/.codex/skills/$s/SKILL.md
done
```

Codex extras: the `/yt-*` prompts (`integrations/codex/prompts/*.md` →
`~/.codex/prompts/`) and `integrations/codex/AGENTS.md` → `~/.codex/AGENTS.md`.
Full guide: [`skills/README.md`](skills/README.md).
</details>

### 4. The CLI on its own

The skills drive it, but it's a perfectly good standalone tool:

```bash
uvx yt-mem-ai --help          # zero-install run
uv tool install yt-mem-ai     # or install the persistent `yt-ai` command
```

Needs Python 3.11+ and [uv](https://docs.astral.sh/uv/); `ffmpeg` only for
`supercut` / `frame`.

The desktop UI lives in a separate repo:
**[yt-mem-ai-desktop](https://github.com/dasein108/yt-mem-ai-desktop)** — it
depends on this package and runs its own local REST API.

## Getting Started

Installed and host restarted? You're ready. Just talk to your assistant — the
skills (or MCP prompts + `analyze_video`) do the ingesting for you:

> **"Summarize https://youtu.be/dQw4w9WgXcQ"**
> → ingests the video (captions → whisper), then writes an executive summary
> plus key points, in the video's own language.

> **"Give me the highlights of that video with timestamps"**
> → 3–8 deep-linked moments (`watch?v=…&t=123s`) anchored by semantic search.

> **"What did I watch about retrieval-augmented generation?"**
> → searches every transcript in your library and quotes the moments.

> **"Process my subscriptions into today's digest"**
> → discovers new uploads, ingests them, writes `digests/<DATE>.md`.

Prefer the terminal? The same first run:

```bash
yt-ai fetch 'https://www.youtube.com/watch?v=VIDEO_ID'   # ingest one video
yt-ai search "what was said about embeddings"            # search your library
yt-ai status                                             # what's in the store
```

Everything lands in `~/.yt-mem-ai/` (library, logs, downloads).

**Daily routine**

```bash
yt-ai discover               # what's new in your subscriptions
yt-ai fetch-pending          # transcribe today's batch
```
then in your assistant: *"process subscriptions"* → per-video summaries and
`digests/<DATE>.md`, and optionally
`yt-ai compile --out compilations/$(date +%F).md` for the day's highlights as
clickable links.

## Usage

### Talking to your assistant (skills & prompts)

Two skills ship with the plugin. MCP hosts get the same playbooks as prompts
(`yt_summarize`, `yt_highlights`, `yt_qa`, `yt_presentation`, `yt_digest`,
`yt_review`, `yt_group`), so nothing is lost without skill support.

| Skill | Use it for |
|---|---|
| **`yt`** | the entry point — any operation and the full pipelines (daily routine, single video); hands analysis to `yt-agent` |
| **`yt-agent`** | the scenarios — one video → summary / highlights / Q&A / presentation; subscriptions → daily digest; a cross-video review; a group of videos |

| What you say | What happens | Where it lands |
|---|---|---|
| "summarize `<url>`" | ingest → executive summary + key points | chat, `save_summary` in the store |
| "highlights for `<url>`" | 3–8 timestamped, deep-linked moments | chat + store |
| "Q&A about `<url>`" | 3–6 grounded question/answer pairs | chat + store |
| "make a presentation from `<url>`" | `---`-separated slide deck | `slides/<id>.md` |
| "process subscriptions" | discover → ingest → per-video analysis | `digests/<DATE>.md` |
| "review what I watched this week" | cross-video themes essay | `reviews/<DATE>.md` |
| "analyze these videos: `<ids/urls/channel>`" | ingest a set → per-video + synthesis | `groups/<label>.md` |

Skills never touch the database directly — they call the CLI, so the same
workflow runs on any host. Install or paste them by hand:
[`skills/README.md`](skills/README.md).

### MCP tools

The `yt-ai-mcp` server exposes the whole engine as typed tools. `analyze_video`
is the one-step entry point: it ingests and returns the transcript so the model
can write the summary itself.

| Category | Tool | Description |
|---|---|---|
| **Analyze** | `analyze_video` | Ingest a video and return its transcript (+ title, channel, language, existing summary). Call this first for any summarize / highlight / Q&A request. |
| **Ingest** | `fetch` | Download + transcribe + embed one video (`force`, `captions_only`, `prefer_whisper`). |
| | `discover` | New uploads from your subscription feed (incremental; `after`, `deep`, `min_duration`). |
| | `fetch_pending` | Batch-ingest everything discovered since a date. |
| | `channel_list` | Enumerate a channel's recent uploads (no ingest). |
| **Library** | `search` | Hybrid / vector / FTS search over every chunk, with timestamps. |
| | `show` | Metadata + full transcript for one video. |
| | `list_videos` | List stored videos by status / date / channel. |
| | `status` | Counts by lifecycle status. |
| **Summaries** | `save_summary` | Persist a summary + highlights + Q&A so `compile` and `supercut` can use them. |
| **Taste** | `like` / `dislike` | Record feedback for one video. |
| | `recommend` | Rank unrated videos by similarity to what you liked. |
| **Media** | `compile` | Deep-linked highlights doc, budget-bounded by minutes. |
| | `supercut` | Render the highlight selection into one labeled mp4 (needs ffmpeg + network). |
| | `frame` | Grab a still frame at a timestamp. |
| **Config** | `config_list` / `config_get` | Inspect settings, values, and where each came from (secrets masked). |
| | `config_set` / `config_unset` | Change settings from chat — proxy creds, cookies browser, embedding model. |
| **Maintenance** | `reembed` | Re-embed the whole library after changing the embedding model. |

Server details, prompt list, and raw config: [`integrations/mcp/README.md`](integrations/mcp/README.md).

### CLI commands

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
yt-ai compile                # deep-linked highlights doc, budget-bounded (--since/--max-minutes/--json/--out)
yt-ai supercut               # video reel of highlights, re-downloaded + labeled (--since/--max-minutes/--out/--keep-clips)
yt-ai frame <video_id> --at <ts>  # still frame at a timestamp (seconds or H:M:S) → frames/<id>_<s>s.png
yt-ai reembed                # re-embed all chunks with the current YT_EMBEDDING_* config
yt-ai channel-list <url>     # list a channel's recent uploads (--limit/--from/--to/--json); enumerate only
yt-ai config list            # get/set any .env setting: config get/set/unset/path (reconfigure from CLI or chat)
```

## Configuration

**Nothing is required to start** — defaults put the store, logs, and downloads
under `~/.yt-mem-ai/` and use a local embedding model. Tune it when you need to:

| Setting | What it does |
|---|---|
| `YT_STORE_PATH` | LanceDB directory |
| `YT_EMBEDDING_BACKEND` | `local` (sentence-transformers) or `openai` |
| `YT_EMBEDDING_MODEL` | e.g. `paraphrase-multilingual-MiniLM-L12-v2` for non-English libraries |
| `OPENAI_API_KEY` | only for the `openai` embedding backend |
| `YT_COOKIES_BROWSER` | `chrome`/`firefox`/… — fixes YouTube's "confirm you're not a bot" |
| `YT_CAPTION_LANGS` | preferred caption languages (default `en`, falls back to any track) |
| `WEBSHARE_PROXY_*`, `YT_USE_WEBSHARE` | optional rotating proxy |
| `YT_CHUNK_TARGET_S` | chunk length for embeddings |

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

## Under the hood

Everything below is optional reading — internals, tuning, and developer notes.

### How it works

```
yt-dlp → captions (or Whisper) → chunks → embeddings → LanceDB
                                                          ↓
                     your assistant reads + writes summaries back
```

The CLI does the heavy IO and owns the store; the skills and MCP tools are thin
callers. A video moves through `discovered → downloaded → transcribed →
summarized`; live streams get a terminal `stream` status and are skipped by batch
ingestion (transcribe one on demand with `yt-ai fetch <url>`). Storage is an
embedded **LanceDB** (`videos`, `channels`, `transcripts`, `chunks`, `summaries`,
`feedback`), with per-chunk vectors plus a full-text index — that's what makes
search hybrid.

### Command details

**Rate & recommend** — like/dislike videos you've fetched, then `yt-ai
recommend` ranks the rest by similarity to what you liked (minus what you
disliked), using their transcript embeddings. Before you've liked anything it
falls back to most-recently-published.

**`discover` is incremental** — it pulls the newest feed entries in one flat
call (capped by `YT_DISCOVER_FEED_LIMIT`), stamps each with an approximate
timestamp, and keeps only those newer than the last run's high-water mark minus
a 1h overlap (`YT_DISCOVER_OVERLAP_S`), so hour-rounded dates never miss a
boundary video. Already-processed videos are filtered out. `--after YYYY-MM-DD`
overrides the cutoff.

**`compile` vs `supercut`** — `compile` renders the day's highlights as markdown
deep links (`watch?v=ID&t=<start>s`), newest-video-first and bounded by
`--max-minutes` (default 20); it's instant and prints to stdout unless you pass
`--out`. `supercut` re-downloads each highlight's section at 720p, burns a label
onto it, and concatenates everything into `supercuts/<date>.mp4` plus a
`.refs.md` sidecar listing sources (and any clips skipped after a failure) — much
slower, needs network + `ffmpeg`, but shareable.

### Embeddings, proxy, and other tuning

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

**Working from a checkout?** `uv sync --extra dev`, then `cp .env.example .env`
if you'd rather keep settings project-local than in `~/.yt-mem-ai/config.env`.

### Use as a Python package

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

### Logging

The CLI writes structured JSON events to **`logs/common.jsonl`** (via
`obs.log_event`/`blog`) — one object per line, `{ts, source, level, event, msg,
...ctx}`. Override the path with `YT_LOG_FILE`; it's gitignored. Inspect with jq:

```bash
jq -c 'select(.level=="error")' logs/common.jsonl   # every error
tail -f logs/common.jsonl | jq -c '{ts,event,msg}'  # live tail, compact
```

### Tests

```bash
uv run pytest -q                       # offline unit tests (fake embedder)
YT_RUN_INTEGRATION=1 uv run pytest -q  # + real sentence-transformers integration
```

### Releasing (maintainers)

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
