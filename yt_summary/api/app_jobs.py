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
