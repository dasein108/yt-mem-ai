# yt_mem_ai/store/db.py
from __future__ import annotations
import logging
import re
import warnings
from collections import Counter
import lancedb
from pathlib import Path
from .models import (
    Video, VideoSchema, ChannelSchema, TranscriptSchema,
    SummarySchema, FeedbackSchema, StateSchema, JobSchema, chunk_schema,
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


def _ensure_columns(tbl, schema) -> None:
    """Add any schema columns missing from an existing table (nullable strings).
    Idempotent — new string fields added to VideoSchema land on older stores
    without a manual migration; existing rows get NULL."""
    have = set(tbl.schema.names)
    missing = [name for name in schema.model_fields if name not in have]
    if missing:
        tbl.add_columns({name: "CAST(NULL AS STRING)" for name in missing})


def init_db(db: lancedb.DBConnection, embedder) -> None:
    # create_table(exist_ok=True) rejects a *changed* schema, so for videos we
    # create only when absent, then evolve columns on the existing table.
    if "videos" not in db.table_names():
        db.create_table("videos", schema=VideoSchema)
    _ensure_columns(db.open_table("videos"), VideoSchema)
    db.create_table("channels", schema=ChannelSchema, exist_ok=True)
    db.create_table("transcripts", schema=TranscriptSchema, exist_ok=True)
    db.create_table("summaries", schema=SummarySchema, exist_ok=True)
    db.create_table("feedback", schema=FeedbackSchema, exist_ok=True)
    db.create_table("app_state", schema=StateSchema, exist_ok=True)
    db.create_table("chunks", schema=chunk_schema(embedder), exist_ok=True)
    db.create_table("jobs", schema=JobSchema, exist_ok=True)


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


def get_transcript_lang(db: lancedb.DBConnection, video_id: str) -> str | None:
    tbl = db.open_table("transcripts")
    rows = tbl.search().where(f"video_id = '{_safe(video_id)}'").limit(1).to_list()
    return rows[0]["lang"] if rows else None


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


_CHUNK_FIELDS = ("id", "video_id", "start_s", "end_s", "text")


def all_chunks(db: lancedb.DBConnection) -> list[dict]:
    """Every chunk row as {id, video_id, start_s, end_s, text} (vector stripped)."""
    tbl = db.open_table("chunks")
    rows = tbl.search().limit(100_000_000).to_list()
    return [{k: r[k] for k in _CHUNK_FIELDS} for r in rows]


def rebuild_chunks(db: lancedb.DBConnection, embedder, rows: list[dict]) -> None:
    """Drop + recreate the chunks table with `embedder` and re-insert `rows`
    (text is the embedder's SourceField → auto re-embedded). Rebuilds FTS."""
    if "chunks" in db.table_names():
        db.drop_table("chunks")
    tbl = db.create_table("chunks", schema=chunk_schema(embedder))
    if rows:
        clean = [{k: r[k] for k in _CHUNK_FIELDS} for r in rows]
        tbl.add(clean)
        _ensure_fts(tbl, "text")


def upsert_summary(db, video_id, summary_md, highlights, qa, model, created_at) -> None:
    tbl = db.open_table("summaries")
    row = {"video_id": video_id, "summary_md": summary_md, "highlights": highlights,
           "qa": qa, "model": model, "created_at": created_at}
    tbl.merge_insert("video_id") \
        .when_matched_update_all() \
        .when_not_matched_insert_all() \
        .execute([row])


def get_summary(db, video_id: str) -> dict | None:
    tbl = db.open_table("summaries")
    rows = tbl.search().where(f"video_id = '{_safe(video_id)}'").limit(1).to_list()
    return rows[0] if rows else None


def insert_feedback(db, video_id: str, signal: int, created_at: str) -> None:
    tbl = db.open_table("feedback")
    tbl.add([{"video_id": video_id, "signal": signal, "created_at": created_at}])


def get_state(db, key: str) -> str | None:
    tbl = db.open_table("app_state")
    rows = tbl.search().where(f"key = '{_safe(key)}'").limit(1).to_list()
    return rows[0]["value"] if rows else None


def set_state(db, key: str, value: str) -> None:
    tbl = db.open_table("app_state")
    tbl.merge_insert("key") \
        .when_matched_update_all() \
        .when_not_matched_insert_all() \
        .execute([{"key": key, "value": value}])


def count_by_status(db) -> dict[str, int]:
    tbl = db.open_table("videos")
    rows = tbl.search().limit(100000).to_list()
    return dict(Counter((r.get("status") or "(none)") for r in rows))


def search_chunks(db, query: str, k: int = 10, mode: str = "hybrid") -> list[dict]:
    tbl = db.open_table("chunks")
    if mode == "fts":
        res = tbl.search(query, query_type="fts").limit(k)
    elif mode == "vector":
        res = tbl.search(query, query_type="vector").limit(k)
    elif mode == "hybrid":
        from lancedb.rerankers import RRFReranker
        res = tbl.search(query, query_type="hybrid").rerank(reranker=RRFReranker()).limit(k)
    else:
        raise ValueError(f"unknown search mode: {mode!r}")
    hits = res.to_list()
    for h in hits:
        h.pop("vector", None)
        h.pop("_relevance_score", None)
        h.pop("_distance", None)
        h.pop("_score", None)
    return hits


def upsert_channel(db, channel_id: str, title: str | None = None, subscribed: int = 1) -> None:
    tbl = db.open_table("channels")
    row = {"channel_id": channel_id, "title": title, "subscribed": subscribed}
    merge = tbl.merge_insert("channel_id")
    if title is not None:
        merge = merge.when_matched_update_all()
    merge.when_not_matched_insert_all().execute([row])


def insert_discovered_video(db, v: Video) -> None:
    tbl = db.open_table("videos")
    tbl.merge_insert("video_id") \
        .when_not_matched_insert_all() \
        .execute([_video_to_row(v)])


def list_videos_by_status(db, status: str, since: str | None = None,
                          limit: int | None = None) -> list[Video]:
    tbl = db.open_table("videos")
    rows = tbl.search().where(f"status = '{_safe(status)}'").limit(1_000_000).to_list()
    if since is not None:
        rows = [r for r in rows if (r.get("published_at") or "") >= since]
    rows.sort(key=lambda d: (d.get("published_at") or ""), reverse=True)
    if limit is not None:
        rows = rows[:limit]
    return [_row_to_video(d) for d in rows]


def list_feedback(db) -> list[dict]:
    tbl = db.open_table("feedback")
    return tbl.search().limit(1_000_000).to_list()


_JOB_FIELDS = list(JobSchema.model_fields)


def insert_job(db, row: dict) -> None:
    tbl = db.open_table("jobs")
    tbl.merge_insert("id").when_matched_update_all().when_not_matched_insert_all() \
        .execute([{k: row.get(k) for k in _JOB_FIELDS}])


def update_job(db, job_id: str, **fields) -> None:
    existing = get_job(db, job_id)
    if existing is None:
        return
    existing.update(fields)
    insert_job(db, existing)


def get_job(db, job_id: str) -> dict | None:
    tbl = db.open_table("jobs")
    rows = tbl.search().where(f"id = '{_safe(job_id)}'").limit(1).to_list()
    return {k: rows[0].get(k) for k in _JOB_FIELDS} if rows else None


def list_jobs(db, status: str | None = None, limit: int | None = None) -> list[dict]:
    tbl = db.open_table("jobs")
    q = tbl.search()
    if status is not None:
        q = q.where(f"status = '{_safe(status)}'")
    rows = q.limit(1_000_000).to_list()
    rows.sort(key=lambda d: (d.get("created_at") or ""), reverse=True)
    if limit is not None:
        rows = rows[:limit]
    return [{k: r.get(k) for k in _JOB_FIELDS} for r in rows]
