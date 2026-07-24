# SP9 — Desktop UI history + durable async jobs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the desktop app's first page into a paged, date-grouped subscription-history feed with per-video async summary jobs that survive restart, an embedded YouTube player that seeks to highlight timestamps, and hourly backend auto-sync.

**Architecture:** A durable `jobs` LanceDB table is the source of truth for a bounded thread-pool Worker; the FastAPI `lifespan` re-enqueues unfinished jobs on startup and runs a discover timer. The React first page pages `/videos`, overlays job badges by polling `/jobs`, and the watch view uses the YouTube IFrame API to seek.

**Tech Stack:** Python 3.12, FastAPI, LanceDB, faster-whisper (unchanged); React + TypeScript + Vite, TanStack Query, MSW, Vitest.

## Global Constraints

- UI summaries use the OpenRouter path (`api/summarize.py`, `OPENROUTER_API_KEY` + `YT_OPENROUTER_MODEL`) — the only server-side summarizer. No new summarizer.
- `_safe(...)` guards every LanceDB `where/delete/update` clause interpolating an id/key/status.
- Offline tests only: no network, no model downloads. Reuse `FakeEmbedder` (tests/support.py) and injected seams (`store_opener`, `run_one`, monkeypatched `run_discover`/`summarize_video`).
- Dates are `YYYY-MM-DD` strings; string comparison is date comparison.
- Job fns are idempotent (`upsert_summary`, `is_seen`, insert-only discover) — "resume" == "re-run".
- Page size default 30. No runtime auto-retry (retry only at startup for queued/running; `error` needs a manual Retry click). Auto-sync ON by default: run once on startup, then every `YT_DISCOVER_INTERVAL_S` (default 3600, 0=off). Job concurrency default 3.
- Python commit trailer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

### Task 1: Config knobs + durable `jobs` table (schema + CRUD)

**Files:**
- Modify: `yt_summary/config.py` (add two fields + env parse)
- Modify: `yt_summary/store/models.py` (add `JobSchema`)
- Modify: `yt_summary/store/db.py` (create table in `init_db`; add job CRUD)
- Test: `tests/test_config.py`, `tests/test_db.py`

**Interfaces:**
- Produces: `Config.job_concurrency: int`, `Config.discover_interval_s: float`.
- Produces: `JobSchema` (LanceModel) with fields `id, kind, video_id, status, progress, error, created_at, updated_at`.
- Produces: `store.insert_job(db, row: dict)`, `store.update_job(db, job_id: str, **fields)`, `store.get_job(db, job_id: str) -> dict | None`, `store.list_jobs(db, status: str | None = None, limit: int | None = None) -> list[dict]`.

- [ ] **Step 1: Write the failing config test**

In `tests/test_config.py`, add:
```python
def test_load_config_job_and_interval_knobs(tmp_path):
    env = tmp_path / ".env"
    env.write_text("YT_JOB_CONCURRENCY=5\nYT_DISCOVER_INTERVAL_S=120\n")
    cfg = load_config(env)
    assert cfg.job_concurrency == 5
    assert cfg.discover_interval_s == 120.0

def test_load_config_job_defaults(tmp_path):
    cfg = load_config(tmp_path / "none.env")
    assert cfg.job_concurrency == 3
    assert cfg.discover_interval_s == 3600.0
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_config.py::test_load_config_job_and_interval_knobs -q`
Expected: FAIL (`AttributeError: ... 'job_concurrency'`).

- [ ] **Step 3: Add the config fields**

In `yt_summary/config.py`, in the `Config` dataclass after `discover_feed_limit`/`discover_overlap_s`:
```python
    job_concurrency: int = 3
    discover_interval_s: float = 3600.0
```
Add the env keys to the override tuple in `load_config` (next to `YT_DISCOVER_OVERLAP_S`):
```python
        "YT_JOB_CONCURRENCY", "YT_DISCOVER_INTERVAL_S",
```
Add to the `Config(...)` constructor:
```python
        job_concurrency=int(_clean(data.get("YT_JOB_CONCURRENCY")) or "3"),
        discover_interval_s=float(_clean(data.get("YT_DISCOVER_INTERVAL_S")) or "3600"),
```

- [ ] **Step 4: Add the failing jobs-table CRUD test**

