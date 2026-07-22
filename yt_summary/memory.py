# yt_summary/memory.py
from __future__ import annotations
from .store import db as store

_SEEN_STATUSES = {"transcribed", "summarized"}


def is_seen(db, video_id: str) -> bool:
    v = store.get_video(db, video_id)
    return v is not None and v.status in _SEEN_STATUSES


def mark_status(db, video_id: str, status: str) -> None:
    tbl = db.open_table("videos")
    tbl.update(where=f"video_id = '{store._safe(video_id)}'", values={"status": status})
