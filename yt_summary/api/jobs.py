from __future__ import annotations
import queue
import threading
import uuid
from dataclasses import dataclass
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
