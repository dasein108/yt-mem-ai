# yt_summary/api/app.py
from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from ..cli import (open_store, run_list, run_search, run_recommend, run_feedback)
from ..store import db as store
from . import schemas
from .app_jobs import register_jobs
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
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
    )

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

    # job routes are added in Task 4 via register_jobs(app, cfg)
    register_jobs(app, cfg)
    return app
