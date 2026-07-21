from __future__ import annotations
from .config import Config


def ytdlp_proxy_url(cfg: Config) -> str | None:
    if cfg.proxy_username and cfg.proxy_password:
        return f"http://{cfg.proxy_username}:{cfg.proxy_password}@p.webshare.io:80"
    return None


def webshare_config(cfg: Config):
    if cfg.proxy_username and cfg.proxy_password:
        from youtube_transcript_api.proxies import WebshareProxyConfig
        return WebshareProxyConfig(
            proxy_username=cfg.proxy_username,
            proxy_password=cfg.proxy_password,
        )
    return None