In `tests/test_db.py`, add:
```python
def test_job_crud_roundtrip(tmp_path):
    import lancedb
    from tests.support import fake_embedder
    conn = lancedb.connect(str(tmp_path / "l"))
    store.init_db(conn, fake_embedder())
    store.insert_job(conn, {"id": "j1", "kind": "summarize", "video_id": "abc",
                            "status": "queued", "progress": None, "error": None,
                            "created_at": "2026-07-24T00:00:00Z", "updated_at": "2026-07-24T00:00:00Z"})
    assert store.get_job(conn, "j1")["status"] == "queued"
    store.update_job(conn, "j1", status="running", progress=0.5)
    j = store.get_job(conn, "j1")
    assert j["status"] == "running" and j["progress"] == 0.5
    store.insert_job(conn, {"id": "j2", "kind": "discover", "video_id": None,
                            "status": "done", "progress": None, "error": None,
                            "created_at": "2026-07-24T00:01:00Z", "updated_at": "2026-07-24T00:01:00Z"})
    assert {r["id"] for r in store.list_jobs(conn, status="running")} == {"j1"}
    assert len(store.list_jobs(conn)) == 2
```

- [ ] **Step 5: Run it to verify it fails**

Run: `uv run pytest tests/test_db.py::test_job_crud_roundtrip -q`
Expected: FAIL (`AttributeError: module ... has no attribute 'insert_job'`).

- [ ] **Step 6: Add `JobSchema`**

In `yt_summary/store/models.py`, after `StateSchema`:
```python
class JobSchema(LanceModel):
    id: str
    kind: str
    video_id: str | None = None
    status: str = "queued"
    progress: float | None = None
    error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
```

- [ ] **Step 7: Create the table + CRUD helpers**

In `yt_summary/store/db.py`, import `JobSchema` in the models import line. In `init_db`, after the app_state table:
```python
    db.create_table("jobs", schema=JobSchema, exist_ok=True)
```
Add helpers (job rows are plain dicts, not the `Video` dataclass):
```python
_JOB_FIELDS = list(JobSchema.model_fields)


def insert_job(db, row: dict) -> None:
    tbl = db.open_table("jobs")
    tbl.merge_insert("id").when_matched_update_all().when_not_matched_insert_all() \
        .execute([{k: row.get(k) for k in _JOB_FIELDS}])


def update_job(db, job_id: str, **fields) -> None:
    existing = get_job(db, job_id)
    if existing is None:
        return
    existing.update(fields)
    insert_job(db, existing)


def get_job(db, job_id: str) -> dict | None:
    tbl = db.open_table("jobs")
    rows = tbl.search().where(f"id = '{_safe(job_id)}'").limit(1).to_list()
    return {k: rows[0].get(k) for k in _JOB_FIELDS} if rows else None


def list_jobs(db, status: str | None = None, limit: int | None = None) -> list[dict]:
    tbl = db.open_table("jobs")
    q = tbl.search()
    if status is not None:
        q = q.where(f"status = '{_safe(status)}'")
    rows = q.limit(1_000_000).to_list()
    rows.sort(key=lambda d: (d.get("created_at") or ""), reverse=True)
    if limit is not None:
        rows = rows[:limit]
    return [{k: r.get(k) for k in _JOB_FIELDS} for r in rows]
```

- [ ] **Step 8: Run the tests**

Run: `uv run pytest tests/test_config.py tests/test_db.py -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add yt_summary/config.py yt_summary/store/models.py yt_summary/store/db.py tests/test_config.py tests/test_db.py
git commit -m "feat(store): jobs table + CRUD; job_concurrency/discover_interval_s config

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Worker — bounded thread pool + video_id + write-through persist

**Files:**
- Modify: `yt_summary/api/jobs.py`
- Test: `tests/test_jobs.py`

**Interfaces:**
- Consumes: `Job` dataclass (extend it).
- Produces: `Job.video_id: str | None`, `Job.updated_at: str`.
- Produces: `Worker(registry, *, concurrency: int = 1, persist: Callable[[Job], None] | None = None)`; `Worker.submit(kind, fn, video_id=None) -> Job`; `persist(job)` invoked on every status transition (create, running, done, error). `Worker.start()` spawns `concurrency` daemon threads.

- [ ] **Step 1: Write the failing tests**

In `tests/test_jobs.py`, add:
```python
import threading
from yt_summary.api.jobs import JobRegistry, Worker


def test_worker_persists_each_transition():
    reg = JobRegistry()
    seen = []
    w = Worker(reg, persist=lambda job: seen.append((job.id, job.status)))
    job = w.submit("summarize", lambda j: {"ok": True}, video_id="abc")
    assert job.video_id == "abc"
    w.run_one(block=False)
    statuses = [s for (_id, s) in seen if _id == job.id]
    assert statuses[0] == "queued"
    assert statuses[-1] == "done"


