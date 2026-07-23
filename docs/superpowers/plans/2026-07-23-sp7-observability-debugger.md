# SP7 Observability + yt-debugger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A unified `logs/common.jsonl` written by backend + Electron + frontend (each `source`-tagged), targeted workflow events, and a `yt-debugger` skill that runs the server, reads the schema, and filters logs with `jq`.

**Architecture:** `obs.log_event` (backend, JSONL append, never-raises) is the core. The frontend routes logs through a `POST /log` endpoint; Electron main writes JSONL directly via a tested `logLine` helper. Workflow events are added at the high-signal points (discover/fetch steps, job lifecycle, sidecar/waitForApi). The skill documents `/openapi.json` introspection + `jq` recipes.

**Tech Stack:** Python 3.11+ (stdlib json/logging), FastAPI (POST /log), React/TS + Vitest/MSW (frontend), Electron/Vitest (main), uv/npm.

## Global Constraints

- **Mixed toolchain.** Tasks 1–2 Python (`uv run pytest -q` + `uv run --with ruff ruff check .`). Tasks 3–4 Node (`npm --prefix frontend run typecheck|test|build|lint`). Task 5 both. State which per task.
- **Logging never raises:** `obs.log_event` and electron `logLine` wrap their body in try/except and swallow — observability must not break the app.
- **Log path resolution:** `obs.log_event` writes to `YT_LOG_FILE` env → else `logs/common.jsonl`; `Config.log_file` mirrors this (a defaulted field). Tests point the log at a temp path via the `YT_LOG_FILE` env (Python) or an explicit path arg (electron).
- **Line schema:** `{ts (ISO8601 UTC), source, level, event, msg, ...ctx}`; `source ∈ {backend, electron, frontend}`; `json.dumps(..., default=str)` so odd ctx never breaks it.
- Frontend logging is **fire-and-forget** (`.catch(()=>{})`, never awaited in hot paths). No import cycle: `apiBase()` lives in its own module imported by both `client.ts` and `log.ts`.
- `logs/` gitignored; `node_modules` excluded from commits. Config gets a **defaulted** `log_file` field (no test-helper churn — mirrors the SP-HF_TOKEN pattern).
- Every task ends with its gates green and is committed.

---

## File Structure

```
yt_summary/
  obs.py         NEW
  config.py      + log_file (defaulted)
  api/app.py     + POST /log + api.start event
  api/schemas.py + LogIn
  api/jobs.py    + job.* events (duration_ms)
  cli.py         + fetch.*/discover.* events (targeted)
frontend/
  src/lib/apiBase.ts   NEW (extracted from client.ts)
  src/lib/log.ts       NEW
  src/api/client.ts    use apiBase.ts + log ApiError
  electron/lib.ts      + logLine + logsPath
  electron/main.ts     + electron.* events
skills/yt-debugger/SKILL.md   NEW
tests/                 (python) test_obs.py, test_api_reads.py(+/log), test_cli.py(+event)
frontend/src/**        (node) log.test.ts, lib.test.ts(+logLine)
```

---

## Task 1: obs.py + config.log_file (Python)

**Files:** `yt_summary/obs.py`, `yt_summary/config.py`. Test: `tests/test_obs.py`. Gates: pytest + ruff.

**Interfaces:** `log_event(source, event, level="info", msg="", *, log_file=None, **ctx)`; `blog(event, level="info", msg="", *, log_file=None, **ctx)`; `Config.log_file: Path`.

- [ ] **Step 1: Write the failing test — `tests/test_obs.py`**

```python
import json
from yt_summary import obs


def test_log_event_writes_jsonl(tmp_path):
    f = tmp_path / "common.jsonl"
    obs.log_event("backend", "fetch.done", "info", "ok", log_file=str(f), video_id="v1")
    obs.log_event("frontend", "ui.api_error", "error", "boom", log_file=str(f), status=500)
    lines = [json.loads(x) for x in f.read_text().splitlines()]
    assert len(lines) == 2
    assert lines[0]["source"] == "backend" and lines[0]["event"] == "fetch.done"
    assert lines[0]["video_id"] == "v1" and "ts" in lines[0]
    assert lines[1]["level"] == "error" and lines[1]["status"] == 500


def test_log_event_creates_parent_dir(tmp_path):
    f = tmp_path / "nested" / "d" / "common.jsonl"
    obs.log_event("backend", "e", log_file=str(f))
    assert f.exists()


def test_log_event_never_raises():
    # a directory path as the log file → open() would fail; must be swallowed
    obs.log_event("backend", "e", log_file="/")  # no exception


def test_blog_is_backend_source(tmp_path):
    f = tmp_path / "c.jsonl"
    obs.blog("api.start", log_file=str(f), port=8000)
    assert json.loads(f.read_text().splitlines()[0])["source"] == "backend"


def test_config_log_file_default_and_env(tmp_path):
    from yt_summary.config import load_config
    assert load_config(tmp_path / "none.env").log_file.name == "common.jsonl"
    env = tmp_path / ".env"
    env.write_text("YT_LOG_FILE=/x/y.jsonl\n")
    from pathlib import Path
    assert load_config(env).log_file == Path("/x/y.jsonl")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_obs.py -q` → FAIL (`ModuleNotFoundError: yt_summary.obs`)

