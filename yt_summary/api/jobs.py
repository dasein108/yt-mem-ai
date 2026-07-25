from __future__ import annotations
import queue
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, UTC

from ..obs import blog


@dataclass
class Job:
    id: str
    kind: str
    status: str = "queued"
    progress: float | None = None
    result: dict | None = None
    error: str | None = None
    created_at: str = ""
    video_id: str | None = None
    updated_at: str = ""


class JobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, kind: str, job_id: str | None = None, created_at: str | None = None) -> Job:
        job = Job(id=job_id or uuid.uuid4().hex, kind=kind,
                  created_at=created_at or datetime.now(UTC).isoformat())
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
        try:
            self._persist(job)
        except Exception as exc:  # noqa: BLE001 - persistence must never kill the worker
            blog("job.persist_error", level="error", msg=str(exc), job_id=job.id, kind=job.kind)

    def submit(self, kind: str, fn, video_id: str | None = None,
               job_id: str | None = None, created_at: str | None = None) -> Job:
        job = self.registry.create(kind, job_id=job_id, created_at=created_at)
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

    def stop(self) -> None:
        self._running = False
        for _ in range(len(self._threads)):
            self._q.put(_STOP)
        self._threads = []
