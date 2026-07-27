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
    # OpenRouter + job/discover fields below are consumed by the **yt-mem-ai-desktop**
    # backend (via this shared load_config), NOT by the engine itself — do not remove.
    openrouter_api_key: str | None
    openrouter_model: str
    store_path: Path
    embedding_backend: str
    embedding_model: str | None
    chunk_target_s: float
    openai_api_key: str | None
    hf_token: str | None = None
    log_file: Path = Path("logs/common.jsonl")
    discover_timeout_s: float = 30.0
    # Cap how many newest subscription-feed entries discover pulls. The feed is
    # newest-first; without a cap yt-dlp paginates the entire history (minutes).
    discover_feed_limit: int = 60
    # Incremental discover re-fetches this many seconds before the last high-water
    # mark. approximate_date timestamps are hour-rounded, so a 1h overlap ensures
    # no boundary video is missed; the DB dedupes the re-seen ones.
    discover_overlap_s: float = 3600.0
    # Route yt-dlp / youtube-transcript-api through the Webshare rotating proxy.
    # Default off: a system-level VLESS/VPN proxy already provides the IP, and
    # stacking Webshare on top breaks the authenticated subscription feed (its
    # CONNECT tunnel returns 405). Turn on only if you have no other proxy and
    # YouTube is rate-limiting your raw IP.
    use_webshare: bool = False
    # Route ONLY the transcript API (youtube-transcript-api) through Webshare,
    # leaving yt-dlp direct. Needed because YouTube IP-blocks the transcript
    # endpoint, but yt-dlp's HTTPS CONNECT through Webshare 405s. Independent of
    # use_webshare (which gates yt-dlp). Uses WebshareProxyConfig's rotating proxy.
    captions_use_webshare: bool = False
    job_concurrency: int = 3          # desktop backend: job worker concurrency
    discover_interval_s: float = 3600.0  # desktop backend: background discover timer
    # Preferred caption languages (order = priority). `fetch_captions` tries these
    # first, then falls back to ANY available track (manual preferred over
    # auto-generated) — so non-English videos are no longer skipped. Summaries are
    # produced in the user's target language by the LLM regardless of source lang.
    caption_langs: tuple[str, ...] = ("en",)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _truthy(value: str | None) -> bool:
    return _clean(value) is not None and _clean(value).lower() in ("1", "true", "yes", "on")


def _parse_langs(value: str | None) -> tuple[str, ...]:
    """Comma-separated caption language codes → tuple; default ('en',)."""
    if not value:
        return ("en",)
    langs = tuple(x.strip() for x in value.split(",") if x.strip())
    return langs or ("en",)


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
        "YT_CHUNK_TARGET_S", "OPENAI_API_KEY", "HF_TOKEN", "YT_LOG_FILE",
        "YT_DISCOVER_TIMEOUT_S", "YT_USE_WEBSHARE", "YT_DISCOVER_FEED_LIMIT",
        "YT_DISCOVER_OVERLAP_S",
        "YT_JOB_CONCURRENCY", "YT_DISCOVER_INTERVAL_S", "YT_CAPTION_LANGS",
        "YT_CAPTIONS_USE_WEBSHARE",
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
        hf_token=_clean(data.get("HF_TOKEN")),
        log_file=Path(_clean(data.get("YT_LOG_FILE")) or "logs/common.jsonl"),
        discover_timeout_s=float(_clean(data.get("YT_DISCOVER_TIMEOUT_S")) or "30"),
        use_webshare=_truthy(data.get("YT_USE_WEBSHARE")),
        discover_feed_limit=int(_clean(data.get("YT_DISCOVER_FEED_LIMIT")) or "60"),
        discover_overlap_s=float(_clean(data.get("YT_DISCOVER_OVERLAP_S")) or "3600"),
        job_concurrency=int(_clean(data.get("YT_JOB_CONCURRENCY")) or "3"),
        discover_interval_s=float(_clean(data.get("YT_DISCOVER_INTERVAL_S")) or "3600"),
        caption_langs=_parse_langs(_clean(data.get("YT_CAPTION_LANGS"))),
        captions_use_webshare=_truthy(data.get("YT_CAPTIONS_USE_WEBSHARE")),
    )
