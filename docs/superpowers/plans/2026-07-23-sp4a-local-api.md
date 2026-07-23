# SP4a Local FastAPI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local FastAPI server (`127.0.0.1`) exposing the yt_summary pipeline: read endpoints over the `run_*` cores, a background-job system for the multi-minute operations, and an automated OpenRouter summarizer — all offline-testable.

**Architecture:** A `yt_summary/api/` package. `jobs.py` = in-memory registry + a single-worker queue with a `run_one()` seam so tests drain synchronously. `summarize.py` = OpenRouter automated summarizer with an injectable client. `app.py` = a `create_app(cfg, *, store_opener, summarize_client, start_worker)` factory: read endpoints pass the shared store handle to the existing `run_*` cores; job endpoints enqueue closures that open their own store via `store_opener`. All external dependencies (store, LLM, worker thread) are injectable, so the whole API is tested with `TestClient` against a temp-dir LanceDB + fakes.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, pydantic v2, LanceDB, pytest (+httpx for TestClient), uv.

## Global Constraints

- Python 3.11+, `X | None` unions. uv; console script `yt-ai`.
- Reuse existing service functions unchanged: `run_fetch`, `run_search`, `run_discover`, `run_list`, `run_fetch_pending`, `run_feedback`, `run_recommend` (in `cli.py`), and store reads (`get_video`, `get_transcript_text`, `get_summary`, `count_by_status`, `list_chunks`, `upsert_summary`), plus `memory.mark_status`, `open_store`, `build_embedder`.
- **Injectable seams (offline tests):** `create_app(cfg, *, store_opener=None, summarize_client=None, start_worker=True)`. `store_opener` defaults to `lambda: open_store(cfg)`; tests pass `lambda: <temp-dir LanceDB opened with the fake embedder>` (NO model download). `summarize_client` is passed into summarize jobs; tests inject a fake. `start_worker=False` in tests — drain the queue via `worker.run_one(block=False)`.
- **Jobs:** in-memory only; a single daemon worker thread serializes heavy work; job functions open their OWN store via `store_opener()` (never share the request handle across threads). Job IDs are `uuid4().hex`; tests assert structure/transitions, not exact IDs. A job function raising sets `status="error"`, `error=<msg>`, and the worker survives to the next job.
- **Summarizer:** OpenRouter via the OpenAI-compatible client (`base_url="https://openrouter.ai/api/v1"`, `api_key=cfg.openrouter_api_key`, model `cfg.openrouter_model`). Highlights snap to the nearest real chunk `start_s` (never invented). Missing `openrouter_api_key` → clear error before any call.
- Server binds `127.0.0.1` only.
- Every task ends green (`uv run pytest -q`), `uv run --with ruff ruff check .` clean, `-W error::DeprecationWarning` clean, and is committed.

---

## File Structure

```
yt_summary/
  api/
    __init__.py
    schemas.py     pydantic request/response models
    jobs.py        Job, JobRegistry, Worker (run_one seam)
    summarize.py   summarize_video(cfg, db, video_id, client=None)
    app.py         create_app(...) + routes
  config.py        + openrouter_model
  cli.py           + serve command
pyproject.toml     + fastapi, uvicorn; dev + httpx
tests/
  test_jobs.py
  test_summarize.py
  test_api_reads.py
  test_api_jobs.py
```

---

## Task 1: Deps + config + jobs + schemas

**Files:**
- Modify: `pyproject.toml` (+ `fastapi`, `uvicorn`; dev + `httpx`), `yt_summary/config.py` (+ `openrouter_model`)
- Create: `yt_summary/api/__init__.py`, `yt_summary/api/schemas.py`, `yt_summary/api/jobs.py`
- Test: `tests/test_jobs.py`

