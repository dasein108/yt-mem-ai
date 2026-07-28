"""Offline tests for the MCP server tool/prompt adapters.

The server is a thin wrapper over cli.run_* cores, so we monkeypatch those (and
open_store) and assert each tool maps args through and returns JSON-safe output.
No network, no model downloads. Skipped entirely if the optional `mcp` extra
isn't installed.
"""
from __future__ import annotations

import json

import lancedb
import pytest

pytest.importorskip("mcp")

from tests.support import fake_embedder  # noqa: E402
from yt_mem_ai import cli, mcp_server  # noqa: E402
from yt_mem_ai.config import Config  # noqa: E402
from yt_mem_ai.store import db as store  # noqa: E402
from yt_mem_ai.store.models import Video  # noqa: E402
from yt_mem_ai.transcript import CaptionsBlocked, TranscriptUnavailable  # noqa: E402


def _cfg(tmp_path, **over):
    base = dict(
        downloads_dir=tmp_path / "dl", proxy_username=None, proxy_password=None,
        cookies_browser=None, whisper_model="small", whisper_device="cpu",
        whisper_compute_type="int8", openrouter_api_key=None,
        openrouter_model="openai/gpt-4o-mini", store_path=tmp_path / "lance",
        embedding_backend="local", embedding_model=None, chunk_target_s=45.0,
        openai_api_key=None,
    )
    base.update(over)
    return Config(**base)


@pytest.fixture()
def db(tmp_path):
    conn = lancedb.connect(str(tmp_path / "lance"))
    store.init_db(conn, fake_embedder())
    return conn


@pytest.fixture(autouse=True)
def _wire(tmp_path, db, monkeypatch):
    """Point the server at a real in-memory store + a fake config, no network."""
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(cli, "load_config", lambda *a, **k: cfg)
    monkeypatch.setattr(cli, "open_store", lambda c: db)
    return cfg


def _json_safe(obj) -> None:
    json.dumps(obj)  # raises TypeError if not serializable


def test_status_and_show_on_empty(db):
    assert mcp_server.status() == {}
    out = mcp_server.show("missing")
    assert out["error"] == "not found"
    _json_safe(out)


def test_fetch_maps_through_and_reports_ok(monkeypatch):
    called = {}

    def fake_run_fetch(url, cfg, **kw):
        called.update(url=url, kw=kw)
        return "abc"

    monkeypatch.setattr(cli, "run_fetch", fake_run_fetch)
    out = mcp_server.fetch("https://y/abc", captions_only=True)
    assert out == {"video_id": "abc", "status": "ok"}
    assert called["url"] == "https://y/abc"
    assert called["kw"]["captions_only"] is True
    assert called["kw"]["include_streams"] is True


def test_fetch_no_captions_is_structured(monkeypatch):
    def boom(*a, **k):
        raise TranscriptUnavailable("nope")

    monkeypatch.setattr(cli, "run_fetch", boom)
    out = mcp_server.fetch("https://y/x", captions_only=True)
    assert out["status"] == "no_captions"
    assert out["video_id"] is None
    _json_safe(out)


def test_fetch_captions_blocked_is_structured(monkeypatch):
    def boom(*a, **k):
        raise CaptionsBlocked("rate limited")

    monkeypatch.setattr(cli, "run_fetch", boom)
    out = mcp_server.fetch("https://y/x")
    assert out["status"] == "captions_blocked"


def test_show_returns_metadata_and_transcript(db):
    store.upsert_video(db, Video(video_id="abc", url="https://y/abc",
                                 title="Hi", status="transcribed"))
    out = mcp_server.show("abc")
    assert out["video_id"] == "abc"
    assert out["title"] == "Hi"
    assert "transcript" in out and "transcript_lang" in out and "summary" in out
    _json_safe(out)


def test_list_videos_serializes(db):
    store.upsert_video(db, Video(video_id="a", url="u1", status="transcribed"))
    store.upsert_video(db, Video(video_id="b", url="u2", status="discovered"))
    rows = mcp_server.list_videos()
    assert {r["video_id"] for r in rows} == {"a", "b"}
    _json_safe(rows)


def test_search_adds_mmss(monkeypatch):
    monkeypatch.setattr(cli, "run_search",
                        lambda cfg, q, mode="hybrid", k=10: [{"video_id": "a", "start_s": 75.0, "text": "x"}])
    hits = mcp_server.search("query")
    assert hits[0]["ts"] == "01:15"
    _json_safe(hits)


def test_save_summary_persists(db):
    store.upsert_video(db, Video(video_id="a", url="u", status="transcribed"))
    out = mcp_server.save_summary("a", "summary text", "[]", "[]")
    assert out == {"status": "saved", "video_id": "a"}
    assert store.get_summary(db, "a")["summary_md"] == "summary text"


def test_discover_shapes_output(monkeypatch):
    vids = [Video(video_id="n1", url="u1", status="discovered")]
    monkeypatch.setattr(cli, "run_discover", lambda cfg, **k: (vids, 1))
    out = mcp_server.discover()
    assert out["new_count"] == 1
    assert out["videos"][0]["video_id"] == "n1"
    _json_safe(out)


def test_fetch_pending_tallies(monkeypatch):
    monkeypatch.setattr(cli, "run_fetch_pending",
                        lambda cfg, **k: [("a", "ok"), ("b", "failed: boom")])
    out = mcp_server.fetch_pending()
    assert out["ok"] == 1 and out["failed"] == 1
    assert out["results"][1] == {"video_id": "b", "outcome": "failed: boom"}


def test_channel_list_serializes(monkeypatch):
    monkeypatch.setattr(cli, "run_channel_list",
                        lambda cfg, url, **k: [Video(video_id="c1", url="u", status="discovered")])
    rows = mcp_server.channel_list("https://youtube.com/@x")
    assert rows[0]["video_id"] == "c1"
    _json_safe(rows)


def test_like_dislike(db):
    assert mcp_server.like("a")["status"] == "liked"
    assert mcp_server.dislike("a")["status"] == "disliked"


def test_recommend_enriches(db, monkeypatch):
    store.upsert_video(db, Video(video_id="a", url="u", title="T", status="transcribed"))
    monkeypatch.setattr(cli, "run_recommend", lambda cfg, limit=20, db=None: [("a", 0.5)])
    rows = mcp_server.recommend()
    assert rows[0]["video_id"] == "a" and rows[0]["score"] == 0.5
    _json_safe(rows)


def test_reembed_reports_count(monkeypatch):
    monkeypatch.setattr(cli, "run_reembed", lambda cfg, **k: 7)
    assert mcp_server.reembed() == {"reembedded": 7}


def test_prompts_include_playbook_and_target():
    body = mcp_server.yt_summarize("https://y/abc")
    assert "https://y/abc" in body
    # The playbook text (from SKILL.md, or the inline fallback) is appended.
    assert "yt-mem-ai MCP tools" in body
    for fn in (mcp_server.yt_highlights, mcp_server.yt_qa,
               mcp_server.yt_presentation, mcp_server.yt_group):
        assert isinstance(fn("x"), str) and len(fn("x")) > 50
    assert isinstance(mcp_server.yt_digest(), str)
    assert isinstance(mcp_server.yt_review(), str)


def test_tools_are_registered():
    # FastMCP keeps the decorated function callable AND registers it.
    import asyncio
    tools = asyncio.run(mcp_server.mcp.list_tools())
    names = {t.name for t in tools}
    assert {"fetch", "show", "search", "save_summary", "discover"} <= names
