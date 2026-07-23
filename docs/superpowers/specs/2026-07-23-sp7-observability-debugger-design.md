# SP7 — Unified Observability + yt-debugger Design

**Date:** 2026-07-23
**Status:** Approved (brainstorming complete)
**Motivation:** the Electron UI showed empty and a `discover` run hung silently for 2 minutes — we had zero visibility into where. This adds a unified, jq-queryable log across all three runtimes and a debugger skill.

## Vision

One structured log (`logs/common.jsonl`) that the **backend** (Python), the
**Electron main** process (Node), and the **frontend** (React, via the backend)
all append to — each line tagged with its `source` — plus workflow-level events
that reflect what the pipeline is actually doing, and a `yt-debugger` skill that
runs the server, introspects the API schema, and filters the log with `jq`.

## Locked Decisions

| Concern | Choice |
|---|---|
| Format | JSON Lines — one `{ts, source, level, event, msg, ...ctx}` object per line |
| Location | `logs/common.jsonl` (gitignored); `YT_LOG_FILE` env override; `Config.log_file` (defaulted field) |
| Multi-writer | per-line open-append-close (O_APPEND → atomic single-line writes across processes) |
| Frontend → log | a `POST /log` backend endpoint; backend appends with `source="frontend"` |
| Electron → log | writes JSONL directly (owns lifecycle events before the API is up) |
| Debugger | full skill: run server + `/openapi.json` schema + example calls + `jq` log recipes |
| Workflow logging | targeted at the high-signal steps (not every function) |

## Log line schema

```json
{"ts":"2026-07-23T12:00:00.123+00:00","source":"backend","level":"info",
 "event":"fetch.transcribe","msg":"whisper fallback","video_id":"abc","source_kind":"whisper"}
```
- `source`: `backend` | `electron` | `frontend`.
- `level`: `debug` | `info` | `warn` | `error`.
- `event`: dotted namespace (`api.start`, `store.connect`, `discover.feed`, `fetch.download`, `job.running`, `job.error`, `ui.api_error`, `electron.sidecar.spawn`, `electron.api.wait`).
- `msg`: short human string. Everything else is free-form context.

## Architecture

```
yt_summary/
  obs.py         NEW: log_event(source, event, level, msg, **ctx) → appends a JSONL line
  config.py      + log_file: Path = Path("logs/common.jsonl")  (defaulted, from YT_LOG_FILE)
  api/app.py     + POST /log (schema LogIn) + lifespan start events
  api/jobs.py    + job.queued/running/done/error events (id, kind, duration_ms)
  cli.py / discovery.py / download.py / transcript / store  + targeted workflow events
frontend/
  src/lib/log.ts        NEW: log(event, level, msg, ctx) → POST /log (fire-and-forget)
  src/api/client.ts     + log ApiError on non-2xx
  electron/lib.ts       + log_line(file, obj) (pure JSONL writer) + repo-root log path resolver
  electron/main.ts      + sidecar.spawn / api.wait / window / tray / quit events
skills/
  yt-debugger/SKILL.md  NEW
```

### obs.py (backend)

- `log_event(source: str, event: str, level: str = "info", msg: str = "", *, log_file=None, **ctx) -> None`
  — build `{ts: now(UTC).isoformat(), source, level, event, msg, **ctx}`, `json.dumps` one line,
  append to `log_file` (default from `load_config().log_file`, or `YT_LOG_FILE`), create parent dir.
  Never raises (logging must not break the app — wrap in try/except, swallow).
- `blog(event, level="info", msg="", **ctx)` — convenience with `source="backend"`.

### Backend workflow events (targeted)

- `api.start` (lifespan), `store.connect` (store_path), `embedder.build` (backend, model).
- `discover.start` (after, deep), `discover.feed` (entry count), `discover.done` (new/known).
- `fetch.start` (url/video_id), `fetch.download` (audio_path), `fetch.transcribe` (source_kind),
  `fetch.chunk` (n_chunks), `fetch.done` (status) — and `fetch.skip` (already seen).
