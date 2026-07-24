import lancedb
import pytest

from tests.support import fake_embedder
from yt_summary.store import db as store
from yt_summary.store import models
from yt_summary.store.models import Video, Segment, TranscriptRow
from yt_summary.store.embeddings import chunk_segments


def test_dataclasses_still_present():
    v = Video(video_id="abc", url="u")
    assert v.status == "discovered"
    s = Segment(video_id="abc", start_s=0.0, end_s=1.0, text="hi")
    assert s.end_s == 1.0
    t = TranscriptRow("abc", "captions", "en", "hi", "2026-07-22T00:00:00+00:00")
    assert t.source == "captions"


def test_lance_schemas_have_expected_fields():
    assert set(models.VideoSchema.model_fields) == {
        "video_id", "channel_id", "channel", "title", "url", "duration_s",
        "published_at", "description", "tags", "fetched_at", "audio_path", "status"}
    assert set(models.TranscriptSchema.model_fields) == {
        "video_id", "source", "lang", "full_text", "created_at"}
    assert set(models.StateSchema.model_fields) == {"key", "value"}


def test_ensure_columns_migrates_old_table(tmp_path):
    import lancedb
    from lancedb.pydantic import LanceModel
    from yt_summary.store.db import _ensure_columns

    class OldVideo(LanceModel):
        video_id: str
        title: str | None = None

    db = lancedb.connect(str(tmp_path / "l"))
    tbl = db.create_table("videos", schema=OldVideo)
    tbl.add([{"video_id": "x", "title": "T"}])
    _ensure_columns(tbl, models.VideoSchema)
    assert {"channel", "description", "tags"} <= set(tbl.schema.names)
    row = tbl.search().where("video_id = 'x'").limit(1).to_list()[0]
    assert row.get("description") is None  # existing row backfilled NULL


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


def test_summary_roundtrip(tmp_path):
    conn = _db(tmp_path)
    store.upsert_summary(conn, "abc", "sum", "[]", "[]", "claude-code-skill", "t0")
    s = store.get_summary(conn, "abc")
    assert s["summary_md"] == "sum" and s["model"] == "claude-code-skill"


def test_state_roundtrip(tmp_path):
    conn = _db(tmp_path)
    assert store.get_state(conn, "last_discover_at") is None
    store.set_state(conn, "last_discover_at", "2026-07-22T00:00:00+00:00")
    assert store.get_state(conn, "last_discover_at") == "2026-07-22T00:00:00+00:00"
    store.set_state(conn, "last_discover_at", "later")
    assert store.get_state(conn, "last_discover_at") == "later"


def test_count_by_status(tmp_path):
    conn = _db(tmp_path)
    store.upsert_video(conn, Video(video_id="a", url="u", status="discovered"))
    store.upsert_video(conn, Video(video_id="b", url="u", status="transcribed"))
    store.upsert_video(conn, Video(video_id="c", url="u", status="transcribed"))
    counts = store.count_by_status(conn)
    assert counts == {"discovered": 1, "transcribed": 2}


def test_feedback_insert(tmp_path):
    conn = _db(tmp_path)
    store.insert_feedback(conn, "abc", 1, "t0")
    tbl = conn.open_table("feedback")
    assert tbl.count_rows() == 1


def test_upsert_channel_roundtrip(tmp_path):
    conn = _db(tmp_path)
    store.upsert_channel(conn, "chan1", "Cool Channel", 1)
    rows = conn.open_table("channels").search().where("channel_id = 'chan1'").limit(1).to_list()
    assert rows and rows[0]["title"] == "Cool Channel" and rows[0]["subscribed"] == 1


def test_upsert_channel_none_title_does_not_clobber(tmp_path):
    conn = _db(tmp_path)
    store.upsert_channel(conn, "c", "Real Title", 1)
    store.upsert_channel(conn, "c", None, 1)  # e.g. discover() re-running with no title
    rows = conn.open_table("channels").search().where("channel_id = 'c'").limit(1).to_list()
    assert rows and rows[0]["title"] == "Real Title"


def test_insert_discovered_video_inserts_new(tmp_path):
    conn = _db(tmp_path)
    store.insert_discovered_video(conn, Video(video_id="v1", url="u", title="T",
                                              status="discovered", published_at="2026-07-20"))
    got = store.get_video(conn, "v1")
    assert got is not None and got.status == "discovered" and got.title == "T"


def test_insert_discovered_video_does_not_downgrade(tmp_path):
    conn = _db(tmp_path)
    # already fetched/transcribed
    store.upsert_video(conn, Video(video_id="v1", url="u", title="T", status="transcribed"))
    # re-discovered
    store.insert_discovered_video(conn, Video(video_id="v1", url="u", title="T",
                                              status="discovered"))
    assert store.get_video(conn, "v1").status == "transcribed"  # unchanged
    assert len(store.list_videos(conn)) == 1


def test_list_videos_by_status_filters_and_orders(tmp_path):
    conn = _db(tmp_path)
    store.upsert_video(conn, Video(video_id="a", url="u", status="discovered", published_at="2026-07-20"))
    store.upsert_video(conn, Video(video_id="b", url="u", status="discovered", published_at="2026-07-22"))
    store.upsert_video(conn, Video(video_id="c", url="u", status="transcribed", published_at="2026-07-22"))
    got = store.list_videos_by_status(conn, "discovered")
    assert [v.video_id for v in got] == ["b", "a"]  # desc by published_at, status-filtered


def test_list_videos_by_status_since_and_limit(tmp_path):
    conn = _db(tmp_path)
    store.upsert_video(conn, Video(video_id="a", url="u", status="discovered", published_at="2026-07-18"))
    store.upsert_video(conn, Video(video_id="b", url="u", status="discovered", published_at="2026-07-21"))
    store.upsert_video(conn, Video(video_id="c", url="u", status="discovered", published_at="2026-07-22"))
    since = store.list_videos_by_status(conn, "discovered", since="2026-07-20")
    assert [v.video_id for v in since] == ["c", "b"]        # a (07-18) excluded
    limited = store.list_videos_by_status(conn, "discovered", limit=1)
    assert [v.video_id for v in limited] == ["c"]           # newest only


def test_list_feedback_returns_rows(tmp_path):
    conn = _db(tmp_path)
    store.insert_feedback(conn, "v1", 1, "2026-07-23T00:00:00+00:00")
    store.insert_feedback(conn, "v1", -1, "2026-07-23T01:00:00+00:00")
    store.insert_feedback(conn, "v2", 1, "2026-07-23T00:00:00+00:00")
    rows = store.list_feedback(conn)
    assert len(rows) == 3
    assert {r["signal"] for r in rows if r["video_id"] == "v1"} == {1, -1}
