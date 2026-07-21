from yt_summary.store.models import Video, Segment, TranscriptRow
from yt_summary.store import db


def test_video_dataclass_defaults():
    v = Video(video_id="abc", url="https://y/abc")
    assert v.video_id == "abc"
    assert v.status == "discovered"
    assert v.channel_id is None


def test_segment_and_transcript():
    s = Segment(video_id="abc", start_s=0.0, end_s=1.5, text="hi")
    assert s.id is None and s.end_s == 1.5
    t = TranscriptRow(
        video_id="abc",
        source="captions",
        lang="en",
        full_text="hi there",
        created_at="2026-07-21T00:00:00+00:00",
    )
    assert t.source == "captions"


def _conn():
    conn = db.connect(":memory:")
    db.init_db(conn)
    return conn


def test_upsert_and_get_video():
    conn = _conn()
    db.upsert_video(conn, Video(video_id="abc", url="u", title="T", status="downloaded"))
    got = db.get_video(conn, "abc")
    assert got is not None and got.title == "T" and got.status == "downloaded"


def test_upsert_video_is_idempotent_update():
    conn = _conn()
    db.upsert_video(conn, Video(video_id="abc", url="u", status="discovered"))
    db.upsert_video(conn, Video(video_id="abc", url="u", status="transcribed"))
    assert db.get_video(conn, "abc").status == "transcribed"
    assert len(db.list_videos(conn)) == 1


def test_transcript_and_segments_roundtrip():
    conn = _conn()
    db.upsert_video(conn, Video(video_id="abc", url="u"))
    db.insert_transcript(conn, TranscriptRow("abc", "captions", "en", "hello", "2026-07-21T00:00:00+00:00"))
    db.insert_segments(conn, [Segment("abc", 0.0, 1.0, "hello")])
    row = conn.execute("SELECT full_text FROM transcripts WHERE video_id='abc'").fetchone()
    assert row["full_text"] == "hello"
    seg = conn.execute("SELECT text FROM segments WHERE video_id='abc'").fetchone()
    assert seg["text"] == "hello"


def test_get_missing_video_returns_none():
    assert db.get_video(_conn(), "missing") is None