**Interfaces:**
- `Config` gains `openrouter_model: str` (default `"openai/gpt-4o-mini"`).
- `jobs.Job` dataclass; `jobs.JobRegistry`; `jobs.Worker` with `submit(kind, fn) -> Job`, `run_one(block=True, timeout=None) -> bool`, `start()`, `stop()`.
- `schemas`: `VideoOut`, `VideoDetailOut`, `SearchHit`, `RecommendItem`, `FeedbackIn`, `JobOut`, `StatusOut`, `FetchIn`, `DiscoverIn`, `FetchPendingIn`, `SummarizeIn`.

- [ ] **Step 1: Add deps to `pyproject.toml`**

In `[project].dependencies` add:
```toml
    "fastapi>=0.110",
    "uvicorn>=0.29",
```
In `[project.optional-dependencies].dev` add `"httpx>=0.27"` (TestClient needs it).

- [ ] **Step 2: Add `openrouter_model` to config**

In `yt_summary/config.py`: add field `openrouter_model: str` to `Config` (after `openrouter_api_key`), add `"YT_OPENROUTER_MODEL"` to the override tuple, and add the constructor line:
```python
        openrouter_model=_clean(data.get("YT_OPENROUTER_MODEL")) or "openai/gpt-4o-mini",
```
Then add `openrouter_model="openai/gpt-4o-mini"` (or any value) to every test `Config(...)` helper (grep `openrouter_api_key=None` under `tests/` — add the new kwarg beside it). Run `uv run pytest -q` and fix each `Config()` the failure names.

- [ ] **Step 3: Write the failing test**

```python
# tests/test_jobs.py
from yt_summary.api import jobs


def test_worker_runs_job_to_done():
    w = jobs.Worker(jobs.JobRegistry())
    job = w.submit("test", lambda j: {"ok": True})
    assert job.status == "queued"
    assert w.run_one(block=False) is True
    assert job.status == "done"
    assert job.result == {"ok": True}


def test_worker_records_error_and_survives():
    reg = jobs.JobRegistry()
    w = jobs.Worker(reg)
    bad = w.submit("test", lambda j: (_ for _ in ()).throw(RuntimeError("boom")))
    good = w.submit("test", lambda j: {"ok": 1})
    assert w.run_one(block=False) is True   # bad
    assert bad.status == "error" and "boom" in bad.error
    assert w.run_one(block=False) is True   # worker survived → good runs
    assert good.status == "done"


def test_run_one_empty_returns_false():
    w = jobs.Worker(jobs.JobRegistry())
    assert w.run_one(block=False) is False


def test_registry_get_and_list():
    reg = jobs.JobRegistry()
    w = jobs.Worker(reg)
    job = w.submit("k", lambda j: {})
    assert reg.get(job.id) is job
    assert job in reg.list()
    assert reg.get("nope") is None
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/test_jobs.py -q`
Expected: FAIL (`ModuleNotFoundError: yt_summary.api.jobs`)

- [ ] **Step 5: Implement `yt_summary/api/__init__.py` (empty), `jobs.py`, `schemas.py`**

`yt_summary/api/jobs.py`:
```python
from __future__ import annotations
import queue
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Callable


@dataclass
class Job:
    id: str
    kind: str
    status: str = "queued"
    progress: float | None = None
    result: dict | None = None
    error: str | None = None
    created_at: str = ""


class JobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, kind: str) -> Job:
        job = Job(id=uuid.uuid4().hex, kind=kind, created_at=datetime.now(UTC).isoformat())
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        with self._lock:
            return list(self._jobs.values())


_STOP = object()


class Worker:
    def __init__(self, registry: JobRegistry) -> None:
        self.registry = registry
        self._q: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None

    def submit(self, kind: str, fn: Callable[[Job], dict]) -> Job:
        job = self.registry.create(kind)
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
        job.status = "running"
        try:
            job.result = fn(job)
            job.status = "done"
        except Exception as exc:  # noqa: BLE001 - jobs must never kill the worker
            job.error = str(exc)
            job.status = "error"
        finally:
            self._q.task_done()
        return True

    def start(self) -> None:
        def loop() -> None:
            while True:
                if not self.run_one(block=True):
                    if self._thread is None:
                        break
        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._thread = None
        self._q.put(_STOP)
```

