from pathlib import Path
from yt_summary.config import Config
from yt_summary import cookies

def _cfg(browser):
    return Config(downloads_dir=Path("d"), proxy_username=None,
                  proxy_password=None, cookies_browser=browser, whisper_model="small",
                  whisper_device="cpu", whisper_compute_type="int8", openrouter_api_key=None, openrouter_model="openai/gpt-4o-mini",
                  store_path=Path("s"), embedding_backend="local", embedding_model=None,
                  chunk_target_s=45.0, openai_api_key=None)

def test_cookie_opts_with_browser():
    assert cookies.cookie_opts(_cfg("chrome")) == {"cookiesfrombrowser": ("chrome",)}

def test_cookie_opts_empty_when_none():
    assert cookies.cookie_opts(_cfg(None)) == {}