- [ ] **Step 3: Implement `yt_summary/obs.py`**

```python
# yt_summary/obs.py
from __future__ import annotations
import json
import os
from datetime import datetime, UTC
from pathlib import Path


def _log_path(log_file: str | None) -> Path:
    if log_file is not None:
        return Path(log_file)
    return Path(os.environ.get("YT_LOG_FILE") or "logs/common.jsonl")


def log_event(source: str, event: str, level: str = "info", msg: str = "",
              *, log_file: str | None = None, **ctx) -> None:
    try:
        path = _log_path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = {"ts": datetime.now(UTC).isoformat(), "source": source,
                "level": level, "event": event, "msg": msg, **ctx}
        with open(path, "a") as f:
            f.write(json.dumps(line, default=str) + "\n")
    except Exception:
        pass  # logging must never break the app


def blog(event: str, level: str = "info", msg: str = "", *,
         log_file: str | None = None, **ctx) -> None:
    log_event("backend", event, level, msg, log_file=log_file, **ctx)
```

- [ ] **Step 4: Add `log_file` to `yt_summary/config.py`**

Add as the LAST `Config` field (after `hf_token`, both defaulted):
```python
    log_file: Path = Path("logs/common.jsonl")
```
Add `"YT_LOG_FILE"` to the env override tuple, and the constructor line:
```python
        log_file=Path(_clean(data.get("YT_LOG_FILE")) or "logs/common.jsonl"),
```

- [ ] **Step 5: Run tests** → `uv run pytest -q` PASS; `-W error::DeprecationWarning` clean; `uv run --with ruff ruff check .` clean.

- [ ] **Step 6: Commit**

```bash
git add yt_summary/obs.py yt_summary/config.py tests/test_obs.py
git commit -m "feat: obs.log_event unified jsonl logger + config.log_file"
```

---

## Task 2: Backend workflow events + POST /log (Python)

**Files:** `yt_summary/api/schemas.py`, `yt_summary/api/app.py`, `yt_summary/api/jobs.py`, `yt_summary/cli.py`. Test: `tests/test_api_reads.py` (append `/log`), `tests/test_cli.py` (append event). Gates: pytest + ruff.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_api_reads.py`:
```python
def test_post_log_appends_frontend_line(tmp_path, monkeypatch):
    monkeypatch.setenv("YT_LOG_FILE", str(tmp_path / "c.jsonl"))
    client, _ = _client(tmp_path)
    with client:
        r = client.post("/log", json={"event": "ui.start", "level": "info", "msg": "hi", "ctx": {"a": 1}})
        assert r.status_code == 204
    import json
    lines = [json.loads(x) for x in (tmp_path / "c.jsonl").read_text().splitlines()]
    assert any(l["source"] == "frontend" and l["event"] == "ui.start" and l["a"] == 1 for l in lines)
```
Append to `tests/test_cli.py`:
```python
def test_run_fetch_emits_workflow_events(tmp_path, monkeypatch):
    import json
    monkeypatch.setenv("YT_LOG_FILE", str(tmp_path / "c.jsonl"))
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)
    monkeypatch.setattr(cli, "download",
        lambda url, c: (Video(video_id="abc", url=url, status="downloaded"), "/a.mp3"))
    monkeypatch.setattr(cli, "get_transcript",
        lambda v, audio, c: T.TranscriptResult("captions", "en", "hello", [Segment("abc", 0.0, 1.0, "hello")]))
    cli.run_fetch("https://y/abc", cfg, db=conn)
    events = {json.loads(x)["event"] for x in (tmp_path / "c.jsonl").read_text().splitlines()}
    assert "fetch.done" in events
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_api_reads.py::test_post_log_appends_frontend_line tests/test_cli.py::test_run_fetch_emits_workflow_events -q`
Expected: FAIL (no `/log` route; no `fetch.done` event)

- [ ] **Step 3: Add `LogIn` to `yt_summary/api/schemas.py`**

```python
class LogIn(BaseModel):
    event: str
    level: str | None = None
    msg: str | None = None
    ctx: dict | None = None