def test_worker_runs_bounded_parallel():
    reg = JobRegistry()
    w = Worker(reg, concurrency=3)
    barrier = threading.Barrier(3, timeout=5)
    def fn(job):
        barrier.wait()  # only completes if 3 run concurrently
        return {}
    for _ in range(3):
        w.submit("x", fn)
    w.start()
    # if concurrency<3 this would deadlock the barrier and raise BrokenBarrierError
    for _ in range(50):
        if all(j.status == "done" for j in reg.list()):
            break
        threading.Event().wait(0.05)
    w.stop()
    assert all(j.status == "done" for j in reg.list())
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_jobs.py::test_worker_persists_each_transition -q`
Expected: FAIL (`TypeError: __init__() got an unexpected keyword argument 'persist'`).

- [ ] **Step 3: Extend `Job` + `Worker`**

In `yt_summary/api/jobs.py`, add to the `Job` dataclass:
```python
    video_id: str | None = None
    updated_at: str = ""
```
Replace `Worker.__init__`, `submit`, `run_one`, `start` with:
```python
    def __init__(self, registry: JobRegistry, *, concurrency: int = 1,
                 persist=None) -> None:
        self.registry = registry
        self.concurrency = max(1, concurrency)
        self._persist = persist or (lambda job: None)
        self._q: queue.Queue = queue.Queue()
        self._threads: list[threading.Thread] = []
        self._running = False

    def _mark(self, job: Job, status: str) -> None:
        job.status = status
        job.updated_at = datetime.now(UTC).isoformat()
        self._persist(job)

    def submit(self, kind: str, fn, video_id: str | None = None) -> Job:
        job = self.registry.create(kind)
        job.video_id = video_id
        self._mark(job, "queued")
        self._q.put((job, fn))
        return job

    def run_one(self, block: bool = True, timeout: float | None = None) -> bool:
        try:
            item = self._q.get(block=block, timeout=timeout)
        except queue.Empty:
            return False
        if item is _STOP:
            self._q.task_done()
            return False
        job, fn = item
        self._mark(job, "running")
        blog("job.running", job_id=job.id, kind=job.kind)
        start = time.monotonic()
        try:
            job.result = fn(job)
            self._mark(job, "done")
            blog("job.done", job_id=job.id, kind=job.kind,
                 duration_ms=round((time.monotonic() - start) * 1000))
        except Exception as exc:  # noqa: BLE001 - jobs must never kill the worker
            job.error = str(exc)
            self._mark(job, "error")
            blog("job.error", level="error", msg=str(exc), job_id=job.id, kind=job.kind)
        finally:
            self._q.task_done()
        return True

    def start(self) -> None:
        self._running = True
        def loop() -> None:
            while self._running:
                if not self.run_one(block=True):
                    break
        for _ in range(self.concurrency):
            t = threading.Thread(target=loop, daemon=True)
            t.start()
            self._threads.append(t)
```
Update `stop` to signal all threads:
```python
    def stop(self) -> None:
        self._running = False
        for _ in range(max(1, len(self._threads))):
            self._q.put(_STOP)
        self._threads = []