`yt_summary/api/schemas.py`:
```python
from __future__ import annotations
from pydantic import BaseModel


class VideoOut(BaseModel):
    video_id: str
    title: str | None = None
    url: str | None = None
    status: str | None = None
    published_at: str | None = None
    duration_s: int | None = None


class VideoDetailOut(VideoOut):
    transcript: str | None = None
    summary: dict | None = None


class SearchHit(BaseModel):
    video_id: str
    start_s: float | None = None
    end_s: float | None = None
    text: str | None = None


class RecommendItem(VideoOut):
    score: float


class FeedbackIn(BaseModel):
    video_id: str
    signal: int


class JobOut(BaseModel):
    id: str
    kind: str
    status: str
    progress: float | None = None
    result: dict | None = None
    error: str | None = None
    created_at: str


class StatusOut(BaseModel):
    counts: dict[str, int]


class FetchIn(BaseModel):
    url: str
    force: bool = False


class DiscoverIn(BaseModel):
    after: str | None = None
    deep: bool = False
    min_duration: int = 120


class FetchPendingIn(BaseModel):
    since: str | None = None
    limit: int | None = None


class SummarizeIn(BaseModel):
    video_id: str
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_jobs.py -q`
Expected: PASS. Then full suite `uv run pytest -q` PASS (config kwarg added everywhere).

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml yt_summary/config.py yt_summary/api/__init__.py yt_summary/api/jobs.py yt_summary/api/schemas.py tests/ uv.lock
git commit -m "feat: api deps + config + jobs registry/worker + schemas"
```

---

## Task 2: summarize.py — automated OpenRouter summarizer

**Files:**
- Create: `yt_summary/api/summarize.py`
- Test: `tests/test_summarize.py`

**Interfaces:**
- Consumes: `store.get_transcript_text`, `store.list_chunks`, `store.upsert_summary`, `memory.mark_status`.
- Produces: `summarize_video(cfg, db, video_id, client=None) -> dict` (keys `summary_md`, `highlights`, `qa`); helper `_nearest(sorted_starts, x)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_summarize.py
import json
import lancedb
import pytest
from pathlib import Path
from tests.support import fake_embedder
from yt_summary.config import Config
from yt_summary.store import db as store
from yt_summary.store.models import Video, TranscriptRow
from yt_summary.api import summarize


def _cfg(**over):
    base = dict(downloads_dir=Path("dl"), proxy_username=None, proxy_password=None,
                cookies_browser=None, whisper_model="small", whisper_device="cpu",
                whisper_compute_type="int8", openrouter_api_key="sk-test",
                store_path=Path("lance"), embedding_backend="local", embedding_model=None,
                chunk_target_s=45.0, openai_api_key=None, openrouter_model="test/model")
    base.update(over)
    return Config(**base)


def _db(tmp_path):
    conn = lancedb.connect(str(tmp_path / "lance"))
    store.init_db(conn, fake_embedder())
    return conn


class _FakeClient:
    """Mimics openai client: .chat.completions.create(...).choices[0].message.content"""
    def __init__(self, content: str):
        self._content = content
        self.chat = self  # so client.chat.completions works
        self.completions = self

    def create(self, **kwargs):
        msg = type("M", (), {"content": self._content})
        choice = type("C", (), {"message": msg})
        return type("R", (), {"choices": [choice]})


def _seed(conn, vid="v1"):
    store.upsert_video(conn, Video(video_id=vid, url="u", status="transcribed"))
    store.insert_transcript(conn, TranscriptRow(vid, "captions", "en", "hello world", "t0"))
    store.replace_chunks(conn, vid, [
        {"id": f"{vid}:0", "video_id": vid, "start_s": 0.0, "end_s": 10.0, "text": "hello"},
        {"id": f"{vid}:1", "video_id": vid, "start_s": 10.0, "end_s": 20.0, "text": "world"}])


