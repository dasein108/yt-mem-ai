# yt_summary/store/db.py
from __future__ import annotations
import lancedb
from pathlib import Path
from .models import (
    Video, VideoSchema, ChannelSchema, TranscriptSchema,
    SummarySchema, FeedbackSchema, StateSchema, chunk_schema,
)

_VIDEO_FIELDS = list(VideoSchema.model_fields)


def connect(store_path: str | Path) -> lancedb.DBConnection:
    return lancedb.connect(str(store_path))


def init_db(db: lancedb.DBConnection, embedder) -> None:
    db.create_table("videos", schema=VideoSchema, exist_ok=True)
    db.create_table("channels", schema=ChannelSchema, exist_ok=True)
    db.create_table("transcripts", schema=TranscriptSchema, exist_ok=True)
    db.create_table("summaries", schema=SummarySchema, exist_ok=True)
    db.create_table("feedback", schema=FeedbackSchema, exist_ok=True)
    db.create_table("app_state", schema=StateSchema, exist_ok=True)
    db.create_table("chunks", schema=chunk_schema(embedder), exist_ok=True)


def _video_to_row(v: Video) -> dict:
    return {k: getattr(v, k) for k in _VIDEO_FIELDS}


def _row_to_video(d: dict) -> Video:
    return Video(**{k: d.get(k) for k in _VIDEO_FIELDS})


def upsert_video(db: lancedb.DBConnection, v: Video) -> None:
    tbl = db.open_table("videos")
    tbl.merge_insert("video_id") \
        .when_matched_update_all() \
        .when_not_matched_insert_all() \
        .execute([_video_to_row(v)])


def get_video(db: lancedb.DBConnection, video_id: str) -> Video | None:
    tbl = db.open_table("videos")
    rows = tbl.search().where(f"video_id = '{video_id}'").limit(1).to_list()
    return _row_to_video(rows[0]) if rows else None


def list_videos(db: lancedb.DBConnection) -> list[Video]:
    tbl = db.open_table("videos")
    rows = tbl.search().limit(100000).to_list()
    rows.sort(key=lambda d: (d.get("published_at") or ""), reverse=True)
    return [_row_to_video(d) for d in rows]
