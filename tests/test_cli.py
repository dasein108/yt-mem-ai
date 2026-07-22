from yt_summary.config import Config
from yt_summary.store import db
from yt_summary.store.models import Video, Segment
from yt_summary import cli, transcript as T


def _cfg(tmp_path):
    return Config(db_path=tmp_path / "t.db", downloads_dir=tmp_path / "dl",
                  proxy_username=None, proxy_password=None, cookies_browser=None,
                  whisper_model="small", whisper_device="cpu",
                  whisper_compute_type="int8", openrouter_api_key=None,
                  store_path=tmp_path / "s", embedding_backend="local", embedding_model=None,
                  chunk_target_s=45.0, openai_api_key=None)


def test_run_fetch_stores_video_and_transcript(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    conn = db.connect(":memory:")
    db.init_db(conn)
    monkeypatch.setattr(cli, "download",
        lambda url, c: (Video(video_id="abc", url=url, status="downloaded"), "/a.mp3"))
    monkeypatch.setattr(cli, "get_transcript",
        lambda v, audio, c: T.TranscriptResult("captions", "en", "hello world",
                                               [Segment("abc", 0.0, 1.0, "hello world")]))
    vid = cli.run_fetch("https://y/abc", cfg, conn=conn)
    assert vid == "abc"
    assert db.get_video(conn, "abc").status == "transcribed"
    assert conn.execute("SELECT full_text FROM transcripts WHERE video_id='abc'").fetchone()["full_text"] == "hello world"


def test_run_fetch_skips_when_seen(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    conn = db.connect(":memory:")
    db.init_db(conn)
    db.upsert_video(conn, Video(video_id="abc", url="u"))
    db.insert_transcript(
        conn,
        __import__("yt_summary.store.models", fromlist=["TranscriptRow"]).TranscriptRow(
            "abc", "captions", "en", "x", "2026-07-21T00:00:00+00:00"
        ),
    )
    called = {"dl": False}

    def _dl(url, c):
        called["dl"] = True
        raise AssertionError("should skip")

    monkeypatch.setattr(cli, "download", _dl)
    vid = cli.run_fetch("https://y/watch?v=abc", cfg, conn=conn, video_id="abc")
    assert vid == "abc"
    assert called["dl"] is False


def test_run_fetch_skips_after_download_when_real_id_already_seen(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    conn = db.connect(":memory:")
    db.init_db(conn)
    db.upsert_video(conn, Video(video_id="realid", url="u"))
    existing_transcript = __import__(
        "yt_summary.store.models", fromlist=["TranscriptRow"]
    ).TranscriptRow("realid", "captions", "en", "existing", "2026-07-21T00:00:00+00:00")
    db.insert_transcript(conn, existing_transcript)

    monkeypatch.setattr(
        cli, "download",
        lambda url, c: (Video(video_id="realid", url=url, status="downloaded"), "/a.mp3"),
    )
    called = {"transcript": False}

    def _get_transcript(v, audio, c):
        called["transcript"] = True
        raise AssertionError("should skip transcript when already seen")

    monkeypatch.setattr(cli, "get_transcript", _get_transcript)

    # URL is unrecognizable by _extract_video_id, so the pre-download fast path is bypassed.
    vid = cli.run_fetch("https://y/embed/xyz", cfg, conn=conn)
    assert vid == "realid"
    assert called["transcript"] is False
    row = conn.execute("SELECT full_text FROM transcripts WHERE video_id='realid'").fetchone()
    assert row["full_text"] == "existing"