- `job.queued` / `job.running` / `job.done` (duration_ms) / `job.error` (error) in `jobs.Worker.run_one`.
- Errors log at `level="error"` with the exception string.

### POST /log

- `LogIn` schema: `{level?: str, event: str, msg?: str, ctx?: dict}`.
- Handler: `log_event("frontend", body.event, body.level or "info", body.msg or "", **(body.ctx or {}))`; returns 204.

### frontend/src/lib/log.ts

- `log(event, level = "info", msg = "", ctx = {})` → `fetch(<API_BASE>/log, {method:"POST", body:...})`,
  `.catch(() => {})` (never throw; don't await in hot paths).
- Wire: `App` mount (`ui.start`), `client.ts` `req()` on `ApiError` (`ui.api_error` with status/path),
  job-start mutations (`ui.job_start` with kind). Keep it a handful of high-signal calls.

### electron/lib.ts + main.ts

- `log_line(file, obj) -> void` (pure: JSON.stringify + append, mkdir parent) — Vitest-tested.
- `logs_path(repoRoot) -> string` — `<repoRoot>/logs/common.jsonl`.
- main.ts calls: `electron.start`, `electron.sidecar.spawn` (command+args), `electron.api.wait`
  (ok/attempts), `electron.window`, `electron.tray.hide`, `electron.quit` (+ sidecar kill).

### yt-debugger skill

Documented workflow (SKILL.md):
1. **Run backend:** `uv run yt-ai serve &` (background); note Electron is GUI — launch `npm run electron:dev` manually if needed.
2. **Schema:** `curl -s 127.0.0.1:8000/openapi.json | jq '.paths | keys'`; drill into an endpoint's params/schema.
3. **Probe:** `curl -s 127.0.0.1:8000/status | jq`, `/videos`, `/jobs`.
4. **Logs (jq recipes over `logs/common.jsonl`):**
   - errors: `jq -c 'select(.level=="error")' logs/common.jsonl`
   - one source: `jq -c 'select(.source=="electron")' …`
   - a job's full trace: `jq -c 'select(.id=="<jobid>")' …`
   - an event prefix: `jq -c 'select(.event|startswith("fetch"))' …`
   - tail live: `tail -f logs/common.jsonl | jq -c '{ts,source,event,msg}'`
   - last N of a run: `jq -c 'select(.source=="backend")' … | tail -20`
5. Correlate a failing UI action → its `ui.*` line → the backend `job.*`/`fetch.*` trail.

## Testing (offline)

- `obs.log_event`: writes a line to a temp file that `json.loads` round-trips with `ts/source/event`; appends (2 calls → 2 lines); a bad `log_file` dir is created; never raises on error.
- `POST /log`: TestClient with `cfg.log_file`→tmp; posting `{event,level,msg,ctx}` appends a `source="frontend"` line.
- A workflow event fires: point `log_file` at tmp, run `run_fetch` (fakes) → assert a `fetch.done` line exists; `jobs.Worker.run_one` on a raising job → a `job.error` line.
- frontend `log()`: MSW mock `POST /log`, assert it's called with the event (fire-and-forget, no throw on failure).
- electron `log_line`: Vitest writes an object → file has the JSON line; `logs_path` builds the repo-root path.
- No network; all file writes to temp/`tmp_path`.

## Documentation Updates

- README: a "Debugging" section — the unified `logs/common.jsonl`, `YT_LOG_FILE`, and the `yt-debugger` skill + a couple jq one-liners.
- `CLAUDE.md`: add `obs.py` + the logging convention (every runtime → `logs/common.jsonl`, `source`-tagged) + the `yt-debugger` skill.
- `.gitignore`: `logs/`.
- Roadmap memory: record SP7 (observability) done.

## Out of Scope

- Log rotation/retention, log levels config beyond per-line `level`, remote/aggregated logging.
- OpenTelemetry/spans, metrics, a live log-viewer UI.
- Auto-diagnosis (the skill guides a human/agent; it doesn't auto-fix).
- Changing the cookie-hang behavior itself (SP7 makes it *visible*; the fix — e.g. a cookie-extract timeout or a clearer prompt — is a separate follow-up informed by the logs).
