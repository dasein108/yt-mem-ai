# yt_summary/store/db.py
from __future__ import annotations
import logging
import re
import warnings
import lancedb
from pathlib import Path
from .models import (
    Video, VideoSchema, ChannelSchema, TranscriptSchema,
    SummarySchema, FeedbackSchema, StateSchema, chunk_schema,
)

_log = logging.getLogger(__name__)

_VIDEO_FIELDS = list(VideoSchema.model_fields)

_SAFE_ID = re.compile(r"^[A-Za-z0-9_:-]+$")


def _safe(value: str) -> str:
    """Guard an identifier before interpolating it into a LanceDB filter string."""
    if not isinstance(value, str) or not _SAFE_ID.match(value):
        raise ValueError(f"unsafe filter identifier: {value!r}")
    return value


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
    rows = tbl.search().where(f"video_id = '{_safe(video_id)}'").limit(1).to_list()
    return _row_to_video(rows[0]) if rows else None


def list_videos(db: lancedb.DBConnection) -> list[Video]:
    tbl = db.open_table("videos")
    rows = tbl.search().limit(100000).to_list()
    rows.sort(key=lambda d: (d.get("published_at") or ""), reverse=True)
    return [_row_to_video(d) for d in rows]


def _ensure_fts(tbl, column: str) -> None:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            tbl.create_fts_index(column, replace=True)
    except Exception as exc:
        # FTS index creation can legitimately fail on an empty table; log so a
        # real failure (which Task 7 search depends on) is discoverable.
        _log.debug("FTS index on %r skipped: %s", column, exc)


def insert_transcript(db: lancedb.DBConnection, t) -> None:
    tbl = db.open_table("transcripts")
    row = {"video_id": t.video_id, "source": t.source, "lang": t.lang,
           "full_text": t.full_text, "created_at": t.created_at}
    tbl.merge_insert("video_id") \
        .when_matched_update_all() \
        .when_not_matched_insert_all() \
        .execute([row])
    _ensure_fts(tbl, "full_text")


def get_transcript_text(db: lancedb.DBConnection, video_id: str) -> str | None:
    tbl = db.open_table("transcripts")
    rows = tbl.search().where(f"video_id = '{_safe(video_id)}'").limit(1).to_list()
    return rows[0]["full_text"] if rows else None


def replace_chunks(db: lancedb.DBConnection, video_id: str, chunk_rows: list[dict]) -> None:
    tbl = db.open_table("chunks")
    tbl.delete(f"video_id = '{_safe(video_id)}'")
    if chunk_rows:
        tbl.add(chunk_rows)
        _ensure_fts(tbl, "text")


def list_chunks(db: lancedb.DBConnection, video_id: str) -> list[dict]:
    tbl = db.open_table("chunks")
    rows = tbl.search().where(f"video_id = '{_safe(video_id)}'").limit(100000).to_list()
    rows.sort(key=lambda d: d.get("start_s", 0.0))
    return rows
