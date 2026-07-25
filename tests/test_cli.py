import datetime

import lancedb
from tests.support import fake_embedder
from yt_mem_ai.config import Config
from yt_mem_ai.store import db as store
from yt_mem_ai.store.models import Video, Segment
from yt_mem_ai import cli, transcript as T


def _cfg(tmp_path, **over):
    base = dict(downloads_dir=tmp_path / "dl", proxy_username=None,
                proxy_password=None, cookies_browser=None, whisper_model="small",
                whisper_device="cpu", whisper_compute_type="int8", openrouter_api_key=None, openrouter_model="openai/gpt-4o-mini",
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
        lambda v, audio, c, force_whisper=False: T.TranscriptResult("captions", "en", "hello world",
            [Segment("abc", 0.0, 10.0, "hello"), Segment("abc", 10.0, 20.0, "world")]))
    vid = cli.run_fetch("https://y/abc", cfg, db=conn)
    assert vid == "abc"
    assert store.get_video(conn, "abc").status == "transcribed"
    assert store.get_transcript_text(conn, "abc") == "hello world"
    assert len(store.list_chunks(conn, "abc")) >= 1


def test_run_fetch_captions_only_skips_audio_download(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)

    def _no_audio_download(*a, **k):
        raise AssertionError("captions_only must NOT download audio")
    monkeypatch.setattr(cli, "download", _no_audio_download)
    monkeypatch.setattr(cli, "download_metadata",
        lambda url, c: Video(video_id="cap", url=url, status="downloaded"))
    monkeypatch.setattr(cli, "get_transcript",
        lambda v, audio, c, force_whisper=False: T.TranscriptResult("captions", "en", "hi there",
            [Segment("cap", 0.0, 5.0, "hi"), Segment("cap", 5.0, 10.0, "there")]))
    vid = cli.run_fetch("https://y/cap", cfg, db=conn, captions_only=True)
    assert vid == "cap"
    assert store.get_video(conn, "cap").status == "transcribed"
    assert store.get_transcript_text(conn, "cap") == "hi there"


def test_run_fetch_captions_only_raises_when_no_captions(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)
    monkeypatch.setattr(cli, "download_metadata",
        lambda url, c: Video(video_id="cap", url=url, status="downloaded"))

    def _unavailable(v, audio, c, force_whisper=False):
        raise T.TranscriptUnavailable("no captions and no audio")
    monkeypatch.setattr(cli, "get_transcript", _unavailable)
    import pytest
    with pytest.raises(T.TranscriptUnavailable):
        cli.run_fetch("https://y/cap", cfg, db=conn, captions_only=True)


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


def test_show_json_includes_summary(tmp_path, monkeypatch, capsys):
    import json as _json
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)
    store.upsert_video(conn, Video(video_id="s1", url="u", status="summarized"))
    cli.run_save_summary(cfg, "s1", "sum md", '[{"start_s":1,"label":"x"}]',
                         '[{"q":"a","a":"b"}]', db=conn)
    monkeypatch.setattr(cli, "load_config", lambda: cfg)
    monkeypatch.setattr(cli, "open_store", lambda c: conn)
    cli.show("s1", as_json=True)
    out = _json.loads(capsys.readouterr().out)
    assert out["summary"]["summary_md"] == "sum md"
    assert _json.loads(out["summary"]["highlights"])[0]["label"] == "x"


def test_save_summary(tmp_path, monkeypatch):
    from yt_mem_ai import cli
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
        lambda cfg, after=None, deep=False, min_duration=120, after_ts=None, overlap_s=0.0: [
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
        lambda cfg, after=None, deep=False, min_duration=120, after_ts=None, overlap_s=0.0: [
            Video(video_id="v1", url="u1", channel_id="c1", status="discovered"),
            Video(video_id="v2", url="u2", channel_id="c1", status="discovered", published_at="2026-07-20"),
        ])
    discovered, new = cli.run_discover(cfg, after="2026-07-01", db=conn)
    assert new == 1                                   # only v2 is new
    assert [v.video_id for v in discovered] == ["v2"]  # v1 already processed → filtered out
    assert store.get_video(conn, "v1").status == "transcribed"  # not downgraded


