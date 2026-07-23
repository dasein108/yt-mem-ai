import datetime

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


def test_save_summary(tmp_path, monkeypatch):
    from yt_summary import cli
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)
    cli.run_save_summary(cfg, "abc", "the summary", "[]", "[]", db=conn)
    s = store.get_summary(conn, "abc")
    assert s["summary_md"] == "the summary" and s["model"] == "claude-code-skill"


def test_save_summary_marks_video_summarized(tmp_path):
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)
    store.upsert_video(conn, Video(video_id="vid", url="u", status="transcribed"))
    cli.run_save_summary(cfg, "vid", "sum", "[]", "[]", db=conn)
    assert store.get_video(conn, "vid").status == "summarized"
    assert store.get_summary(conn, "vid")["summary_md"] == "sum"


def test_run_discover_writes_and_advances_state(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)
    monkeypatch.setattr(cli, "discover_videos",
        lambda cfg, after, deep=False, min_duration=120: [
            Video(video_id="v1", url="u1", channel_id="c1", title="A", status="discovered", published_at="2026-07-21"),
            Video(video_id="v2", url="u2", channel_id="c1", title="B", status="discovered", published_at="2026-07-20"),
        ])
    discovered, new = cli.run_discover(cfg, after="2026-07-01", db=conn)
    assert new == 2
    assert store.get_video(conn, "v1").status == "discovered"
    assert store.get_state(conn, "last_discover_at") is not None


def test_run_discover_reports_known_and_no_downgrade(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)
    store.upsert_video(conn, Video(video_id="v1", url="u1", status="transcribed"))
    monkeypatch.setattr(cli, "discover_videos",
        lambda cfg, after, deep=False, min_duration=120: [
            Video(video_id="v1", url="u1", channel_id="c1", status="discovered"),
            Video(video_id="v2", url="u2", channel_id="c1", status="discovered", published_at="2026-07-20"),
        ])
    discovered, new = cli.run_discover(cfg, after="2026-07-01", db=conn)
    assert new == 1                                   # only v2 is new
    assert store.get_video(conn, "v1").status == "transcribed"  # not downgraded


def test_run_discover_cutoff_precedence(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)
    store.set_state(conn, "last_discover_at", "2026-07-10")
    captured = {}
    def fake(cfg, after, deep=False, min_duration=120):
        captured["after"] = after
        return []
    monkeypatch.setattr(cli, "discover_videos", fake)
    cli.run_discover(cfg, after=None, db=conn)       # no --after → use stored state
    assert captured["after"] == "2026-07-10"


def test_run_discover_defaults_to_7_days_when_no_after_or_state(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)  # fresh store, no last_discover_at set
    captured = {}
    def fake(cfg, after, deep=False, min_duration=120):
        captured["after"] = after
        return []
    monkeypatch.setattr(cli, "discover_videos", fake)
    cli.run_discover(cfg, after=None, db=conn)
    expected = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    assert captured["after"] == expected


def test_run_list_by_status(tmp_path):
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)
    store.upsert_video(conn, Video(video_id="a", url="u", status="discovered", published_at="2026-07-20"))
    store.upsert_video(conn, Video(video_id="b", url="u", status="transcribed", published_at="2026-07-22"))
    got = cli.run_list(cfg, status="discovered", db=conn)
    assert [v.video_id for v in got] == ["a"]


def test_run_list_all_with_since(tmp_path):
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)
    store.upsert_video(conn, Video(video_id="a", url="u", status="discovered", published_at="2026-07-18"))
    store.upsert_video(conn, Video(video_id="b", url="u", status="transcribed", published_at="2026-07-22"))
    got = cli.run_list(cfg, since="2026-07-20", db=conn)
    assert [v.video_id for v in got] == ["b"]


def test_run_fetch_pending_continue_on_error(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)
    store.upsert_video(conn, Video(video_id="ok1", url="u1", status="discovered", published_at="2026-07-22"))
    store.upsert_video(conn, Video(video_id="bad", url="u2", status="discovered", published_at="2026-07-22"))
    store.upsert_video(conn, Video(video_id="ok2", url="u3", status="discovered", published_at="2026-07-22"))

    def fake_run_fetch(url, cfg, force=False, db=None, video_id=None):
        if video_id == "bad":
            raise RuntimeError("blocked")
        return video_id
    monkeypatch.setattr(cli, "run_fetch", fake_run_fetch)

    results = cli.run_fetch_pending(cfg, since="2026-07-01", db=conn)
    outcomes = dict(results)
    assert outcomes["ok1"] == "ok" and outcomes["ok2"] == "ok"
    assert outcomes["bad"].startswith("failed:")            # captured, batch continued
    assert len(results) == 3


def test_run_fetch_pending_since_and_limit(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)
    store.upsert_video(conn, Video(video_id="old", url="u", status="discovered", published_at="2026-07-01"))
    store.upsert_video(conn, Video(video_id="new1", url="u", status="discovered", published_at="2026-07-22"))
    store.upsert_video(conn, Video(video_id="new2", url="u", status="discovered", published_at="2026-07-21"))
    monkeypatch.setattr(cli, "run_fetch", lambda url, cfg, force=False, db=None, video_id=None: video_id)

    results = cli.run_fetch_pending(cfg, since="2026-07-10", limit=1, db=conn)
    assert [vid for vid, _ in results] == ["new1"]          # since excludes old, limit=1 keeps newest


def test_run_feedback_writes_signal(tmp_path):
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)
    cli.run_feedback(cfg, "v1", 1, db=conn)
    cli.run_feedback(cfg, "v1", -1, db=conn)
    rows = store.list_feedback(conn)
    assert len(rows) == 2
    assert {r["signal"] for r in rows} == {1, -1}


def test_run_recommend_returns_ranked(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)
    monkeypatch.setattr(cli, "recommend_videos",
                        lambda db, limit=20: [("v2", 0.9), ("v1", 0.1)])
    ranked = cli.run_recommend(cfg, limit=20, db=conn)
    assert ranked == [("v2", 0.9), ("v1", 0.1)]
