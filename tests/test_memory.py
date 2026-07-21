from yt_summary.store import db
from yt_summary.store.models import Video, TranscriptRow
from yt_summary import memory


def _conn():
    c = db.connect(":memory:")
    db.init_db(c)
    return c


def test_unseen_when_no_transcript():
    conn = _conn()
    db.upsert_video(conn, Video(video_id="abc", url="u"))
    assert memory.is_seen(conn, "abc") is False


def test_seen_after_transcript():
    conn = _conn()
    db.upsert_video(conn, Video(video_id="abc", url="u"))
    db.insert_transcript(conn, TranscriptRow("abc", "captions", "en", "t", "2026-07-21T00:00:00+00:00"))
    assert memory.is_seen(conn, "abc") is True


def test_mark_status_updates_video():
    conn = _conn()
    db.upsert_video(conn, Video(video_id="abc", url="u"))
    memory.mark_status(conn, "abc", "downloaded")
    assert db.get_video(conn, "abc").status == "downloaded"