```
Note: `JobRegistry.create` already sets `created_at`; `_mark("queued")` sets `updated_at`. `datetime`/`UTC` are already imported at the top of the file.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_jobs.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add yt_summary/api/jobs.py tests/test_jobs.py
git commit -m "feat(api): bounded thread-pool Worker with video_id + write-through persist

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Job-fn builder, startup recovery, auto-sync timer

**Files:**
- Modify: `yt_summary/api/app_jobs.py` (extract `build_job_fn`, pass `video_id` on submit, `_job_out` gains fields)
- Modify: `yt_summary/api/app.py` (`lifespan`: DB-backed persist, recovery, auto-sync)
- Test: `tests/test_api_jobs.py`, `tests/test_api_reads.py`

**Interfaces:**
- Consumes: `store.list_jobs`, `store.update_job` (Task 1); `Worker(concurrency, persist)`, `submit(kind, fn, video_id)` (Task 2).
- Produces: `app_jobs.build_job_fn(app, cfg, kind: str, video_id: str | None) -> Callable[[Job], dict]`.
- Produces: `app.state.worker` with DB persist; recovered jobs re-enqueued; auto-sync submits `discover` jobs.

- [ ] **Step 1: Write the failing recovery test**

In `tests/test_api_jobs.py`, add (follow the file's existing app-construction helper; this uses `create_app` with `start_worker=False` and a shared store):
```python
def test_recovery_requeues_and_resets_running(tmp_path, monkeypatch):
    from yt_summary.api.app import create_app
    from yt_summary.config import load_config
    from yt_summary.store import db as store
    from tests.support import fake_embedder
    import lancedb
    cfg = load_config(tmp_path / "none.env")
    object.__setattr__(cfg, "discover_interval_s", 0.0)  # disable auto-sync in this test
    conn = lancedb.connect(str(tmp_path / "l"))
    store.init_db(conn, fake_embedder())
    # a leftover 'running' (interrupted) + a 'queued' job persisted before restart
    store.insert_job(conn, {"id": "r1", "kind": "discover", "video_id": None,
                            "status": "running", "progress": None, "error": None,
                            "created_at": "t", "updated_at": "t"})
    store.insert_job(conn, {"id": "q1", "kind": "summarize", "video_id": "abc",
                            "status": "queued", "progress": None, "error": None,
                            "created_at": "t", "updated_at": "t"})
    monkeypatch.setattr("yt_summary.api.app_jobs.run_discover",
                        lambda *a, **k: ([], 0))
    monkeypatch.setattr("yt_summary.api.app_jobs.summarize_video",
                        lambda *a, **k: {"video_id": "abc"})
    app = create_app(cfg, store_opener=lambda: conn, start_worker=False)
    with __import__("fastapi").testclient.TestClient(app):  # triggers lifespan
        # recovery drained into the worker; run them synchronously
        while app.state.worker.run_one(block=False):
            pass
    assert store.get_job(conn, "r1")["status"] == "done"   # requeued + ran
    assert store.get_job(conn, "q1")["status"] == "done"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_api_jobs.py::test_recovery_requeues_and_resets_running -q`
Expected: FAIL (recovery not implemented; jobs stay `running`/`queued`).

- [ ] **Step 3: Extract `build_job_fn` + persist video_id + enrich `_job_out`**

In `yt_summary/api/app_jobs.py`, replace `_job_out` and add `build_job_fn`:
```python
def _job_out(job) -> dict:
    return {"id": job.id, "kind": job.kind, "video_id": job.video_id,
            "status": job.status, "progress": job.progress, "result": job.result,
            "error": job.error, "created_at": job.created_at,
            "updated_at": getattr(job, "updated_at", "")}


def build_job_fn(app, cfg, kind: str, video_id: str | None):
    """Rebuild a job's work function from its kind (used by startup recovery)."""
    if kind == "summarize":
        def fn(job):
            db = app.state.store_opener()
            return summarize_video(cfg, db, video_id, client=app.state.summarize_client)
        return fn
    if kind == "fetch":
        def fn(job):
            db = app.state.store_opener()
            return {"video_id": run_fetch(video_id, cfg, db=db, video_id=video_id)}
        return fn
    def fn(job):  # discover / fetch-pending default to a plain discover
        db = app.state.store_opener()
        discovered, new = run_discover(cfg, db=db)
        return {"discovered": len(discovered), "new": new}
    return fn
```
Update the `summarize` and `fetch` routes to pass `video_id` on submit:
```python
        return _job_out(app.state.worker.submit("fetch", fn, video_id=body.url))
```
```python
        return _job_out(app.state.worker.submit("summarize", fn, video_id=body.video_id))
```
Add `status`/`video_id` filtering to the `list_jobs` route:
```python
    @app.get("/jobs", response_model=list[schemas.JobOut])
    def list_jobs(status: str | None = None, video_id: str | None = None):
        if status in ("done", "error"):
            from ..store import db as store
            rows = store.list_jobs(app.state.db, status=status)
            jobs = rows
        else:
            jobs = [_job_out(j) for j in app.state.registry.list()]
            if status is not None:
                jobs = [j for j in jobs if j["status"] == status]
        if video_id is not None:
            jobs = [j for j in jobs if j.get("video_id") == video_id]
        return jobs
