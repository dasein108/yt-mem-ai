import lancedb
import pytest

from tests.support import fake_embedder
from yt_summary.store import db as store
from yt_summary.store import models
from yt_summary.store.models import Video, Segment, TranscriptRow


def test_dataclasses_still_present():
    v = Video(video_id="abc", url="u")
    assert v.status == "discovered"
    s = Segment(video_id="abc", start_s=0.0, end_s=1.0, text="hi")
    assert s.end_s == 1.0
    t = TranscriptRow("abc", "captions", "en", "hi", "2026-07-22T00:00:00+00:00")
    assert t.source == "captions"


def test_lance_schemas_have_expected_fields():
    assert set(models.VideoSchema.model_fields) == {
        "video_id", "channel_id", "title", "url", "duration_s",
        "published_at", "fetched_at", "audio_path", "status"}
    assert set(models.TranscriptSchema.model_fields) == {
        "video_id", "source", "lang", "full_text", "created_at"}
    assert set(models.StateSchema.model_fields) == {"key", "value"}


def test_chunk_schema_carries_vector():
    Chunk = models.chunk_schema(fake_embedder())
    fields = set(Chunk.model_fields)
    assert {"id", "video_id", "start_s", "end_s", "text", "vector"} <= fields


def _db(tmp_path):
    conn = lancedb.connect(str(tmp_path / "lance"))
    store.init_db(conn, fake_embedder())
    return conn


def test_init_db_creates_all_tables(tmp_path):
    conn = _db(tmp_path)
    names = set(conn.list_tables().tables)
    assert {"videos", "channels", "transcripts", "chunks",
            "summaries", "feedback", "app_state"} <= names


def test_upsert_and_get_video(tmp_path):
    conn = _db(tmp_path)
    store.upsert_video(conn, Video(video_id="abc", url="u", title="T", status="downloaded"))
    got = store.get_video(conn, "abc")
    assert got is not None and got.title == "T" and got.status == "downloaded"


def test_upsert_video_updates_in_place(tmp_path):
    conn = _db(tmp_path)
    store.upsert_video(conn, Video(video_id="abc", url="u", status="discovered"))
    store.upsert_video(conn, Video(video_id="abc", url="u", status="transcribed"))
    assert store.get_video(conn, "abc").status == "transcribed"
    assert len(store.list_videos(conn)) == 1


def test_get_missing_video_none(tmp_path):
    assert store.get_video(_db(tmp_path), "missing") is None


def test_get_video_rejects_unsafe_id(tmp_path):
    conn = _db(tmp_path)
    with pytest.raises(ValueError):
        store.get_video(conn, "x' OR '1'='1")


from yt_summary.store.models import TranscriptRow
from yt_summary.store.embeddings import chunk_segments
from yt_summary.store.models import Segment


def test_transcript_roundtrip(tmp_path):
    conn = _db(tmp_path)
    store.insert_transcript(conn, TranscriptRow("abc", "captions", "en", "hello world", "2026-07-22T00:00:00+00:00"))
    assert store.get_transcript_text(conn, "abc") == "hello world"


def test_transcript_merge_updates(tmp_path):
    conn = _db(tmp_path)
    store.insert_transcript(conn, TranscriptRow("abc", "captions", "en", "first", "t0"))
    store.insert_transcript(conn, TranscriptRow("abc", "whisper", "en", "second", "t1"))
    assert store.get_transcript_text(conn, "abc") == "second"


def test_replace_chunks_idempotent(tmp_path):
    conn = _db(tmp_path)
    segs = [Segment("abc", 0.0, 10.0, "alpha"), Segment("abc", 10.0, 20.0, "beta")]
    rows = chunk_segments("abc", segs, target_s=5.0)
    store.replace_chunks(conn, "abc", rows)
    store.replace_chunks(conn, "abc", rows)  # second pass must not duplicate
    got = store.list_chunks(conn, "abc")
    assert len(got) == len(rows)
    assert got[0]["start_s"] == 0.0