def test_summarize_persists_and_snaps(tmp_path):
    conn = _db(tmp_path); _seed(conn)
    content = json.dumps({
        "summary_md": "A summary.",
        "highlights": [{"start_s": 11.7, "label": "the world part"}],  # 11.7 → nearest 10.0
        "qa": [{"q": "what?", "a": "world"}]})
    out = summarize.summarize_video(_cfg(), conn, "v1", client=_FakeClient(content))
    assert out["summary_md"] == "A summary."
    saved = store.get_summary(conn, "v1")
    assert saved["summary_md"] == "A summary."
    assert json.loads(saved["highlights"])[0]["start_s"] == 10.0   # snapped
    assert store.get_video(conn, "v1").status == "summarized"


def test_summarize_no_transcript_errors(tmp_path):
    conn = _db(tmp_path)
    store.upsert_video(conn, Video(video_id="x", url="u", status="downloaded"))
    with pytest.raises(ValueError):
        summarize.summarize_video(_cfg(), conn, "x", client=_FakeClient("{}"))


def test_summarize_missing_key_errors(tmp_path):
    conn = _db(tmp_path); _seed(conn)
    with pytest.raises(ValueError):
        summarize.summarize_video(_cfg(openrouter_api_key=None), conn, "v1", client=None)


def test_nearest_snaps():
    assert summarize._nearest([0.0, 10.0, 20.0], 11.7) == 10.0
    assert summarize._nearest([0.0, 10.0, 20.0], 16.0) == 20.0
    assert summarize._nearest([], 5.0) == 5.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_summarize.py -q`
Expected: FAIL (`ModuleNotFoundError: yt_summary.api.summarize`)

- [ ] **Step 3: Implement `yt_summary/api/summarize.py`**

```python
# yt_summary/api/summarize.py
from __future__ import annotations
import json
from datetime import datetime, UTC
from ..config import Config
from ..store import db as store
from .. import memory

_SYSTEM = (
    "You summarize a YouTube video transcript. Respond with a JSON object with keys: "
    "summary_md (2-4 sentence executive summary plus key bullets, markdown), "
    "highlights (array of {start_s: number, label: string}, 3-8 items), "
    "qa (array of {q: string, a: string}, 3-6 items). "
    "Ground everything in the transcript. Pick start_s values from the provided chunk anchors."
)


def _nearest(sorted_starts: list[float], x: float) -> float:
    if not sorted_starts:
        return x
    return min(sorted_starts, key=lambda s: abs(s - x))


def _client(cfg: Config):
    from openai import OpenAI
    return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=cfg.openrouter_api_key)