def test_run_discover_cutoff_precedence(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)
    store.set_state(conn, "last_discover_at", "2026-07-10")
    captured = {}
    def fake(cfg, after=None, deep=False, min_duration=120, after_ts=None, overlap_s=0.0):
        captured["after"], captured["after_ts"] = after, after_ts
        return []
    monkeypatch.setattr(cli, "discover_videos", fake)
    cli.run_discover(cfg, after=None, db=conn)       # no --after, no ts → legacy date state
    assert captured["after"] == "2026-07-10"
    assert captured["after_ts"] is None


def test_run_discover_uses_stored_epoch_high_water(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)
    store.set_state(conn, "last_discover_ts", "1784592000.0")  # takes precedence over date
    store.set_state(conn, "last_discover_at", "2026-07-10")
    captured = {}
    def fake(cfg, after=None, deep=False, min_duration=120, after_ts=None, overlap_s=0.0):
        captured["after"], captured["after_ts"], captured["overlap"] = after, after_ts, overlap_s
        return []
    monkeypatch.setattr(cli, "discover_videos", fake)
    cli.run_discover(cfg, after=None, db=conn)
    assert captured["after"] is None
    assert captured["after_ts"] == 1784592000.0      # epoch high-water wins
    assert captured["overlap"] == cfg.discover_overlap_s


def test_run_discover_advances_epoch_high_water(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)
    store.set_state(conn, "last_discover_ts", "1000.0")
    monkeypatch.setattr(cli, "discover_videos",
        lambda cfg, after=None, deep=False, min_duration=120, after_ts=None, overlap_s=0.0: [
            Video(video_id="v1", url="u1", channel_id="c1", status="discovered",
                  published_at="2026-07-21", published_ts=1784592000.0),
        ])
    cli.run_discover(cfg, after=None, db=conn)
    assert store.get_state(conn, "last_discover_ts") == repr(1784592000.0)  # advanced


def test_run_discover_defaults_to_7_days_when_no_after_or_state(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)  # fresh store, no last_discover_at set
    captured = {}
    def fake(cfg, after=None, deep=False, min_duration=120, after_ts=None, overlap_s=0.0):
        captured["after"] = after
        return []
    monkeypatch.setattr(cli, "discover_videos", fake)
    cli.run_discover(cfg, after=None, db=conn)
    expected = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    assert captured["after"] == expected


def test_run_list_limit_and_channel(tmp_path):
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)
    store.upsert_video(conn, Video(video_id="a", url="ua", channel_id="c1", published_at="2026-07-23", status="discovered"))
    store.upsert_video(conn, Video(video_id="b", url="ub", channel_id="c2", published_at="2026-07-22", status="discovered"))
    store.upsert_video(conn, Video(video_id="c", url="uc", channel_id="c1", published_at="2026-07-21", status="discovered"))
    assert {v.video_id for v in cli.run_list(cfg, channel="c1", db=conn)} == {"a", "c"}
    assert [v.video_id for v in cli.run_list(cfg, limit=2, db=conn)] == ["a", "b"]  # newest-first


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


def test_run_compile_returns_clips(tmp_path):
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)
    store.upsert_video(conn, Video(video_id="v", url="u", title="V", status="summarized", published_at="2026-07-22"))
    store.replace_chunks(conn, "v", [{"id": "v:0", "video_id": "v", "start_s": 0.0, "end_s": 30.0, "text": "c"}])
    store.upsert_summary(conn, "v", "s", '[{"start_s": 0, "label": "hi"}]', "[]", "m", "t0")
    clips = cli.run_compile(cfg, since="2026-07-01", db=conn)
    assert clips and clips[0].link.endswith("watch?v=v&t=0s")


def test_run_fetch_emits_workflow_events(tmp_path, monkeypatch):
    import json
    monkeypatch.setenv("YT_LOG_FILE", str(tmp_path / "c.jsonl"))
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)
    monkeypatch.setattr(cli, "download",
        lambda url, c: (Video(video_id="abc", url=url, status="downloaded"), "/a.mp3"))
    monkeypatch.setattr(cli, "get_transcript",
        lambda v, audio, c, force_whisper=False: T.TranscriptResult("captions", "en", "hello", [Segment("abc", 0.0, 1.0, "hello")]))
    cli.run_fetch("https://y/abc", cfg, db=conn)
    events = {json.loads(x)["event"] for x in (tmp_path / "c.jsonl").read_text().splitlines()}
    assert "fetch.done" in events
