import pytest
from pathlib import Path
from yt_mem_ai.config import Config
from yt_mem_ai.store.models import Video, Segment
from yt_mem_ai import transcript as T

def _cfg():
    return Config(downloads_dir=Path("d"), proxy_username=None,
                  proxy_password=None, cookies_browser=None, whisper_model="small",
                  whisper_device="cpu", whisper_compute_type="int8", openrouter_api_key=None, openrouter_model="openai/gpt-4o-mini",
                  store_path=Path("s"), embedding_backend="local", embedding_model=None,
                  chunk_target_s=45.0, openai_api_key=None)

def _res(source):
    return T.TranscriptResult(source=source, lang="en", full_text="x",
                              segments=[Segment("abc", 0.0, 1.0, "x")])

def test_uses_captions_when_available():
    v = Video(video_id="abc", url="u")
    out = T.get_transcript(v, "/a.mp3", _cfg(),
                           captions_fn=lambda vid, cfg: _res("captions"),
                           whisper_fn=lambda p, vid, cfg: pytest.fail("should not call"))
    assert out.source == "captions"

def test_falls_back_to_whisper():
    v = Video(video_id="abc", url="u")
    out = T.get_transcript(v, "/a.mp3", _cfg(),
                           captions_fn=lambda vid, cfg: None,
                           whisper_fn=lambda p, vid, cfg: _res("whisper"))
    assert out.source == "whisper"

def test_force_whisper_skips_captions():
    v = Video(video_id="abc", url="u")
    out = T.get_transcript(v, "/a.mp3", _cfg(),
                           captions_fn=lambda vid, cfg: pytest.fail("captions must be skipped"),
                           whisper_fn=lambda p, vid, cfg: _res("whisper"),
                           force_whisper=True)
    assert out.source == "whisper"


def test_raises_when_no_captions_and_no_audio():
    v = Video(video_id="abc", url="u")
    with pytest.raises(T.TranscriptUnavailable):
        T.get_transcript(v, None, _cfg(), captions_fn=lambda vid, cfg: None,
                         whisper_fn=lambda p, vid, cfg: _res("whisper"))
