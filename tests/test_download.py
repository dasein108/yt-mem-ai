from yt_summary.config import Config
from yt_summary import download

def _cfg(tmp_path):
    return Config(db_path=tmp_path / "x.db", downloads_dir=tmp_path / "dl",
                  proxy_username="u", proxy_password="p", cookies_browser="chrome",
                  whisper_model="small", whisper_device="cpu",
                  whisper_compute_type="int8", openrouter_api_key=None)

def test_build_opts_merges_proxy_and_cookies(tmp_path):
    opts = download.build_opts(_cfg(tmp_path), download_audio=True)
    assert opts["proxy"] == "http://u:p@p.webshare.io:80"
    assert opts["cookiesfrombrowser"] == ("chrome",)
    assert opts["format"] == "bestaudio/best"

def test_video_from_info_maps_fields():
    info = {"id": "abc", "title": "T", "duration": 120,
            "channel_id": "chan", "upload_date": "20260721",
            "webpage_url": "https://y/abc"}
    v = download.video_from_info(info, "https://y/abc")
    assert v.video_id == "abc" and v.duration_s == 120
    assert v.channel_id == "chan"
    assert v.published_at == "2026-07-21"

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
