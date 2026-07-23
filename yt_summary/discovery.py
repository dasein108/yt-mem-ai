# yt_summary/discovery.py
from __future__ import annotations
import threading
from datetime import datetime, UTC
from .config import Config
from .download import build_opts
from .obs import blog
from .store.models import Video

FEED_URL = "https://www.youtube.com/feed/subscriptions"
CHANNELS_URL = "https://www.youtube.com/feed/channels"


class DiscoverTimeout(RuntimeError):
    """A YouTube extraction call exceeded the discover timeout (commonly a
    macOS Chrome-cookie Keychain prompt blocking headlessly)."""


def _run_with_timeout(fn, timeout_s: float):
    """Run fn() in a daemon thread bounded by timeout_s. Raises DiscoverTimeout
    if it doesn't finish (the blocked thread is abandoned, dying with the process)."""
    box: dict = {}

    def run() -> None:
        try:
            box["value"] = fn()
        except Exception as exc:  # noqa: BLE001 - re-raised on the caller thread
            box["error"] = exc

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        raise DiscoverTimeout(
            f"discover timed out after {timeout_s:g}s waiting on YouTube. "
            "This usually means a Chrome Keychain prompt for cookie access is "
            "blocking — grant it by running discover interactively (e.g. quit Chrome "
            "first, or run in your terminal so you can approve the prompt), or set "
            "YT_COOKIES_BROWSER to a different browser. Add WEBSHARE_PROXY_* if YouTube "
            "is rate-limiting this IP."
        )
    if "error" in box:
        raise box["error"]
    return box.get("value")


def _default_extract_fn(cfg: Config):
    from yt_dlp import YoutubeDL
    base = build_opts(cfg, download_audio=False)

    def extract_fn(url: str, flat: bool) -> dict:
        opts = dict(base)
        opts["skip_download"] = True
        opts["extract_flat"] = "in_playlist" if flat else False
        with YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False) or {}

    return extract_fn


def _to_date(value) -> str | None:
    """Convert a yt-dlp timestamp (epoch) or upload_date (YYYYMMDD) to YYYY-MM-DD."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, UTC).strftime("%Y-%m-%d")
    text = str(value)
    if len(text) == 8 and text.isdigit():
        return datetime.strptime(text, "%Y%m%d").strftime("%Y-%m-%d")
    return None


def _published_date(entry: dict, extract_fn) -> str | None:
    pub = _to_date(entry.get("timestamp")) or _to_date(entry.get("upload_date"))
    if pub:
        return pub
    vid = entry.get("id")
    url = entry.get("url") or entry.get("webpage_url") or (
        f"https://www.youtube.com/watch?v={vid}" if vid else None
    )
    if not url:
        return None
    try:
        info = extract_fn(url, False) or {}
    except Exception:
        return None
    return _to_date(info.get("timestamp")) or _to_date(info.get("upload_date"))


def _entry_to_video(entry: dict, published_at: str | None) -> Video:
    vid = entry["id"]
    url = entry.get("url") or entry.get("webpage_url") or f"https://www.youtube.com/watch?v={vid}"
    return Video(
        video_id=vid,
        url=url,
        channel_id=entry.get("channel_id"),
        title=entry.get("title"),
        duration_s=entry.get("duration"),
        published_at=published_at,
        fetched_at=datetime.now(UTC).isoformat(),
        status="discovered",
    )


def _sources(extract_fn, deep: bool) -> list[list[dict]]:
    feed = extract_fn(FEED_URL, True) or {}
    sources = [feed.get("entries") or []]
    if deep:
        chans = extract_fn(CHANNELS_URL, True) or {}
        for c in (chans.get("entries") or []):
            url = c.get("url")
            if not url and c.get("id"):
                url = f"https://www.youtube.com/channel/{c['id']}/videos"
            if not url:
                continue
            try:
                cvids = extract_fn(url, True) or {}
                sources.append(cvids.get("entries") or [])
            except Exception:
                continue  # best-effort per channel
    return sources


def discover(cfg: Config, after: str, deep: bool = False,
             min_duration: int = 120, extract_fn=None,
             timeout_s: float | None = None) -> list[Video]:
    if extract_fn is None:
        extract_fn = _default_extract_fn(cfg)
    timeout_s = timeout_s if timeout_s is not None else cfg.discover_timeout_s
    if timeout_s and timeout_s > 0:
        raw = extract_fn

        def extract_fn(url: str, flat: bool) -> dict:  # noqa: F811 - wrap each call in a timeout
            try:
                return _run_with_timeout(lambda: raw(url, flat), timeout_s)
            except DiscoverTimeout:
                blog("discover.timeout", level="error", msg="extraction timed out",
                     url=url, timeout_s=timeout_s)
                raise
    out: list[Video] = []
    for entries in _sources(extract_fn, deep):
        for entry in entries:
            pub = _published_date(entry, extract_fn)
            if pub is not None and pub < after:
                break  # source is newest-first: the rest are older
            dur = entry.get("duration")
            if dur is not None and dur < min_duration:
                continue
            out.append(_entry_to_video(entry, pub))
    return out