```

- [ ] **Step 4: Add `POST /log` + `api.start` to `yt_summary/api/app.py`**

In the lifespan (after the store opens), add:
```python
        from ..obs import blog
        blog("api.start", msg="server ready")
```
Add the route inside `create_app` (near the other routes):
```python
    @app.post("/log", status_code=204)
    def post_log(body: schemas.LogIn):
        from ..obs import log_event
        log_event("frontend", body.event, body.level or "info", body.msg or "", **(body.ctx or {}))
        return Response(status_code=204)
```

- [ ] **Step 5: Add `job.*` events to `yt_summary/api/jobs.py`**

In `Worker.run_one`, wrap the job execution with timing + events:
```python
import time
from ..obs import blog
# inside run_one, after popping (job, fn):
        job.status = "running"
        blog("job.running", job_id=job.id, kind=job.kind)
        start = time.monotonic()
        try:
            job.result = fn(job)
            job.status = "done"
            blog("job.done", job_id=job.id, kind=job.kind,
                 duration_ms=round((time.monotonic() - start) * 1000))
        except Exception as exc:  # noqa: BLE001
            job.error = str(exc)
            job.status = "error"
            blog("job.error", level="error", msg=str(exc), job_id=job.id, kind=job.kind)
        finally:
            self._q.task_done()
        return True
```

- [ ] **Step 6: Add targeted `fetch.*`/`discover.*` events to `yt_summary/cli.py`**

In `run_fetch`, emit (from `..obs import blog`): `blog("fetch.skip", ...)` on the seen short-circuit; `blog("fetch.download", video_id=..., audio_path=...)`, `blog("fetch.transcribe", video_id=..., source_kind=result.source)`, `blog("fetch.done", video_id=..., status="transcribed")`. In `run_discover`: `blog("discover.start", after=cutoff, deep=deep)` and `blog("discover.done", new=new_count, found=len(discovered))`. Keep them minimal at the step boundaries.

- [ ] **Step 7: Run gates** → `uv run pytest -q` PASS; `-W error::DeprecationWarning` clean; ruff clean.

- [ ] **Step 8: Commit**

```bash
git add yt_summary/api/schemas.py yt_summary/api/app.py yt_summary/api/jobs.py yt_summary/cli.py tests/
git commit -m "feat: POST /log + backend workflow events (fetch/discover/job lifecycle)"
```

---

## Task 3: Frontend logging (Node)

**Files:** `frontend/src/lib/apiBase.ts` (extract), `frontend/src/lib/log.ts`, `frontend/src/api/client.ts` (use apiBase + log ApiError). Test: `frontend/src/lib/log.test.ts`. Gates: frontend typecheck/test/lint/build.

- [ ] **Step 1: Extract `apiBase()` → `frontend/src/lib/apiBase.ts`**

```ts
export function apiBase(): string {
  return (
    (typeof window !== 'undefined' && window.electron?.apiBase) ||
    (import.meta.env.VITE_API_BASE as string | undefined) ||
    '/api'
  )
}
```
In `client.ts`, delete its local `apiBase()` and `import { apiBase } from '@/lib/apiBase'`.

- [ ] **Step 2: Write the failing test — `frontend/src/lib/log.test.ts`**

```ts
import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../mocks/node'
import { log } from './log'

describe('log', () => {
  it('POSTs the event to /log', async () => {
    let got: any = null
    server.use(http.post('/api/log', async ({ request }) => {
      got = await request.json()
      return new HttpResponse(null, { status: 204 })
    }))
    log('ui.start', 'info', 'hello', { a: 1 })
    await new Promise((r) => setTimeout(r, 20))
    expect(got).toMatchObject({ event: 'ui.start', level: 'info', ctx: { a: 1 } })
  })
  it('never throws when the endpoint fails', async () => {
    server.use(http.post('/api/log', () => new HttpResponse(null, { status: 500 })))
    expect(() => log('x')).not.toThrow()
    await new Promise((r) => setTimeout(r, 20))
  })
})
```

- [ ] **Step 3: Run to verify it fails**

Run: `npm --prefix frontend run test -- log.test`
Expected: FAIL (`Cannot find module './log'`)

- [ ] **Step 4: Implement `frontend/src/lib/log.ts`**

```ts
import { apiBase } from './apiBase'

