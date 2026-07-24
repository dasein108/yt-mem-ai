# yt_summary/api/app_jobs.py
from __future__ import annotations
from fastapi import HTTPException
from ..cli import run_fetch, run_discover, run_fetch_pending
from ..store import db as store
from . import schemas
from .summarize import summarize_video


def _job_out(job) -> dict:
    return {"id": job.id, "kind": job.kind, "video_id": job.video_id,
            "status": job.status, "progress": job.progress, "result": job.result,
            "error": job.error, "created_at": job.created_at,
            "updated_at": getattr(job, "updated_at", "")}


def build_job_fn(app, cfg, kind: str, video_id: str | None):
    """Rebuild a job's work function from its persisted kind/video_id.

    Used by startup recovery to re-enqueue jobs that were left `queued` or
    `running` in the durable `jobs` table when the process last exited.
    """
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


def register_jobs(app, cfg) -> None:
    @app.post("/jobs/fetch", response_model=schemas.JobOut)
    def start_fetch(body: schemas.FetchIn):
        def fn(job):
            db = app.state.store_opener()
            vid = run_fetch(body.url, cfg, force=body.force, db=db)
            return {"video_id": vid}
        return _job_out(app.state.worker.submit("fetch", fn, video_id=body.url))

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
        return _job_out(app.state.worker.submit("summarize", fn, video_id=body.video_id))

    @app.get("/jobs/{job_id}", response_model=schemas.JobOut)
    def get_job(job_id: str):
        job = app.state.registry.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return _job_out(job)

    @app.get("/jobs", response_model=list[schemas.JobOut])
    def list_jobs(status: str | None = None, video_id: str | None = None):
        if status in ("done", "error"):
            jobs = store.list_jobs(app.state.db, status=status)
        else:
            jobs = [_job_out(j) for j in app.state.registry.list()]
            if status is not None:
                jobs = [j for j in jobs if j["status"] == status]
        if video_id is not None:
            jobs = [j for j in jobs if j.get("video_id") == video_id]
        return jobs
