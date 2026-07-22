import lancedb
from tests.support import fake_embedder
from yt_summary.store import db as store
from yt_summary.store.models import Video
from yt_summary import memory


def _db(tmp_path):
    conn = lancedb.connect(str(tmp_path / "lance"))
    store.init_db(conn, fake_embedder())
    return conn


def test_unseen_when_downloaded(tmp_path):
    conn = _db(tmp_path)
    store.upsert_video(conn, Video(video_id="abc", url="u", status="downloaded"))
    assert memory.is_seen(conn, "abc") is False


def test_seen_when_transcribed(tmp_path):
    conn = _db(tmp_path)
    store.upsert_video(conn, Video(video_id="abc", url="u", status="transcribed"))
    assert memory.is_seen(conn, "abc") is True


def test_unseen_when_missing(tmp_path):
    assert memory.is_seen(_db(tmp_path), "nope") is False


def test_mark_status_updates(tmp_path):
    conn = _db(tmp_path)
    store.upsert_video(conn, Video(video_id="abc", url="u", status="downloaded"))
    memory.mark_status(conn, "abc", "transcribed")
    assert store.get_video(conn, "abc").status == "transcribed"
