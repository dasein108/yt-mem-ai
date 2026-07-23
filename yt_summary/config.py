from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import dotenv_values


@dataclass(frozen=True)
class Config:
    downloads_dir: Path
    proxy_username: str | None
    proxy_password: str | None
    cookies_browser: str | None
    whisper_model: str
    whisper_device: str
    whisper_compute_type: str
    openrouter_api_key: str | None
    openrouter_model: str
    store_path: Path
    embedding_backend: str
    embedding_model: str | None
    chunk_target_s: float
    openai_api_key: str | None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def load_config(env_path: Path | None = None) -> Config:
    if env_path is None:
        env_path = Path(".env")
    data: dict[str, str | None] = {}
    if Path(env_path).exists():
        data.update(dotenv_values(env_path))
    # process env overrides file
    for key in (
        "WEBSHARE_PROXY_USERNAME", "WEBSHARE_PROXY_PASSWORD", "YT_COOKIES_BROWSER",
        "YT_DOWNLOADS_DIR", "YT_WHISPER_MODEL", "YT_WHISPER_DEVICE",
        "YT_WHISPER_COMPUTE_TYPE", "OPENROUTER_API_KEY", "YT_OPENROUTER_MODEL",
        "YT_STORE_PATH", "YT_EMBEDDING_BACKEND", "YT_EMBEDDING_MODEL",
        "YT_CHUNK_TARGET_S", "OPENAI_API_KEY",
    ):
        if os.environ.get(key) is not None:
            data[key] = os.environ[key]

    return Config(
        downloads_dir=Path(_clean(data.get("YT_DOWNLOADS_DIR")) or "downloads"),
        proxy_username=_clean(data.get("WEBSHARE_PROXY_USERNAME")),
        proxy_password=_clean(data.get("WEBSHARE_PROXY_PASSWORD")),
        cookies_browser=_clean(data.get("YT_COOKIES_BROWSER")),
        whisper_model=_clean(data.get("YT_WHISPER_MODEL")) or "small",
        whisper_device=_clean(data.get("YT_WHISPER_DEVICE")) or "cpu",
        whisper_compute_type=_clean(data.get("YT_WHISPER_COMPUTE_TYPE")) or "int8",
        openrouter_api_key=_clean(data.get("OPENROUTER_API_KEY")),
        openrouter_model=_clean(data.get("YT_OPENROUTER_MODEL")) or "openai/gpt-4o-mini",
        store_path=Path(_clean(data.get("YT_STORE_PATH")) or "yt_lance"),
        embedding_backend=_clean(data.get("YT_EMBEDDING_BACKEND")) or "local",
        embedding_model=_clean(data.get("YT_EMBEDDING_MODEL")),
        chunk_target_s=float(_clean(data.get("YT_CHUNK_TARGET_S")) or "45"),
        openai_api_key=_clean(data.get("OPENAI_API_KEY")),
    )
