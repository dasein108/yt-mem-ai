from pathlib import Path
from yt_summary.config import Config
from yt_summary import download

def _cfg(tmp_path, use_webshare=True):
    return Config(downloads_dir=tmp_path / "dl",
                  proxy_username="u", proxy_password="p", cookies_browser="chrome",
                  whisper_model="small", whisper_device="cpu",
                  whisper_compute_type="int8", openrouter_api_key=None, openrouter_model="openai/gpt-4o-mini",
                  store_path=Path("s"), embedding_backend="local", embedding_model=None,
                  chunk_target_s=45.0, openai_api_key=None, use_webshare=use_webshare)

def test_build_opts_merges_proxy_and_cookies(tmp_path):
    opts = download.build_opts(_cfg(tmp_path), download_audio=True)
    assert opts["proxy"] == "http://u:p@p.webshare.io:80"
    assert opts["cookiesfrombrowser"] == ("chrome",)
    assert opts["format"] == "bestaudio/best"
    assert opts["remote_components"] == ["ejs:github"]  # EJS solver for audio


def test_build_opts_no_ejs_when_not_downloading_audio(tmp_path):
    opts = download.build_opts(_cfg(tmp_path), download_audio=False)
    assert "remote_components" not in opts  # metadata/discovery need no solver
    assert "format" not in opts

def test_build_opts_no_proxy_when_webshare_disabled(tmp_path):
    opts = download.build_opts(_cfg(tmp_path, use_webshare=False), download_audio=True)
    assert "proxy" not in opts
    assert opts["cookiesfrombrowser"] == ("chrome",)  # cookies still ride direct

def test_video_from_info_maps_fields():
    info = {"id": "abc", "title": "T", "duration": 120,
            "channel_id": "chan", "upload_date": "20260721",
            "webpage_url": "https://y/abc"}
    v = download.video_from_info(info, "https://y/abc")
    assert v.video_id == "abc" and v.duration_s == 120
    assert v.channel_id == "chan"
    assert v.published_at == "2026-07-21"


def test_video_from_info_captures_channel_description_tags():
    info = {"id": "abc", "title": "T", "channel": "My Channel",
            "description": "the description", "tags": ["x", "y", "z"],
            "webpage_url": "https://y/abc"}
    v = download.video_from_info(info, "https://y/abc")
    assert v.channel == "My Channel"
    assert v.description == "the description"
    assert v.tags == "x,y,z"


def test_video_from_info_tags_none_when_absent():
    v = download.video_from_info({"id": "abc", "webpage_url": "u"}, "u")
    assert v.tags is None and v.description is None

def test_download_uses_injected_factory(tmp_path):
    calls = {}
    class FakeYDL:
        def __init__(self, opts): calls["opts"] = opts
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def extract_info(self, url, download):
            calls["download"] = download
            return {"id": "abc", "title": "T", "duration": 10,
                    "webpage_url": url, "upload_date": "20260721",
                    "requested_downloads": [{"filepath": str(tmp_path / "abc.mp3")}]}
    v, audio = download.download("https://y/abc", _cfg(tmp_path), ydl_factory=FakeYDL)
    assert v.video_id == "abc"
    assert audio.endswith("abc.mp3")
    assert calls["download"] is True
