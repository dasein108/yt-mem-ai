# CLAUDE.md — yt-mem-ai

Guidance for Claude Code (and any LLM) working in this repo.

## What this is

A local-first YouTube AI CLI (`yt-ai`): download audio, transcribe (captions →
faster-whisper fallback), store everything in an embedded LanceDB with per-chunk
embeddings, discover subscription uploads, and produce summaries/highlights/Q&A.
Heavy IO lives in the CLI; summarization is **skills-primary** (Claude Code skills,
not an API) to keep it free and high-quality.

## Architecture (module map)

- `config.py` — `.env` loading (`Config`). Secrets only from `.env` (gitignored).
  `use_webshare` (`YT_USE_WEBSHARE`, default **off**) gates the Webshare proxy;
  `discover_feed_limit`/`discover_overlap_s` tune incremental discovery.
  `load_config` precedence is **global config file < project `.env` < process
  env**: the global file (`$YT_MEM_AI_HOME/config.env`, default
  `~/.yt-mem-ai/config.env`) lets settings applied from chat persist for the MCP
  server no matter its cwd.
- `settings.py` — runtime get/set of the `.env` variables, powering `yt-ai
  config {list,get,set,unset,path}` and the MCP `config_*` tools (so an agent/user
  can set Webshare creds, swap the embedding model, etc. from chat). `KNOWN`
  registry covers the `.env.example` variables plus a couple of desktop-backend
  knobs (validates keys + choices, masks secrets);
  `set_setting` writes the global config file by default (`scope="project"` →
  `./.env`) and flags when a process env var would override the write.
- `obs.py` — unified logging. `log_event(source, event, level="info", msg="", *,
  log_file=None, **ctx)` never raises (append fails silently); `blog(...)` is the
  `source="backend"` shorthand used across `cli.py`. Writes one JSON line
  (`{ts, source, level, event, msg, ...ctx}`) to `Config.log_file`
  (`YT_LOG_FILE` env, default `logs/common.jsonl`; gitignored).
- `proxy.py` / `cookies.py` — Webshare rotating proxy + Chrome cookies for yt-dlp.
  Both `ytdlp_proxy_url` and `webshare_config` return `None` unless
  `cfg.use_webshare` **and** creds are set — so a system-level VLESS/VPN carries
  traffic by default (stacking Webshare on the authed subscription feed 405s).
- `download.py` — yt-dlp download + metadata; `build_opts(cfg, download_audio)`.
  `download_metadata(url, cfg)` fetches metadata only (no audio) for the
  captions-only path; uses `process=False` so meta survives the missing JS
  challenge solver (which otherwise fails format selection). Both extract calls
  go through `_extract`, which maps YouTube's bot check ("Sign in to confirm
  you're not a bot") to `SignInRequired` so `cli.fetch` can print the
  `config set YT_COOKIES_BROWSER <browser>` fix (exit 4) instead of a traceback.
- `transcript/` — `captions.py` (youtube-transcript-api) → `whisper.py` (faster-whisper)
  fallback, orchestrated by `get_transcript`. `fetch_captions` tries `cfg.caption_langs`
  (`YT_CAPTION_LANGS`, default `en`) then falls back to ANY available track (manual
  over auto-generated), so non-English videos ingest via the fast captions path; the
  source language is stored in `transcripts.lang` (exposed as `transcript_lang` in
  `show --json`). Skills produce artifacts in the video's original language by
  default (user preference); translate only when a target language is requested.
- `discovery.py` — subscription feed extraction (`discover`), injectable `extract_fn` seam.
  Flat feed pull is capped (`playlistend=discover_feed_limit`) and stamped with
  approximate per-entry `timestamp` via `youtubetab:approximate_date` — dates in
  one call, no per-video N+1. Cutoff is epoch-based: `after_ts` (incremental
  high-water) beats `after` (YYYY-MM-DD), minus `overlap_s`; newest-first with an
  early break. `Video.published_ts` (epoch, **not** persisted — absent from
  `VideoSchema`) carries the high-water back to `run_discover`. Per-video date
  fallback (`_published_ts`, `process=False`) only fires for entries lacking an
  inline timestamp (e.g. live premieres).
