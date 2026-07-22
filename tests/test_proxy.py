from yt_summary.config import Config
from pathlib import Path
from yt_summary import proxy


def _cfg(user, pw):
    return Config(db_path=Path("x"), downloads_dir=Path("d"),
                  proxy_username=user, proxy_password=pw, cookies_browser=None,
                  whisper_model="small", whisper_device="cpu",
                  whisper_compute_type="int8", openrouter_api_key=None,
                  store_path=Path("s"), embedding_backend="local", embedding_model=None,
                  chunk_target_s=45.0, openai_api_key=None)


def test_ytdlp_proxy_url_built():
    assert proxy.ytdlp_proxy_url(_cfg("u", "p")) == "http://u:p@p.webshare.io:80"


def test_ytdlp_proxy_url_none_when_missing():
    assert proxy.ytdlp_proxy_url(_cfg(None, None)) is None


def test_webshare_config_none_when_missing():
    assert proxy.webshare_config(_cfg(None, None)) is None


def test_webshare_config_built_when_present():
    cfg = proxy.webshare_config(_cfg("u", "p"))
    assert cfg is not None