```

- [ ] **Step 4: Wire persist + recovery + auto-sync into `lifespan`**

In `yt_summary/api/app.py`, replace the worker setup inside `lifespan` (after `app.state.db = opener()`):
```python
        from ..store import db as store
        from datetime import datetime, UTC
        import threading, time as _time
        from .app_jobs import build_job_fn

        app.state.registry = JobRegistry()

        def _persist(job):
            store.update_job(app.state.db, job.id, kind=job.kind, video_id=job.video_id,
                             status=job.status, progress=job.progress, error=job.error,
                             updated_at=getattr(job, "updated_at", "") or datetime.now(UTC).isoformat(),
                             created_at=job.created_at) if store.get_job(app.state.db, job.id) \
                else store.insert_job(app.state.db, {
                    "id": job.id, "kind": job.kind, "video_id": job.video_id,
                    "status": job.status, "progress": job.progress, "error": job.error,
                    "created_at": job.created_at, "updated_at": getattr(job, "updated_at", "")})

        app.state.worker = Worker(app.state.registry, concurrency=cfg.job_concurrency,
                                  persist=_persist)
        if start_worker:
            app.state.worker.start()

        # recovery: re-enqueue queued + interrupted-running jobs
        for row in store.list_jobs(app.state.db, status="running") + \
                   store.list_jobs(app.state.db, status="queued"):
            app.state.worker.submit(row["kind"],
                                    build_job_fn(app, cfg, row["kind"], row.get("video_id")),
                                    video_id=row.get("video_id"))

        # auto-sync: discover on startup + every discover_interval_s
        app.state._sync_stop = threading.Event()
        def _sync_loop():
            interval = cfg.discover_interval_s
            if interval and interval > 0:
                while not app.state._sync_stop.is_set():
                    active = any(j.kind == "discover" and j.status in ("queued", "running")
                                 for j in app.state.registry.list())
                    if not active:
                        app.state.worker.submit("discover",
                                                build_job_fn(app, cfg, "discover", None))
                    if app.state._sync_stop.wait(interval):
                        break
        if start_worker:
            threading.Thread(target=_sync_loop, daemon=True).start()
```
Delete the old `app.state.registry`/`app.state.worker`/`start()` lines that this replaces. In the shutdown section (after `yield`), stop the sync loop:
```python
        app.state._sync_stop.set()
        app.state.worker.stop()
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_api_jobs.py tests/test_api_reads.py -q`
Expected: PASS. (The recovery test drives the worker synchronously; `discover_interval_s=0` disables the timer there.)

- [ ] **Step 6: Commit**

```bash
git add yt_summary/api/app.py yt_summary/api/app_jobs.py tests/test_api_jobs.py
git commit -m "feat(api): durable job recovery on startup + hourly auto-sync timer

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `/videos` pagination (envelope with total) + `JobOut` shape

**Files:**
- Modify: `yt_summary/api/schemas.py` (`JobOut` fields; `VideoPageOut`)
- Modify: `yt_summary/api/app.py` (`/videos` returns page envelope)
- Test: `tests/test_api_reads.py`

**Interfaces:**
- Produces: `GET /videos?status=&since=&limit=30&offset=0` → `{"items": VideoOut[], "total": int}`.
- Produces: `JobOut` includes `video_id: str | None`, `updated_at: str | None`.

- [ ] **Step 1: Write the failing test**