- `channel-list` (CLI) — `channel_videos` enumerates a channel's recent uploads
  (reuses discovery's flat-extract), date-filtered then capped to `--limit`; the
  `yt` skill's "group" scenario uses it to ingest + review an arbitrary set →
  `groups/<label>.md`. The underlying fetch is bounded by `YT_DISCOVER_FEED_LIMIT`
  (default 60), so `--limit`/date windows beyond the newest ~60 uploads need it raised.
- `store/` — `models.py` (dataclasses + LanceModel schemas + `chunk_schema`),
  `embeddings.py` (`build_embedder`, `chunk_segments`), `db.py` (LanceDB CRUD + search).
- `reembed` (CLI) — `run_reembed` rebuilds the `chunks` table with the current
  `build_embedder(cfg)` (via `store.rebuild_chunks`), migrating the library to a
  new embedding model without re-fetching.
- `memory.py` — status-based `is_seen` / `mark_status`.
- `recommend.py` — taste-centroid ranking over chunk embeddings (like − dislike).
- `compile.py` — `compile_highlights` builds a deep-linked highlights doc from
  summarized videos' `summaries.highlights` + `chunks` spans (`chunk_span`
  snaps each highlight to its containing/nearest chunk, falling back to a
  fixed window), newest-video-first and budget-bounded by `--max-minutes`
  (`accumulate`). `render_markdown` emits `watch?v=ID&t=<start>s` links per
  clip; no media rendering here.
