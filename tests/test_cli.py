import lancedb
from tests.support import fake_embedder
from yt_summary.config import Config
from yt_summary.store import db as store
from yt_summary.store.models import Video, Segment
from yt_summary import cli, transcript as T


def _cfg(tmp_path, **over):
    base = dict(downloads_dir=tmp_path / "dl", proxy_username=None,
                proxy_password=None, cookies_browser=None, whisper_model="small",
                whisper_device="cpu", whisper_compute_type="int8", openrouter_api_key=None,
                store_path=tmp_path / "lance", embedding_backend="local", embedding_model=None,
                chunk_target_s=45.0, openai_api_key=None)
    base.update(over)
    return Config(**base)


def _db(tmp_path):
    conn = lancedb.connect(str(tmp_path / "lance"))
    store.init_db(conn, fake_embedder())
    return conn


def test_run_fetch_stores_video_transcript_chunks(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)
    monkeypatch.setattr(cli, "download",
        lambda url, c: (Video(video_id="abc", url=url, status="downloaded"), "/a.mp3"))
    monkeypatch.setattr(cli, "get_transcript",
        lambda v, audio, c: T.TranscriptResult("captions", "en", "hello world",
            [Segment("abc", 0.0, 10.0, "hello"), Segment("abc", 10.0, 20.0, "world")]))
    vid = cli.run_fetch("https://y/abc", cfg, db=conn)
    assert vid == "abc"
    assert store.get_video(conn, "abc").status == "transcribed"
    assert store.get_transcript_text(conn, "abc") == "hello world"
    assert len(store.list_chunks(conn, "abc")) >= 1


def test_run_fetch_skips_when_seen(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)
    store.upsert_video(conn, Video(video_id="abc", url="u", status="transcribed"))
    def _boom(url, c):
        raise AssertionError("should skip")
    monkeypatch.setattr(cli, "download", _boom)
    vid = cli.run_fetch("https://y/watch?v=abc", cfg, db=conn, video_id="abc")
    assert vid == "abc"


def test_run_fetch_skips_after_download_when_real_id_seen(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)
    # real id already fully processed
    store.upsert_video(conn, Video(video_id="abc", url="u", status="transcribed"))
    # URL is unparseable by _extract_video_id (no v=/youtu.be/shorts marker),
    # so the pre-download check can't catch it; download reveals the real id "abc".
    monkeypatch.setattr(cli, "download",
        lambda url, c: (Video(video_id="abc", url=url, status="downloaded"), "/a.mp3"))
    def _boom(*a, **k):
        raise AssertionError("get_transcript must NOT run when real id already seen")
    monkeypatch.setattr(cli, "get_transcript", _boom)
    vid = cli.run_fetch("https://example.com/embed/xyz", cfg, db=conn)
    assert vid == "abc"
