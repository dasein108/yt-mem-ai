from yt_mem_ai.config import Config
from pathlib import Path
from yt_mem_ai import proxy


def _cfg(user, pw, use_webshare=True):
    return Config(downloads_dir=Path("d"),
                  proxy_username=user, proxy_password=pw, cookies_browser=None,
                  whisper_model="small", whisper_device="cpu",
                  whisper_compute_type="int8", openrouter_api_key=None, openrouter_model="openai/gpt-4o-mini",
                  store_path=Path("s"), embedding_backend="local", embedding_model=None,
                  chunk_target_s=45.0, openai_api_key=None, use_webshare=use_webshare)


def test_ytdlp_proxy_url_built():
    assert proxy.ytdlp_proxy_url(_cfg("u", "p")) == "http://u:p@p.webshare.io:80"


def test_ytdlp_proxy_url_none_when_missing():
    assert proxy.ytdlp_proxy_url(_cfg(None, None)) is None


def test_ytdlp_proxy_url_none_when_webshare_disabled():
    # creds present but the toggle is off (default) → no proxy, ride VLESS direct.
    assert proxy.ytdlp_proxy_url(_cfg("u", "p", use_webshare=False)) is None


def test_webshare_config_none_when_missing():
    assert proxy.webshare_config(_cfg(None, None)) is None


def test_webshare_config_built_when_present():
    cfg = proxy.webshare_config(_cfg("u", "p"))
    assert cfg is not None


def test_webshare_config_none_when_disabled():
    assert proxy.webshare_config(_cfg("u", "p", use_webshare=False)) is None


def test_captions_proxy_decoupled_from_ytdlp():
    from dataclasses import replace
    # captions_use_webshare on, use_webshare off → transcript API routes through
    # Webshare (avoids the transcript IP-block), yt-dlp stays direct (avoids 405).
    cfg = replace(_cfg("u", "p", use_webshare=False), captions_use_webshare=True)
    assert proxy.webshare_config(cfg) is not None
    assert proxy.ytdlp_proxy_url(cfg) is None