- `supercut.py` — renders `compile_highlights`' clip selection as an actual
  video reel instead of a doc: pure command-builders (`download_section_opts`
  — 720p `download_range_func` section + `build_opts` proxy/cookies;
  `normalize_label_cmd` — scale/pad/fps + `drawtext=textfile=<label_file>`,
  which sidesteps drawtext text-escaping entirely; `concat_cmd` — concat
  demuxer; `label_text`/`refs_markdown` — clip label/sidecar refs text) plus
  the orchestrator `build_supercut(db, since, max_minutes, out_path, cfg=,
  workdir=, download_fn=, ffmpeg_fn=)`, which takes injectable
  `download_fn`/`ffmpeg_fn` so the whole flow is unit-tested offline, and
  continues past a clip whose download/render fails (recorded in the
  `.refs.md` sidecar's skipped list) rather than aborting the run. Real
  rendering (actual yt-dlp downloads + ffmpeg) is manual smoke only, not in
  the test suite.
- `frame.py` — single still-frame grab: `grab_frame(db, video_id, at_s, out_path,
  cfg=, workdir=, download_fn=, ffmpeg_fn=)` downloads a 1s 720p section at the
  timestamp (reusing `supercut`'s `_FORMAT` + `download_range_func`) and extracts
  the first frame via ffmpeg. `parse_timestamp` accepts seconds or `H:M:S`.
  Injectable seams keep it offline-testable; real yt-dlp/ffmpeg is manual smoke.
- `cli.py` — Typer app; thin `run_*` cores are the testable seam.
  `fetch --captions-only` runs the metadata+captions path
  (no audio/whisper). `run_discover` is incremental: cutoff precedence is
  explicit `--after` > stored epoch `last_discover_ts` (−`overlap_s`) > legacy
  `last_discover_at` date > 7-day default; it drops `is_seen` videos and advances
  `last_discover_ts` (never regressing) from the discovered `published_ts`.
- `mcp_server.py` — `FastMCP` server (`yt-ai-mcp` console entry, optional `[mcp]`
  extra) exposing the engine to any MCP host. Thin protocol adapter: each
  `@mcp.tool()` loads config, opens the store, and calls the matching `run_*`
  core, returning JSON-safe dicts (no business logic here). The `yt`/`yt-agent`
  scenarios ship as `@mcp.prompt()`s whose bodies are loaded from the checked-in
  SKILL.md files (`_load_skill`: source `skills/<name>/SKILL.md`, or the
  `force-include`d `yt_mem_ai/_skills/*.md` in a built wheel) — single source of
  truth, no drift. Host packaging lives under `integrations/` (see below).
- `integrations/` — host packaging. **Native skills** (symlinked, never copied,
  from the canonical `skills/`) drive the `yt-ai` CLI via `uvx yt-mem-ai <cmd>`:
  `claude-code/` (`.claude-plugin/{plugin,marketplace}.json` + `commands/` +
  `skills/`), `codex/` (`.codex-plugin/plugin.json` + `skills/` + `prompts/` +
  `AGENTS.md`; → `~/.codex/skills/`), `cursor/` (`skills/` → `~/.cursor/skills/`
  + MCP `~/.cursor/mcp.json`), `antigravity/` (`skills/` → `~/.gemini/skills/` +
  MCP `~/.gemini/config/mcp_config.json`). **Claude Desktop plugins are
  account-side, not on disk** — `~/.claude/plugins` is Claude Code's store and
  Desktop chat does not read it, so no script can install/uninstall a Desktop
  plugin; the installer prints the in-app steps (Customize → Plugins → add the
  repo-root marketplace) and `claude-desktop/` covers the scriptable path, a
  `claude_desktop_config.json` MCP entry (the `.mcpb` bundle was dropped as
  fussy). MCP (`yt-ai-mcp`) is an optional typed-tool surface on any host; `mcp/`
  documents it, and the server ships an `instructions` string so MCP-only hosts
  still know the workflow. Any MCP install uses a persistent, absolute-path
  `yt-ai-mcp` binary (`uv tool install 'yt-mem-ai[mcp]'`) so GUI hosts start it
  instantly. **One installer at the repo root** — `install.sh` (+ `install.ps1`),
  self-contained, no helper files, so `curl … | sh` works: a **two-step wizard**
  (step 1 = single choice plugin|mcp, step 2 = host checkboxes; menu rows are
  ASCII and truncated to `tput cols` with a per-line `\033[2K`, since a wrapped
  row desynced the cursor-up redraw) over the
  five hosts, keyed by `method:host` pairs. Install detection is exact — an
  `mcpServers` key lookup (`json_has_server`, recursing into Claude Code's
  project-scoped maps) and `"yt-mem-ai@yt-mem-ai"` in `settings.json`, because a
  loose name grep matched `githubRepoPaths` and made MCP look installed after a
  plugin install; `claude mcp add/remove` use `-s user` so the server is global,
  not bound to the cwd the installer ran in. `plugin` also runs `uv tool install yt-mem-ai` (the CLI
  the skills shell out to); `mcp` runs `uv tool install 'yt-mem-ai[mcp]'`.
  Installed pairs come pre-ticked and unticking removes (diff-based, extra
  confirm); **a method not ticked in step 1 is never touched**, and flag runs
  are additive-only. Anything unautomatable (Desktop plugins, a missing host
  CLI, a skill fetch that failed) prints a bright `warnbox` with manual steps.
  Flags: `--plugin --mcp | --claude-code --claude-desktop --codex --cursor
  --antigravity --openclaw --hermes | --all --all-hosts --all-methods -y
  --bootstrap`. **OpenClaw** (skills `~/.agents/skills`, MCP via `openclaw mcp
  add` or `openclaw.json`'s `mcp.servers` — note the non-standard shape) and
  **Hermes** (skills `~/.hermes/skills`, MCP in `~/.hermes/config.yaml`'s
  `mcp_servers:`) are hosts 6-7; the Hermes writer splices a fixed YAML block by
  hand because neither sh nor python3's stdlib can emit YAML. `curl … | sh`
  with no flags **re-execs itself**: stdin is the script text, so it re-downloads
  a copy to a temp file and runs it with `< /dev/tty` (guarded by
  `YT_INSTALL_REEXEC`; `YT_INSTALL_RAW_ROOT` overrides the source for tests) —
  that's what makes the one-line install interactive. No TTY at all (CI, or the
  refetch failed) falls back to bootstrapping the CLI only. `PROMPT.md` is the paste-into-any-agent
  installer; `skills/README.md` documents installing/pasting the skills by hand.
- REST API — **moved out** to the [`yt-mem-ai-desktop`](https://github.com/dasein108/yt-mem-ai-desktop)
  repo (FastAPI backend that imports this package and reuses `cli.py`'s `run_*`/
  `open_store` cores). This repo is the engine: library + data/pipeline CLI only.
- `frontend/` — **moved out** to the standalone repo
  [`yt-mem-ai-desktop`](https://github.com/dasein108/yt-mem-ai-desktop) (React+TS
  desktop UI + Electron wrapper). It consumes this engine as a Python package
  (its FastAPI backend imports `yt_mem_ai`'s CLI cores directly) and the
  packaged app bundles the engine. This repo is the engine: library + CLI +
  skills, published to PyPI as `yt-mem-ai`.

## Store (LanceDB)

Tables: `videos`, `channels`, `transcripts`, `chunks` (embedded + FTS), `summaries`,
`feedback`, `app_state`. Video lifecycle `status`: `discovered → downloaded →
transcribed → summarized`. Live streams get a terminal `status=stream`: batch
ingestion (`fetch-pending`) detects them via yt-dlp `live_status` (`is_live`/
`is_upcoming`/`post_live`/`was_live`, see `models.is_stream`), marks them, and
**skips transcription** (they're long + usually caption-less). A direct
`yt-ai fetch <url>` transcribes a stream on demand (`run_fetch(include_streams=True)`).

## Conventions (follow these)

- **skills-primary summarization** — the CLI stores data; skills read it via
  `yt-ai show --json` / `search` / `save-summary` and never touch the store engine.
- **`_safe(...)`** guards every LanceDB `where/delete/update` clause that interpolates
  an id/key/status. Always use it for new filters.
- **`is_seen` is status-based** (`transcribed`/`summarized`) → ingest is retry-safe.
- **insert-only discovery** (`insert_discovered_video`) never downgrades a fetched video.
- **Injectable seams for offline tests**: `ydl_factory`, `extract_fn`, `model_factory`,
  and monkeypatched `cli.run_fetch`/`cli.discover_videos`. Unit tests must not hit the
  network or download models — the registered `FakeEmbedder` (tests/support.py) covers
  embeddings.
- Dates are `YYYY-MM-DD` strings; string comparison is date comparison.
- **Logging convention** — every runtime writes to the same file,
  `logs/common.jsonl` (one JSON object per line, gitignored, never edit by
  hand): backend via `obs.log_event`/`blog`, the frontend via
  yt-mem-ai-desktop's `src/lib/log.ts`'s `log()` (fire-and-forget `POST /log`, plus
  `installLogBridge()` auto-forwarding `console.error`/`warn` and uncaught
  errors/rejections), and Electron's main process via
  yt-mem-ai-desktop's `electron/lib.ts`'s `logLine()`/`logsPath()`. Every line has
  `{ts, source, level, event, msg, ...ctx}` with `source ∈
  backend|electron|frontend`; logging never raises. See the `yt-mem-ai-desktop`
  repo for the `yt-debugger`-style tooling to trace an issue across all three.

## Recommendations

`like`/`dislike` write the `feedback` table (latest signal per video wins); `recommend`
builds like/dislike centroids from liked/disliked videos' chunk vectors and ranks unrated
transcribed/summarized videos.

## Skills

Canonical skills live in `skills/<name>/SKILL.md` (checked in, any-LLM usable).
Claude Code only discovers skills under `.claude/skills/`, so each is surfaced
via a symlink `.claude/skills/<name> -> ../../skills/<name>` (thin ref, no drift).

- `yt` — umbrella entry point for any `yt-ai` CLI op + both pipelines;
  delegates per-video analysis, digests, and reviews to `yt-agent`.
- `yt-agent` — scenario skill: one video → summary/highlights/Q&A/presentation
  (`slides/<id>.md`); process subscriptions → `digests/<DATE>.md`; cross-video
  subscriptions review → `reviews/<DATE>.md`. Persists via `save-summary`.

The `yt-debugger` skill (backend/electron/frontend log correlation) **moved
out** with the REST API to the `yt-mem-ai-desktop` repo.

There are two independent summarization paths, both writing the same `summaries`
table via `store.upsert_summary`: the skills-primary path above (free, via Claude
Code) and the `yt-mem-ai-desktop` backend's summarize job (OpenRouter, for the
desktop UI). Neither is authoritative over the other — last write wins.

## Commands & daily routine

See README.md. Pipeline: `discover → fetch-pending → /yt (process subscriptions) → compile`;
single video: `fetch → /yt (summarize/highlights/qa/presentation)`.

## Dev

```bash
uv sync --extra dev
uv run pytest -q                        # offline unit suite (fake embedder)
YT_RUN_INTEGRATION=1 uv run pytest -q   # + real sentence-transformers integration
uv run --with ruff ruff check .         # lint
```

TDD: tests live in `tests/`, one per module; keep them offline via the injectable seams.
Design docs in `docs/superpowers/specs/`, plans in `docs/superpowers/plans/`.

**Releasing** (maintainers): version comes from the git tag (hatch-vcs). Tag →
`uv build` → `sh scripts/publish.sh dist/yt_mem_ai-X.Y.Z*`. The script loads
`UV_PUBLISH_TOKEN` (PyPI token) from `.env` (gitignored) on demand — never commit
it; rotate on PyPI if exposed. `tests/conftest.py` isolates `YT_MEM_AI_HOME` so
the global config file can't perturb tests.