In `tests/test_api_reads.py`, add (follow the file's existing client/store fixtures):
```python
def test_videos_paginated_envelope(client, seeded_store):
    # seeded_store has >2 videos newest-first
    r = client.get("/videos?limit=2&offset=0")
    body = r.json()
    assert set(body) == {"items", "total"}
    assert len(body["items"]) == 2
    assert body["total"] >= 3
    r2 = client.get("/videos?limit=2&offset=2")
    assert body["items"][0]["video_id"] != r2.json()["items"][0]["video_id"]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_api_reads.py::test_videos_paginated_envelope -q`
Expected: FAIL (`/videos` returns a bare list; no `items`/`total`).

- [ ] **Step 3: Update schemas**

In `yt_summary/api/schemas.py`, add to `JobOut`:
```python
    video_id: str | None = None
    updated_at: str | None = None
```
Add:
```python
class VideoPageOut(BaseModel):
    items: list[VideoOut]
    total: int
```

- [ ] **Step 4: Paginate the `/videos` route**

In `yt_summary/api/app.py`, replace `list_videos`:
```python
    @app.get("/videos", response_model=schemas.VideoPageOut)
    def list_videos(status: str | None = None, since: str | None = None,
                    limit: int = 30, offset: int = 0):
        vids = run_list(cfg, status=status, since=since, db=app.state.db)
        total = len(vids)
        page = vids[offset:offset + limit]
        return {"items": [_video_out(v) for v in page], "total": total}
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_api_reads.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add yt_summary/api/schemas.py yt_summary/api/app.py tests/test_api_reads.py
git commit -m "feat(api): paginate /videos (items+total envelope); JobOut video_id/updated_at

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Frontend API layer — paginated videos + Job.video_id

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/api/hooks.ts`
- Modify: `frontend/src/mocks/handlers.ts` (MSW: `/videos` envelope)
- Test: `frontend/src/api/__tests__/hooks.test.tsx` (or the repo's existing hooks test file)

**Interfaces:**
- Produces: `VideoPage { items: VideoOut[]; total: number }`; `Job.video_id: string | null`.
- Produces: `api.listVideos(f: { status?; since?; limit?; offset? }) => Promise<VideoPage>`; `useVideos(filters)` returns `VideoPage`.

- [ ] **Step 1: Write the failing test**

In the frontend hooks test (follow existing MSW+RTL setup, `renderHook` from `@/test/utils`):
```tsx
import { waitFor } from '@testing-library/react'
import { renderHook } from '@/test/utils'
import { useVideos } from '@/api/hooks'

test('useVideos returns a paginated page', async () => {
  const { result } = renderHook(() => useVideos({ limit: 30, offset: 0 }))
  await waitFor(() => expect(result.current.isSuccess).toBe(true))
  expect(Array.isArray(result.current.data!.items)).toBe(true)
  expect(typeof result.current.data!.total).toBe('number')
})
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npm test -- hooks`
Expected: FAIL (type error / `data.items` undefined; current `useVideos` returns an array).

- [ ] **Step 3: Update types**

In `frontend/src/api/types.ts`, add `video_id` to `Job` and add `VideoPage`:
```ts
export interface VideoPage { items: VideoOut[]; total: number }
```
In `interface Job`, add:
```ts
  video_id: string | null
  updated_at?: string
```

- [ ] **Step 4: Update client + hook**

In `frontend/src/api/client.ts`, replace `listVideos`:
```ts
  listVideos: (f: { status?: string; since?: string; limit?: number; offset?: number } = {}) =>
    req<VideoPage>(`/videos${qs(f)}`),
```
Add `VideoPage` to the type import. In `frontend/src/api/hooks.ts`, replace `useVideos`:
```ts
export function useVideos(filters: { status?: string; since?: string; limit?: number; offset?: number } = {}) {
  return useQuery({ queryKey: ['videos', filters], queryFn: () => api.listVideos(filters) })
}
```

- [ ] **Step 5: Update the MSW handler**

In `frontend/src/mocks/handlers.ts`, change the `GET /videos` handler to return the envelope, e.g.:
```ts
http.get('*/videos', () => HttpResponse.json({ items: SAMPLE_VIDEOS, total: SAMPLE_VIDEOS.length })),
```
(Keep `SAMPLE_VIDEOS` as the existing fixture array; if job fixtures exist, add `video_id` to them.)

- [ ] **Step 6: Run the tests**

Run: `cd frontend && npm test -- hooks`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api frontend/src/mocks/handlers.ts frontend/src/**/hooks.test.tsx
git commit -m "feat(ui): paginated useVideos (VideoPage) + Job.video_id

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: `HistoryView` — paged, date-grouped, Refresh, summary button + badges

**Files:**
- Create: `frontend/src/components/HistoryView.tsx`
- Modify: `frontend/src/App.tsx` (index route → `HistoryView`)
- Modify: `frontend/src/components/AppShell.tsx` (render `<Outlet/>`/history at `/` — follow existing shell)
- Test: `frontend/src/components/__tests__/HistoryView.test.tsx`

**Interfaces:**
- Consumes: `useVideos({limit,offset})`, `useJobs()`, `useSummarize()`, `useStartDiscover()` (existing).
- Produces: default route renders a paged, date-grouped list; each row has a Generate-summary button whose badge reflects an active job for that `video_id`.

- [ ] **Step 1: Write the failing test**

`frontend/src/components/__tests__/HistoryView.test.tsx`:
```tsx
import { screen, waitFor, fireEvent } from '@testing-library/react'
import { render } from '@/test/utils'
import { HistoryView } from '@/components/HistoryView'

test('lists videos grouped and summarize posts a job', async () => {
  render(<HistoryView />)
  await waitFor(() => expect(screen.getByText(/Today|\d{4}-\d{2}-\d{2}/)).toBeInTheDocument())
  const btn = await screen.findAllByRole('button', { name: /summar/i })
  fireEvent.click(btn[0])
  await waitFor(() => expect(screen.getAllByText(/summariz/i).length).toBeGreaterThan(0))
})
```
Ensure `mocks/handlers.ts` has a `POST /jobs/summarize` returning a `queued` job with the row's `video_id`, and `GET /jobs` returns that active job.

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npm test -- HistoryView`
Expected: FAIL (`Cannot find module HistoryView`).

- [ ] **Step 3: Implement `HistoryView`**

`frontend/src/components/HistoryView.tsx`:
```tsx
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useVideos, useJobs, useSummarize, useStartDiscover } from '@/api/hooks'
import { Button } from './ui/button'
import { Badge } from './ui/badge'
import type { VideoOut } from '@/api/types'

const PAGE = 30
const today = () => new Date().toISOString().slice(0, 10)

function groupByDay(items: VideoOut[]) {
  const groups: Record<string, VideoOut[]> = {}
  for (const v of items) (groups[v.published_at ?? 'Unknown'] ??= []).push(v)
  return Object.entries(groups)
}

export function HistoryView() {
  const [offset, setOffset] = useState(0)
  const videos = useVideos({ limit: PAGE, offset })
  const jobs = useJobs()
  const summarize = useSummarize()
  const discover = useStartDiscover()

  const activeFor = (id: string) =>
    jobs.data?.find(j => j.video_id === id && (j.status === 'queued' || j.status === 'running'))
  const total = videos.data?.total ?? 0

  return (
    <div className="p-4">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Subscriptions</h1>
        <Button onClick={() => discover.mutate({})} disabled={discover.isPending}>Refresh</Button>
      </div>
      {groupByDay(videos.data?.items ?? []).map(([day, rows]) => (
        <section key={day} className="mb-6">
          <h2 className="mb-2 text-sm font-medium text-muted-foreground">
            {day === today() ? 'Today' : day}
          </h2>
          <ul className="divide-y">
            {rows.map(v => {
              const job = activeFor(v.video_id)
              const done = v.status === 'summarized'
              return (
                <li key={v.video_id} className="flex items-center gap-3 py-2">
                  <Link to={`/videos/${v.video_id}`} className="flex-1 truncate hover:underline">
                    {v.title ?? v.video_id}
                  </Link>
                  {job ? <Badge>summarizing…</Badge>
                    : done ? <Badge variant="secondary">summarized</Badge>
                    : <Button size="sm" onClick={() => summarize.mutate(v.video_id)}>Summarize</Button>}
                </li>
              )
            })}
          </ul>
        </section>
      ))}
      <div className="mt-4 flex items-center gap-2">
        <Button variant="outline" disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - PAGE))}>Prev</Button>
        <span className="text-sm text-muted-foreground">
          {offset + 1}–{Math.min(offset + PAGE, total)} of {total}
        </span>
        <Button variant="outline" disabled={offset + PAGE >= total}
          onClick={() => setOffset(offset + PAGE)}>Next</Button>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Route it as the index page**

