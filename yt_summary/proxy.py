from __future__ import annotations

from typing import TYPE_CHECKING

from .config import Config

if TYPE_CHECKING:
    from youtube_transcript_api.proxies import WebshareProxyConfig


def ytdlp_proxy_url(cfg: Config) -> str | None:
    if cfg.proxy_username and cfg.proxy_password:
        return f"http://{cfg.proxy_username}:{cfg.proxy_password}@p.webshare.io:80"
    return None


def webshare_config(cfg: Config) -> "WebshareProxyConfig | None":
    if cfg.proxy_username and cfg.proxy_password:
        from youtube_transcript_api.proxies import WebshareProxyConfig
        return WebshareProxyConfig(
            proxy_username=cfg.proxy_username,
            proxy_password=cfg.proxy_password,
        )
    return None