export function log(event: string, level = 'info', msg = '',
                    ctx: Record<string, unknown> = {}): void {
  try {
    void fetch(`${apiBase()}/log`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ event, level, msg, ctx }),
    }).catch(() => {})
  } catch {
    /* never throw */
  }
}
```

- [ ] **Step 5: Log `ApiError` in `client.ts`**

In `req()`'s non-2xx branch, before throwing `ApiError`, emit a log (import `log` from `@/lib/log`):
```ts
    log('ui.api_error', 'error', detail, { status: res.status, path })
```
(where `path` is the request path arg). Ensure no import cycle: `client.ts → log.ts → apiBase.ts`, and `log.ts` does NOT import `client.ts`.

- [ ] **Step 6: Run gates** → `npm --prefix frontend run test typecheck lint build` all PASS. Report count.

- [ ] **Step 7: Commit**

```bash
git add frontend/src ':!frontend/node_modules'
git commit -m "feat(ui): frontend log() → POST /log + apiBase extraction"
```

---

## Task 4: Electron main logging (Node)

**Files:** `frontend/electron/lib.ts` (+ `logLine`, `logsPath`), `frontend/electron/main.ts` (+ events). Test: `frontend/electron/lib.test.ts` (append). Gates: frontend typecheck/test/lint/build.

- [ ] **Step 1: Write the failing test (append to `frontend/electron/lib.test.ts`)**

```ts
import { logLine, logsPath } from './lib'
import { readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

describe('logLine / logsPath', () => {
  it('logsPath builds the repo-root path', () => {
    expect(logsPath('/repo')).toBe(path.join('/repo', 'logs', 'common.jsonl'))
  })
  it('logLine appends a json line with ts', () => {
    const f = path.join(tmpdir(), `sp7-${process.pid}.jsonl`)
    rmSync(f, { force: true })
    logLine(f, { source: 'electron', event: 'electron.start' })
    logLine(f, { source: 'electron', event: 'electron.quit' })
    const lines = readFileSync(f, 'utf8').trim().split('\n').map((l) => JSON.parse(l))
    expect(lines.length).toBe(2)
    expect(lines[0]).toMatchObject({ source: 'electron', event: 'electron.start' })
    expect(typeof lines[0].ts).toBe('string')
    rmSync(f, { force: true })
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `npm --prefix frontend run test -- lib.test`
Expected: FAIL (`logLine` / `logsPath` not exported)

- [ ] **Step 3: Add `logLine`/`logsPath` to `frontend/electron/lib.ts`**

```ts
import fs from 'node:fs'
import path from 'node:path'

export function logsPath(repoRoot: string): string {
  return path.join(repoRoot, 'logs', 'common.jsonl')
}

export function logLine(file: string, obj: Record<string, unknown>): void {
  try {
    fs.mkdirSync(path.dirname(file), { recursive: true })
    fs.appendFileSync(file, JSON.stringify({ ts: new Date().toISOString(), ...obj }) + '\n')
  } catch {
    /* never throw */
  }
}
```

- [ ] **Step 4: Emit events in `frontend/electron/main.ts`**

Compute `const logFile = logsPath(repoRoot)` once. Add `logLine(logFile, {source:'electron', event, ...})` at:
- `electron.start` (whenReady);
- `electron.sidecar.spawn` with `{command, args}` (in `startSidecar`);
- `electron.api.wait` with `{ok, attempts?}` after `waitForApi`;
- `electron.window` (createWindow), `electron.tray.hide` (on hide), `electron.quit` (before app.quit / before-quit).
Import `logLine`, `logsPath` from `./lib`.

- [ ] **Step 5: Run gates** → `npm --prefix frontend run test typecheck lint build` all PASS (verify `dist-electron/main.js` still emits). Report.

- [ ] **Step 6: Commit**

```bash
git add frontend/electron ':!frontend/node_modules'
git commit -m "feat(electron): unified jsonl logging (sidecar/api-wait/window/tray/quit)"
```

---

## Task 5: yt-debugger skill + docs + final sweep

**Files:** `skills/yt-debugger/SKILL.md`, `.gitignore`, `README.md`, `CLAUDE.md`. Gates: both suites.

- [ ] **Step 1: gitignore `logs/`**

Append `logs/` to `.gitignore`.

- [ ] **Step 2: Create `skills/yt-debugger/SKILL.md`**

````markdown
---
name: yt-debugger
description: Use when debugging the yt_summary app (empty UI, a hung/failed command, an API/pipeline error). Runs the backend, introspects the API schema via /openapi.json, makes probe calls, and filters the unified logs/common.jsonl with jq to trace an issue across backend/electron/frontend.
---

# yt-debugger

Diagnose yt_summary end-to-end. All runtimes log to `logs/common.jsonl`
(`{ts, source, level, event, msg, ...ctx}`); `source ∈ backend|electron|frontend`.

## 1. Run the backend
```bash
uv run yt-ai serve &        # http://127.0.0.1:8000 ; kill %1 when done
```
Electron is a GUI — launch `npm --prefix frontend run electron:dev` manually if you need it; its
main-process events land in the same log with `source=electron`.

## 2. Understand the API (schema)
```bash
curl -s 127.0.0.1:8000/openapi.json | jq '.paths | keys'
curl -s 127.0.0.1:8000/openapi.json | jq '.paths["/videos/{video_id}"].get'
```

## 3. Probe endpoints
```bash
curl -s 127.0.0.1:8000/status  | jq
curl -s 127.0.0.1:8000/videos  | jq 'length'
curl -s 127.0.0.1:8000/jobs    | jq -c '.[] | {id,kind,status,error}'
```

## 4. Query the unified log with jq
```bash
LOG=logs/common.jsonl
jq -c 'select(.level=="error")' $LOG                      # all errors
jq -c 'select(.source=="electron")' $LOG                  # electron lifecycle (sidecar/api wait)
jq -c 'select(.event|startswith("fetch"))' $LOG           # a fetch's steps
jq -c 'select(.job_id=="<id>")' $LOG                      # one job's full trace
jq -c '{ts,source,event,msg}' $LOG | tail -30            # recent, compact
tail -f $LOG | jq -c '{ts,source,event,msg}'              # live tail
```

## 5. Correlate across runtimes
A failing UI action leaves a `source=frontend` `ui.api_error` line (with `status`/`path`); find the
matching backend `job.*`/`fetch.*` events near the same `ts` to see the server-side cause. If the
last backend line before a hang is e.g. `fetch.download` or a discover/cookie step, that's where it stalled.

## Notes
- The log is append-only JSON Lines; never edit it. Delete/rotate manually if it grows.
- Logging never raises — an absent line means the code path wasn't reached (or errored before logging).
````

- [ ] **Step 3: Docs**

- README: a "Debugging" section — `logs/common.jsonl` (unified, `source`-tagged), `YT_LOG_FILE`, the `/log` endpoint, and the `yt-debugger` skill + 2 jq one-liners.
- `CLAUDE.md`: add `obs.py` + the logging convention (all runtimes → `logs/common.jsonl`) + the `yt-debugger` skill to the catalog.

- [ ] **Step 4: Final sweep**

Run: `uv run pytest -q` → all PASS (report count); `-W error::DeprecationWarning` clean; `uv run --with ruff ruff check .` clean.
Run: `npm --prefix frontend run test typecheck lint build` → all PASS (report count).
Confirm `git status` shows no `logs/`/`node_modules` staged.

- [ ] **Step 5: Commit**

```bash
git add skills/yt-debugger/SKILL.md .gitignore README.md CLAUDE.md
git commit -m "docs: yt-debugger skill + debugging docs; finish SP7"
```

- [ ] **Step 6: Report roadmap-memory update to the controller**

Report SP7 done: unified `logs/common.jsonl` (backend `obs.log_event`, electron `logLine`, frontend `POST /log`), targeted workflow events (fetch/discover/job lifecycle, electron sidecar/api-wait), and the `yt-debugger` skill (serve + /openapi.json + jq recipes).

---

## Self-Review Notes

- **Spec coverage:** JSONL `obs.log_event` never-raises + `Config.log_file` (T1), `POST /log` + backend workflow + job-lifecycle events (T2), frontend `log()` + `ApiError` logging with no import cycle (T3), electron `logLine`/`logsPath` + main events (T4), `yt-debugger` skill + docs + gitignore (T5). Rotation/OTel/live-viewer deferred per spec.
- **Placeholder scan:** none — every code step is complete.
- **Type/name consistency:** `log_event(source, event, level, msg, *, log_file, **ctx)` / `blog(...)` used by app/jobs/cli; `LogIn` fields match the `/log` handler + the frontend `log()` body (`event/level/msg/ctx`); `apiBase()` extracted to its own module so `client.ts → log.ts → apiBase.ts` has no cycle; electron `logLine(file, obj)`/`logsPath(repoRoot)` match the test + main usage.
- **Toolchain isolation:** T1–T2 pytest/ruff; T3–T4 `npm --prefix frontend run *`; T5 both. Log path via `YT_LOG_FILE` (Python tests) / explicit temp path (electron test) keeps every test's writes in `tmp_path`/tmpdir.
- **Never-raises discipline:** both `obs.log_event` and `logLine` swallow their own errors; `log()` is fire-and-forget — a broken log path or down endpoint can't take down the app.
```