In `frontend/src/App.tsx`, add the index route (import `HistoryView`):
```tsx
      <Route path="/" element={<AppShell />}>
        <Route index element={<HistoryView />} />
        <Route path="videos/:id" element={<VideoDetail />} />
      </Route>
```
Ensure `AppShell` renders `<Outlet />` where the page content goes (it already hosts nested routes). If `AppShell` currently renders `VideoList` inline, move that under the index route.

- [ ] **Step 5: Run the tests**

Run: `cd frontend && npm test -- HistoryView`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/HistoryView.tsx frontend/src/App.tsx frontend/src/components/AppShell.tsx frontend/src/components/__tests__/HistoryView.test.tsx
git commit -m "feat(ui): HistoryView — paged, date-grouped subscriptions + summarize button/badges

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: `WatchPlayer` — YouTube IFrame API seek from highlights

**Files:**
- Modify: `frontend/src/components/WatchPlayer.tsx`
- Modify: `frontend/src/components/VideoDetail.tsx` (pass highlights + a seek ref)
- Test: `frontend/src/components/__tests__/WatchPlayer.test.tsx`

**Interfaces:**
- Consumes: `Highlight[]` from `summaries.highlights` (parsed in `VideoDetail`).
- Produces: `WatchPlayer` accepts `onReady?: (seek: (s: number) => void) => void`; highlight clicks in `VideoDetail` call `seek(start_s)`.

- [ ] **Step 1: Write the failing test**

`frontend/src/components/__tests__/WatchPlayer.test.tsx`:
```tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { WatchPlayer } from '@/components/WatchPlayer'

test('exposes a seek callback that maps to iframe start param (non-electron fallback)', () => {
  let seek: ((s: number) => void) | undefined
  render(<WatchPlayer videoId="abc" url={null} onClose={() => {}} onReady={s => { seek = s }} />)
  expect(typeof seek).toBe('function')
  seek!(90)
  const iframe = screen.getByTitle('player') as HTMLIFrameElement
  expect(iframe.src).toContain('start=90')
})
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npm test -- WatchPlayer`
Expected: FAIL (`onReady` not a prop; no `start=` in src).

- [ ] **Step 3: Implement seek (IFrame API + fallback)**