def summarize_video(cfg: Config, db, video_id: str, client=None) -> dict:
    text = store.get_transcript_text(db, video_id)
    if not text:
        raise ValueError(f"no transcript for {video_id}; fetch it first")
    chunks = store.list_chunks(db, video_id)
    anchors = [{"start_s": c.get("start_s"), "text": c.get("text")} for c in chunks]

    if client is None:
        if not cfg.openrouter_api_key:
            raise ValueError("summarization requires OPENROUTER_API_KEY")
        client = _client(cfg)

    user = json.dumps({"transcript": text, "chunk_anchors": anchors})
    resp = client.chat.completions.create(
        model=cfg.openrouter_model,
        messages=[{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
        response_format={"type": "json_object"},
    )
    data = json.loads(resp.choices[0].message.content)

    starts = sorted(float(c["start_s"]) for c in chunks if c.get("start_s") is not None)
    for h in data.get("highlights", []):
        if "start_s" in h:
            h["start_s"] = _nearest(starts, float(h["start_s"]))

    store.upsert_summary(
        db, video_id, data.get("summary_md", ""),
        json.dumps(data.get("highlights", [])), json.dumps(data.get("qa", [])),
        cfg.openrouter_model, datetime.now(UTC).isoformat())
    memory.mark_status(db, video_id, "summarized")
    return data
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_summarize.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add yt_summary/api/summarize.py tests/test_summarize.py
git commit -m "feat: automated openrouter summarizer"
```

---

## Task 3: app.py — factory + read/feedback endpoints

**Files:**
- Create: `yt_summary/api/app.py`
- Test: `tests/test_api_reads.py`

**Interfaces:**
- Produces: `create_app(cfg, *, store_opener=None, summarize_client=None, start_worker=True) -> FastAPI`.
- Read endpoints: `GET /videos`, `GET /videos/{id}`, `GET /status`, `GET /search`, `GET /recommend`. Action: `POST /feedback`.
- `app.state` holds `cfg`, `db` (shared read handle), `registry`, `worker`, `store_opener`, `summarize_client`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_reads.py
import lancedb
from pathlib import Path
from fastapi.testclient import TestClient
from tests.support import fake_embedder
from yt_summary.config import Config
from yt_summary.store import db as store
from yt_summary.store.models import Video, TranscriptRow
from yt_summary.api.app import create_app


def _cfg(tmp_path):
    return Config(downloads_dir=tmp_path / "dl", proxy_username=None, proxy_password=None,
                  cookies_browser=None, whisper_model="small", whisper_device="cpu",
                  whisper_compute_type="int8", openrouter_api_key=None,
                  store_path=tmp_path / "lance", embedding_backend="local", embedding_model=None,
                  chunk_target_s=45.0, openai_api_key=None, openrouter_model="test/model")


def _client(tmp_path):
    conn = lancedb.connect(str(tmp_path / "lance"))
    store.init_db(conn, fake_embedder())
    store.upsert_video(conn, Video(video_id="v1", url="u1", title="First", status="transcribed", published_at="2026-07-22"))
    store.insert_transcript(conn, TranscriptRow("v1", "captions", "en", "hello world", "t0"))
    app = create_app(_cfg(tmp_path), store_opener=lambda: conn, start_worker=False)
    return TestClient(app), conn


def test_list_videos(tmp_path):
    client, _ = _client(tmp_path)
    with client:
        r = client.get("/videos", params={"status": "transcribed"})
        assert r.status_code == 200
        assert [v["video_id"] for v in r.json()] == ["v1"]


def test_video_detail(tmp_path):
    client, _ = _client(tmp_path)
    with client:
        r = client.get("/videos/v1")
        assert r.status_code == 200
        body = r.json()
        assert body["title"] == "First" and body["transcript"] == "hello world"
        r404 = client.get("/videos/nope")
        assert r404.status_code == 404


def test_status_and_feedback(tmp_path):
    client, conn = _client(tmp_path)
    with client:
        assert client.get("/status").json()["counts"]["transcribed"] == 1
        r = client.post("/feedback", json={"video_id": "v1", "signal": 1})
        assert r.status_code == 204
    assert len(store.list_feedback(conn)) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_reads.py -q`
Expected: FAIL (`ModuleNotFoundError: yt_summary.api.app`)

- [ ] **Step 3: Implement `yt_summary/api/app.py`**

```python
# yt_summary/api/app.py
from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Response
from ..cli import (open_store, run_list, run_search, run_recommend, run_feedback)
from ..store import db as store
from . import schemas
from .jobs import JobRegistry, Worker


def create_app(cfg, *, store_opener=None, summarize_client=None, start_worker: bool = True) -> FastAPI:
    opener = store_opener or (lambda: open_store(cfg))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.cfg = cfg
        app.state.store_opener = opener
        app.state.summarize_client = summarize_client
        app.state.db = opener()
        app.state.registry = JobRegistry()
        app.state.worker = Worker(app.state.registry)
        if start_worker:
            app.state.worker.start()
        yield
        app.state.worker.stop()

    app = FastAPI(lifespan=lifespan)

    def _video_out(v) -> dict:
        return {"video_id": v.video_id, "title": v.title, "url": v.url,
                "status": v.status, "published_at": v.published_at, "duration_s": v.duration_s}

    @app.get("/videos", response_model=list[schemas.VideoOut])
    def list_videos(status: str | None = None, since: str | None = None):
        return [_video_out(v) for v in run_list(cfg, status=status, since=since, db=app.state.db)]

    @app.get("/videos/{video_id}", response_model=schemas.VideoDetailOut)
    def video_detail(video_id: str):
        v = store.get_video(app.state.db, video_id)
        if v is None:
            raise HTTPException(status_code=404, detail="video not found")
        out = _video_out(v)
        out["transcript"] = store.get_transcript_text(app.state.db, video_id)
        out["summary"] = store.get_summary(app.state.db, video_id)
        return out

    @app.get("/status", response_model=schemas.StatusOut)
    def status():
        return {"counts": store.count_by_status(app.state.db)}

    @app.get("/search", response_model=list[schemas.SearchHit])
    def search(q: str, mode: str = "hybrid", k: int = 10):
        return run_search(cfg, q, mode=mode, k=k, db=app.state.db)

    @app.get("/recommend", response_model=list[schemas.RecommendItem])
    def recommend(limit: int = 20):
        out = []
        for vid, score in run_recommend(cfg, limit=limit, db=app.state.db):
            v = store.get_video(app.state.db, vid)
            if v is not None:
                out.append({**_video_out(v), "score": score})
        return out

    @app.post("/feedback", status_code=204)
    def feedback(body: schemas.FeedbackIn):
        run_feedback(cfg, body.video_id, body.signal, db=app.state.db)
        return Response(status_code=204)

    # job routes are added in Task 4 via _register_jobs(app, cfg)
    from .app_jobs import register_jobs  # noqa: E402
    register_jobs(app, cfg)
    return app
```

Note: to keep Task 3 self-contained, temporarily stub the job import — create `yt_summary/api/app_jobs.py` with `def register_jobs(app, cfg): pass` now; Task 4 fills it in.

Create `yt_summary/api/app_jobs.py`:
```python
def register_jobs(app, cfg):
    pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_api_reads.py -q`
Expected: PASS. Full suite `uv run pytest -q` PASS.

- [ ] **Step 5: Commit**

```bash
git add yt_summary/api/app.py yt_summary/api/app_jobs.py tests/test_api_reads.py
git commit -m "feat: fastapi app factory + read/feedback endpoints"
```

---

## Task 4: Job endpoints

**Files:**
- Modify: `yt_summary/api/app_jobs.py` (implement `register_jobs`)
- Test: `tests/test_api_jobs.py`

**Interfaces:**
- Produces job routes on the app: `POST /jobs/fetch|discover|fetch-pending|summarize`, `GET /jobs/{id}`, `GET /jobs`. Each POST enqueues a closure that opens its own store via `app.state.store_opener` and calls the matching `run_*`/`summarize_video`; returns a `JobOut`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_jobs.py
import lancedb
from pathlib import Path
from fastapi.testclient import TestClient
from tests.support import fake_embedder
from yt_summary.config import Config
from yt_summary.store import db as store
from yt_summary.store.models import Video
from yt_summary.api import app as app_module
from yt_summary.api.app import create_app


def _cfg(tmp_path):
    return Config(downloads_dir=tmp_path / "dl", proxy_username=None, proxy_password=None,
                  cookies_browser=None, whisper_model="small", whisper_device="cpu",
                  whisper_compute_type="int8", openrouter_api_key=None,
                  store_path=tmp_path / "lance", embedding_backend="local", embedding_model=None,
                  chunk_target_s=45.0, openai_api_key=None, openrouter_model="test/model")


def _setup(tmp_path):
    conn = lancedb.connect(str(tmp_path / "lance"))
    store.init_db(conn, fake_embedder())
    app = create_app(_cfg(tmp_path), store_opener=lambda: conn, start_worker=False)
    return TestClient(app), app, conn


def test_fetch_job_enqueues_and_runs(tmp_path, monkeypatch):
    client, app, conn = _setup(tmp_path)
    # patch run_fetch used by the job closure
    monkeypatch.setattr("yt_summary.api.app_jobs.run_fetch",
                        lambda url, cfg, force=False, db=None, video_id=None: "vid123")
    with client:
        r = client.post("/jobs/fetch", json={"url": "https://y/abc"})
        assert r.status_code == 200
        jid = r.json()["id"]
        assert r.json()["status"] == "queued"
        # drain inline (worker not started)
        assert app.state.worker.run_one(block=False) is True
        got = client.get(f"/jobs/{jid}").json()
        assert got["status"] == "done"
        assert got["result"] == {"video_id": "vid123"}


def test_jobs_list_and_404(tmp_path):
    client, app, conn = _setup(tmp_path)
    with client:
        client.post("/jobs/discover", json={})
        assert len(client.get("/jobs").json()) == 1
        assert client.get("/jobs/nope").status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_jobs.py -q`
Expected: FAIL (job routes not registered → 404 on POST /jobs/fetch)

- [ ] **Step 3: Implement `yt_summary/api/app_jobs.py`**

```python
# yt_summary/api/app_jobs.py
from __future__ import annotations
from fastapi import HTTPException
from ..cli import run_fetch, run_discover, run_fetch_pending
from . import schemas
from .summarize import summarize_video


def _job_out(job) -> dict:
    return {"id": job.id, "kind": job.kind, "status": job.status, "progress": job.progress,
            "result": job.result, "error": job.error, "created_at": job.created_at}


def register_jobs(app, cfg) -> None:
    @app.post("/jobs/fetch", response_model=schemas.JobOut)
    def start_fetch(body: schemas.FetchIn):
        def fn(job):
            db = app.state.store_opener()
            vid = run_fetch(body.url, cfg, force=body.force, db=db)
            return {"video_id": vid}
        return _job_out(app.state.worker.submit("fetch", fn))

    @app.post("/jobs/discover", response_model=schemas.JobOut)
    def start_discover(body: schemas.DiscoverIn):
        def fn(job):
            db = app.state.store_opener()
            discovered, new = run_discover(cfg, after=body.after, deep=body.deep,
                                           min_duration=body.min_duration, db=db)
            return {"discovered": len(discovered), "new": new}
        return _job_out(app.state.worker.submit("discover", fn))

    @app.post("/jobs/fetch-pending", response_model=schemas.JobOut)
    def start_fetch_pending(body: schemas.FetchPendingIn):
        def fn(job):
            db = app.state.store_opener()
            results = run_fetch_pending(cfg, since=body.since, limit=body.limit, db=db)
            ok = sum(1 for _, o in results if o == "ok")
            return {"total": len(results), "ok": ok, "results": results}
        return _job_out(app.state.worker.submit("fetch-pending", fn))

    @app.post("/jobs/summarize", response_model=schemas.JobOut)
    def start_summarize(body: schemas.SummarizeIn):
        def fn(job):
            db = app.state.store_opener()
            return summarize_video(cfg, db, body.video_id, client=app.state.summarize_client)
        return _job_out(app.state.worker.submit("summarize", fn))

    @app.get("/jobs/{job_id}", response_model=schemas.JobOut)
    def get_job(job_id: str):
        job = app.state.registry.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return _job_out(job)

    @app.get("/jobs", response_model=list[schemas.JobOut])
    def list_jobs():
        return [_job_out(j) for j in app.state.registry.list()]
```

Note: `run_discover` returns `(list, int)` (SP1). Confirm the exact return shape in `cli.py` and adjust the `fn` unpacking if needed before writing the test's expectation.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_api_jobs.py -q`
Expected: PASS. Full suite `uv run pytest -q` PASS; `-W error::DeprecationWarning` clean.

- [ ] **Step 5: Commit**

```bash
git add yt_summary/api/app_jobs.py tests/test_api_jobs.py
git commit -m "feat: job endpoints (fetch/discover/fetch-pending/summarize)"
```

---

## Task 5: serve command + docs + final sweep

**Files:**
- Modify: `yt_summary/cli.py` (+ `serve`), `README.md`, `CLAUDE.md`

**Interfaces:** `serve` Typer command → `uvicorn.run(create_app(load_config()), host, port)`.

- [ ] **Step 1: Add `serve` to `yt_summary/cli.py`**

```python
@app.command()
def serve(host: str = typer.Option("127.0.0.1", "--host"), port: int = typer.Option(8000, "--port")):
    """Run the local API server (for the desktop UI)."""
    import uvicorn
    from .api.app import create_app
    uvicorn.run(create_app(load_config()), host=host, port=port)
```

- [ ] **Step 2: Smoke-test the app builds**

```bash
uv run python -c "from yt_summary.api.app import create_app; from yt_summary.config import load_config; create_app(load_config(), store_opener=lambda: None, start_worker=False); print('app builds')"
```
Expected: `app builds` (no store opened because store_opener is a stub and lifespan hasn't run). Report output.

- [ ] **Step 3: Update `README.md`**

Add a "Local API (SP4)" section: `yt-ai serve [--host --port]` starts a localhost-only FastAPI; list the endpoints (`GET /videos`, `/videos/{id}`, `/status`, `/search`, `/recommend`; `POST /feedback`; `POST /jobs/{fetch,discover,fetch-pending,summarize}` + `GET /jobs/{id}`); note it's the backend for the future desktop UI, and that summarize uses OpenRouter (`OPENROUTER_API_KEY` + `YT_OPENROUTER_MODEL`).

- [ ] **Step 4: Update `CLAUDE.md`**

Add `api/` to the module map (`app.py` factory + routes, `jobs.py` in-memory worker, `summarize.py` OpenRouter, `schemas.py`). Note the two summarization paths (skill vs API/OpenRouter) both write the `summaries` table, and that the API is localhost-only with in-memory jobs.

- [ ] **Step 5: Final sweep**

Run: `uv run pytest -q` → all PASS (+1 skipped). Report count.
Run: `uv run --with ruff ruff check .` → clean.
Run: `uv run yt-ai --help` → confirm `serve` listed.

- [ ] **Step 6: Commit**

```bash
git add yt_summary/cli.py README.md CLAUDE.md
git commit -m "feat: serve command + API docs"
```

- [ ] **Step 7: Report roadmap-memory update to the controller**

Report that the roadmap memory should mark SP4a done: local FastAPI (`yt-ai serve`) over the `run_*` cores + in-memory background jobs + OpenRouter summarizer; SP4b (React UI) consumes it.

---

## Self-Review Notes

- **Spec coverage:** read endpoints over run_* cores (T3), background jobs model + endpoints (T1 jobs.py, T4 routes), OpenRouter summarizer with highlight-snapping (T2), `serve` + docs (T5), all injectable/offline (store_opener + fake client + start_worker=False + run_one seam). Auth/persistence/SSE/cancellation intentionally out of scope.
- **Placeholder scan:** none — every code step is complete. The Task-3 `register_jobs` stub is a deliberate two-step (stub then fill in T4), each independently green.
- **Type/name consistency:** `create_app(cfg, *, store_opener, summarize_client, start_worker)` used identically in T3/T4 tests; `Worker.submit(kind, fn)`/`run_one` match test usage; `summarize_video(cfg, db, video_id, client)` matches T2 test and T4 job closure; job closures open `app.state.store_opener()` per Global Constraints. `run_discover` returns `(list, int)` — the T4 job unpacks `(discovered, new)` (verify against `cli.py` at implementation time; the plan flags this in T4 Step 3).
- **Offline discipline:** no uvicorn server, no OpenRouter call, no whisper, no model download in the unit suite — store via injected temp-dir LanceDB + fake embedder, LLM via fake client, jobs drained via `run_one`.
- **Known cross-task risk:** the read-app imports `register_jobs` from `app_jobs.py`; keep that module import-safe at Task 3 (stub) so Task 3's suite is green before Task 4.
