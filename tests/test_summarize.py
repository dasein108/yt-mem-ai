# tests/test_summarize.py
import json
import lancedb
import pytest
from pathlib import Path
from tests.support import fake_embedder
from yt_summary.config import Config
from yt_summary.store import db as store
from yt_summary.store.models import Video, TranscriptRow
from yt_summary.api import summarize


def _cfg(**over):
    base = dict(downloads_dir=Path("dl"), proxy_username=None, proxy_password=None,
                cookies_browser=None, whisper_model="small", whisper_device="cpu",
                whisper_compute_type="int8", openrouter_api_key="sk-test",
                store_path=Path("lance"), embedding_backend="local", embedding_model=None,
                chunk_target_s=45.0, openai_api_key=None, openrouter_model="test/model")
    base.update(over)
    return Config(**base)


def _db(tmp_path):
    conn = lancedb.connect(str(tmp_path / "lance"))
    store.init_db(conn, fake_embedder())
    return conn


class _FakeClient:
    """Mimics openai client: .chat.completions.create(...).choices[0].message.content"""
    def __init__(self, content: str):
        self._content = content
        self.chat = self  # so client.chat.completions works
        self.completions = self

    def create(self, **kwargs):
        msg = type("M", (), {"content": self._content})
        choice = type("C", (), {"message": msg})
        return type("R", (), {"choices": [choice]})


def _seed(conn, vid="v1"):
    store.upsert_video(conn, Video(video_id=vid, url="u", status="transcribed"))
    store.insert_transcript(conn, TranscriptRow(vid, "captions", "en", "hello world", "t0"))
    store.replace_chunks(conn, vid, [
        {"id": f"{vid}:0", "video_id": vid, "start_s": 0.0, "end_s": 10.0, "text": "hello"},
        {"id": f"{vid}:1", "video_id": vid, "start_s": 10.0, "end_s": 20.0, "text": "world"}])


def test_summarize_persists_and_snaps(tmp_path):
    conn = _db(tmp_path)
    _seed(conn)
    content = json.dumps({
        "summary_md": "A summary.",
        "highlights": [{"start_s": 11.7, "label": "the world part"}],  # 11.7 → nearest 10.0
        "qa": [{"q": "what?", "a": "world"}]})
    out = summarize.summarize_video(_cfg(), conn, "v1", client=_FakeClient(content))
    assert out["summary_md"] == "A summary."
    saved = store.get_summary(conn, "v1")
    assert saved["summary_md"] == "A summary."
    assert json.loads(saved["highlights"])[0]["start_s"] == 10.0   # snapped
    assert store.get_video(conn, "v1").status == "summarized"


def test_summarize_malformed_highlight_start_s_does_not_crash(tmp_path):
    conn = _db(tmp_path)
    _seed(conn)
    content = json.dumps({
        "summary_md": "A summary.",
        "highlights": [
            {"start_s": None, "label": "x"},
            {"start_s": 11.7, "label": "the world part"},  # 11.7 → nearest 10.0
        ],
        "qa": [{"q": "what?", "a": "world"}]})
    out = summarize.summarize_video(_cfg(), conn, "v1", client=_FakeClient(content))
    assert out["summary_md"] == "A summary."
    assert out["highlights"][0]["start_s"] is None  # untouched
    assert out["highlights"][1]["start_s"] == 10.0  # snapped
    saved = store.get_summary(conn, "v1")
    assert saved["summary_md"] == "A summary."
    saved_highlights = json.loads(saved["highlights"])
    assert saved_highlights[0]["start_s"] is None
    assert saved_highlights[1]["start_s"] == 10.0
    assert store.get_video(conn, "v1").status == "summarized"


def test_summarize_no_transcript_errors(tmp_path):
    conn = _db(tmp_path)
    store.upsert_video(conn, Video(video_id="x", url="u", status="downloaded"))
    with pytest.raises(ValueError):
        summarize.summarize_video(_cfg(), conn, "x", client=_FakeClient("{}"))


def test_summarize_missing_key_errors(tmp_path):
    conn = _db(tmp_path)
    _seed(conn)
    with pytest.raises(ValueError):
        summarize.summarize_video(_cfg(openrouter_api_key=None), conn, "v1", client=None)


def test_nearest_snaps():
    assert summarize._nearest([0.0, 10.0, 20.0], 11.7) == 10.0
    assert summarize._nearest([0.0, 10.0, 20.0], 16.0) == 20.0
    assert summarize._nearest([], 5.0) == 5.0