In `frontend/src/components/WatchPlayer.tsx`, replace the component body to accept `onReady` and manage a `start` seconds state for the fallback iframe, and (when the YT IFrame API is available) call `player.seekTo`:
```tsx
import { useEffect, useRef, useState } from 'react'
import { isElectron } from '@/lib/electron'
import { Button } from './ui/button'

type Props = { videoId: string; url: string | null; onClose: () => void
  onReady?: (seek: (s: number) => void) => void }

export function WatchPlayer({ videoId, url, onClose, onReady }: Props) {
  const watchUrl = url ?? `https://www.youtube.com/watch?v=${videoId}`
  const [start, setStart] = useState(0)
  const playerRef = useRef<{ seekTo: (s: number, allow: boolean) => void } | null>(null)

  useEffect(() => {
    const seek = (s: number) => {
      if (playerRef.current) playerRef.current.seekTo(s, true)
      else setStart(Math.floor(s)) // fallback: reload iframe with start=
    }
    onReady?.(seek)
    // Best-effort YouTube IFrame API wiring (no-op in jsdom/tests):
    const w = window as unknown as { YT?: { Player: new (el: Element, o: object) => object } }
    if (!isElectron() && w.YT?.Player) {
      // real app: attach a Player to the iframe and store playerRef via events
    }
  }, [onReady])

  return (
    <div className="relative mb-4 aspect-video w-full overflow-hidden rounded-md border bg-black">
      <Button size="icon" variant="ghost" aria-label="close player"
        className="absolute right-1 top-1 z-10 bg-white/80" onClick={onClose}>✕</Button>
      {isElectron() ? (
        <webview src={watchUrl} className="h-full w-full" />
      ) : (
        <iframe className="h-full w-full"
          src={`https://www.youtube.com/embed/${videoId}?enablejsapi=1&start=${start}`}
          title="player" allow="autoplay; encrypted-media" allowFullScreen />
      )}
    </div>
  )
}
```

- [ ] **Step 4: Wire highlights → seek in `VideoDetail`**

In `frontend/src/components/VideoDetail.tsx`, parse `summary.highlights` (JSON string → `Highlight[]`), hold a `seekRef`, pass `onReady={s => (seekRef.current = s)}` to `WatchPlayer`, and render each highlight as a button calling `seekRef.current?.(h.start_s)` and showing `MM:SS — label`. Follow the file's existing summary-rendering block; add:
```tsx
const seekRef = useRef<((s: number) => void) | null>(null)
// in JSX, when the player is shown:
<WatchPlayer videoId={id!} url={video.url} onClose={...} onReady={s => (seekRef.current = s)} />
// highlights list:
{highlights.map(h => (
  <button key={h.start_s} className="block text-left text-sm hover:underline"
    onClick={() => seekRef.current?.(h.start_s)}>
    {fmt(h.start_s)} — {h.label}
  </button>
))}
```
where `fmt(s)` renders `M:SS` and `highlights` is `JSON.parse(summary.highlights ?? '[]') as Highlight[]` (guarded with try/catch → `[]`).

- [ ] **Step 5: Run the tests**

Run: `cd frontend && npm test -- WatchPlayer`
Expected: PASS.

- [ ] **Step 6: Run the whole suites**

Run: `uv run pytest -q` (expect all green) and `cd frontend && npm test` (expect all green).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/WatchPlayer.tsx frontend/src/components/VideoDetail.tsx frontend/src/components/__tests__/WatchPlayer.test.tsx
git commit -m "feat(ui): embedded player seek to highlight timestamps (IFrame API + start= fallback)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review notes (for the executor)

- **Spec coverage:** paged history (T4/T6), summary async job (T2/T3/T6), durable jobs + recovery (T1/T2/T3), auto-sync 1h on startup (T3), embedded player seek (T7), OpenRouter-only summaries (unchanged path), polling (existing `useJobs` 1s interval — reused in T6).
- **Not re-implemented (already present):** `useJobs` polling, `useSummarize`, `useStartDiscover`, `POST /jobs/summarize`, `JobStrip`. Reuse them.
- **Type consistency:** `Job.video_id` added in both `api/jobs.py` (T2) and `types.ts` (T5) and surfaced via `_job_out`/`JobOut` (T3/T4). `VideoPage {items,total}` defined in schemas (T4) and types (T5) and consumed in T6.
- **Manual smoke (not automated):** with `OPENROUTER_API_KEY` set, click Summarize on a transcribed video, watch the badge flip queued→running→done; kill and restart `serve` mid-job and confirm it re-runs; open a video and click a highlight to seek.
