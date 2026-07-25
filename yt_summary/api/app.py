# yt_summary/api/app.py
from __future__ import annotations
from contextlib import asynccontextmanager
from datetime import datetime, UTC
import threading
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from ..cli import (open_store, run_list, run_search, run_recommend, run_feedback)
from ..store import db as store
from . import schemas
from .app_jobs import build_job_fn, register_jobs
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

        def _persist(job) -> None:
            fields = {
                "kind": job.kind, "video_id": job.video_id, "status": job.status,
                "progress": job.progress, "error": job.error,
                "created_at": job.created_at,
                "updated_at": getattr(job, "updated_at", "") or datetime.now(UTC).isoformat(),
            }
            if store.get_job(app.state.db, job.id) is None:
                store.insert_job(app.state.db, {"id": job.id, **fields})
            else:
                store.update_job(app.state.db, job.id, **fields)

        app.state.worker = Worker(app.state.registry, concurrency=cfg.job_concurrency,
                                  persist=_persist)
        if start_worker:
            app.state.worker.start()

        # Recovery: re-enqueue jobs left `queued` or interrupted mid-`running`
        # by a previous process. Job fns are idempotent, so resume == re-run;
        # the original id/created_at are preserved so the persisted row is
        # updated in place rather than orphaned.
        for row in store.list_jobs(app.state.db, status="running") + \
                   store.list_jobs(app.state.db, status="queued"):
            app.state.worker.submit(
                row["kind"], build_job_fn(app, cfg, row["kind"], row.get("video_id")),
                video_id=row.get("video_id"), job_id=row["id"], created_at=row.get("created_at"),
            )

        # Auto-sync: submit a discover job on startup, then every
        # discover_interval_s (<=0 disables the timer entirely).
        app.state._sync_stop = threading.Event()

        def _sync_loop() -> None:
            interval = cfg.discover_interval_s
            if not interval or interval <= 0:
                return
            while not app.state._sync_stop.is_set():
                active = any(j.kind == "discover" and j.status in ("queued", "running")
                             for j in app.state.registry.list())
                if not active:
                    app.state.worker.submit("discover", build_job_fn(app, cfg, "discover", None))
                if app.state._sync_stop.wait(interval):
                    break

        if start_worker:
            threading.Thread(target=_sync_loop, daemon=True).start()

        from ..obs import blog
        blog("api.start", msg="server ready")
        yield
        app.state._sync_stop.set()
        app.state.worker.stop()

    app = FastAPI(lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
    )

    def _video_out(v) -> dict:
        return {"video_id": v.video_id, "title": v.title, "url": v.url,
                "status": v.status, "published_at": v.published_at, "duration_s": v.duration_s,
                "channel_id": v.channel_id, "channel": v.channel,
                "tags": v.tags, "description": v.description}

    @app.get("/videos", response_model=schemas.VideoPageOut)
    def list_videos(status: str | None = None, since: str | None = None,
                    limit: int = 30, offset: int = 0):
        vids = run_list(cfg, status=status, since=since, db=app.state.db)
        total = len(vids)
        page = vids[offset:offset + limit]
        return {"items": [_video_out(v) for v in page], "total": total}

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
        try:
            return run_search(cfg, q, mode=mode, k=k, db=app.state.db)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

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

    @app.post("/log", status_code=204)
    def post_log(body: schemas.LogIn):
        from ..obs import log_event
        safe_ctx = {k: v for k, v in (body.ctx or {}).items()
                    if k not in {"source", "event", "level", "msg", "log_file", "ts"}}
        log_event("frontend", body.event, body.level or "info", body.msg or "", **safe_ctx)
        return Response(status_code=204)

    # job routes are added in Task 4 via register_jobs(app, cfg)
    register_jobs(app, cfg)
    return app
