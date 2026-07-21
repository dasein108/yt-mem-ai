from __future__ import annotations
from .config import Config


def cookie_opts(cfg: Config) -> dict:
    if cfg.cookies_browser:
        return {"cookiesfrombrowser": (cfg.cookies_browser,)}
    return {}
