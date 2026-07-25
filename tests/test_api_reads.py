import lancedb
from fastapi.testclient import TestClient
from tests.support import fake_embedder
from yt_summary.config import Config
from yt_summary.store import db as store
from yt_summary.store.models import Video, TranscriptRow
from yt_summary.api.app import create_app


def _cfg(tmp_path):
    return Config(downloads_dir=tmp_path / "dl", proxy_username=None, proxy_password=None,
                  cookies_browser=None, whisper_model="small", whisper_device="cpu",
                  whisper_compute_type="int8", openrouter_api_key=None,
                  store_path=tmp_path / "lance", embedding_backend="local", embedding_model=None,
                  chunk_target_s=45.0, openai_api_key=None, openrouter_model="test/model")


def _client(tmp_path):
    conn = lancedb.connect(str(tmp_path / "lance"))
    store.init_db(conn, fake_embedder())
    store.upsert_video(conn, Video(video_id="v1", url="u1", title="First", status="transcribed", published_at="2026-07-22"))
    store.insert_transcript(conn, TranscriptRow("v1", "captions", "en", "hello world", "t0"))
    app = create_app(_cfg(tmp_path), store_opener=lambda: conn, start_worker=False)
    return TestClient(app), conn


def test_list_videos(tmp_path):
    client, _ = _client(tmp_path)
    with client:
        r = client.get("/videos", params={"status": "transcribed"})
        assert r.status_code == 200
        body = r.json()
        assert [v["video_id"] for v in body["items"]] == ["v1"]
        assert body["total"] == 1


def test_videos_expose_channel_tags_description(tmp_path):
    client, conn = _client(tmp_path)
    store.upsert_video(conn, Video(video_id="vm", url="um", title="Meta", status="transcribed",
                                    published_at="2026-07-24", channel_id="cid", channel="My Channel",
                                    tags="a,b,c", description="the description"))
    with client:
        item = next(v for v in client.get("/videos").json()["items"] if v["video_id"] == "vm")
        assert item["channel"] == "My Channel"
        assert item["channel_id"] == "cid"
        assert item["tags"] == "a,b,c"
        assert item["description"] == "the description"
        detail = client.get("/videos/vm").json()
        assert detail["channel"] == "My Channel" and detail["tags"] == "a,b,c"


def test_videos_paginated_envelope(tmp_path):
    client, conn = _client(tmp_path)
    store.upsert_video(conn, Video(video_id="v2", url="u2", title="Second",
                                    status="transcribed", published_at="2026-07-23"))
    store.upsert_video(conn, Video(video_id="v3", url="u3", title="Third",
                                    status="transcribed", published_at="2026-07-24"))
    with client:
        r = client.get("/videos", params={"limit": 2, "offset": 0})
        body = r.json()
        assert set(body) == {"items", "total"}
        assert len(body["items"]) == 2
        assert body["total"] >= 3
        r2 = client.get("/videos", params={"limit": 2, "offset": 2})
        assert body["items"][0]["video_id"] != r2.json()["items"][0]["video_id"]


def test_video_detail(tmp_path):
    client, _ = _client(tmp_path)
    with client:
        r = client.get("/videos/v1")
        assert r.status_code == 200
        body = r.json()
        assert body["title"] == "First" and body["transcript"] == "hello world"
        r404 = client.get("/videos/nope")
        assert r404.status_code == 404


def test_status_and_feedback(tmp_path):
    client, conn = _client(tmp_path)
    with client:
        assert client.get("/status").json()["counts"]["transcribed"] == 1
        r = client.post("/feedback", json={"video_id": "v1", "signal": 1})
        assert r.status_code == 204
    assert len(store.list_feedback(conn)) == 1


def test_search_invalid_mode_returns_422(tmp_path):
    client, _ = _client(tmp_path)
    with client:
        r = client.get("/search", params={"q": "x", "mode": "bogus"})
        assert r.status_code == 422


def test_cors_header_present(tmp_path):
    client, _ = _client(tmp_path)
    with client:
        r = client.get("/status", headers={"Origin": "http://localhost:5173"})
        assert r.status_code == 200
        assert r.headers.get("access-control-allow-origin") == "*"


def test_post_log_appends_frontend_line(tmp_path, monkeypatch):
    monkeypatch.setenv("YT_LOG_FILE", str(tmp_path / "c.jsonl"))
    client, _ = _client(tmp_path)
    with client:
        r = client.post("/log", json={"event": "ui.start", "level": "info", "msg": "hi", "ctx": {"a": 1}})
        assert r.status_code == 204
    import json
    lines = [json.loads(x) for x in (tmp_path / "c.jsonl").read_text().splitlines()]
    assert any(entry["source"] == "frontend" and entry["event"] == "ui.start" and entry["a"] == 1 for entry in lines)


def test_post_log_reserved_ctx_key_does_not_500(tmp_path, monkeypatch):
    monkeypatch.setenv("YT_LOG_FILE", str(tmp_path / "c.jsonl"))
    client, _ = _client(tmp_path)
    with client:
        r = client.post("/log", json={"event": "ui.x", "ctx": {"level": "debug", "a": 1}})
        assert r.status_code == 204
    import json
    lines = [json.loads(x) for x in (tmp_path / "c.jsonl").read_text().splitlines()]
    entry = next(e for e in lines if e["event"] == "ui.x")
    assert entry["a"] == 1
    assert entry["level"] == "info"
