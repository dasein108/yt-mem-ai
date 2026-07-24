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
        # subscriptions/channels tabs require auth; skip yt-dlp's authcheck so a
        # first-account-only cookie jar still extracts the feed. approximate_date
        # makes the flat feed carry a per-entry `timestamp` (from YouTube's "N
        # hours ago"), so we get dates in the single feed call — no per-video
        # lookups. Approximate to the hour, which is fine for date filtering.
        opts["extractor_args"] = {"youtubetab": {"skip": ["authcheck"],
                                                 "approximate_date": ["true"]}}
        # Bound pagination + network: the subscriptions feed is newest-first, so
        # the newest `discover_feed_limit` entries are what a daily run needs;
        # without playlistend yt-dlp walks the entire history (minutes).
        opts["playlistend"] = cfg.discover_feed_limit
        opts["socket_timeout"] = 20
        opts["retries"] = 1
        opts["extractor_retries"] = 1
        # Flat playlist extraction must be processed to yield entries. Per-video
        # date lookups use process=False: format selection (which needs the JS
        # challenge solver and fails without it) is skipped, but upload_date /
        # timestamp are still present in the raw info.
        with YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False, process=bool(flat)) or {}

    return extract_fn


def _to_ts(value) -> float | None:
    """Convert a yt-dlp timestamp (epoch) or upload_date (YYYYMMDD) to an epoch
    float (seconds, UTC). Dates map to that day's 00:00 UTC."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value)
    if len(text) == 8 and text.isdigit():
        return datetime.strptime(text, "%Y%m%d").replace(tzinfo=UTC).timestamp()
    return None


def _ts_to_date(ts: float | None) -> str | None:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d") if ts is not None else None


def _day_epoch(date_str: str) -> float:
    """Start-of-day epoch (00:00 UTC) for a YYYY-MM-DD cutoff string."""
    return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC).timestamp()


def _published_ts(entry: dict, extract_fn) -> float | None:
    ts = _to_ts(entry.get("timestamp"))
    if ts is None:
        ts = _to_ts(entry.get("upload_date"))
    if ts is not None:
        return ts
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
    return _to_ts(info.get("timestamp")) or _to_ts(info.get("upload_date"))


def _entry_to_video(entry: dict, published_ts: float | None) -> Video:
    vid = entry["id"]
    url = entry.get("url") or entry.get("webpage_url") or f"https://www.youtube.com/watch?v={vid}"
    return Video(
        video_id=vid,
        url=url,
        channel_id=entry.get("channel_id"),
        title=entry.get("title"),
        duration_s=entry.get("duration"),
        published_at=_ts_to_date(published_ts),
        published_ts=published_ts,
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


def _keep_duration(entry: dict, min_duration: int) -> bool:
    dur = entry.get("duration")
    return dur is None or dur >= min_duration  # keep live/unknown-duration entries


def discover(cfg: Config, after: str | None = None, deep: bool = False,
             min_duration: int = 120, extract_fn=None,
             timeout_s: float | None = None,
             after_ts: float | None = None, overlap_s: float = 0.0) -> list[Video]:
    """Discover subscription uploads newer than a cutoff.

    Cutoff precedence: `after_ts` (an exact epoch, from the incremental
    high-water mark) wins over `after` (a YYYY-MM-DD string). `overlap_s` is
    subtracted from whichever cutoff so hour-rounded approximate dates near the
    boundary aren't missed — the DB dedupes the re-seen videos.
    """
    if extract_fn is None:
        extract_fn = _default_extract_fn(cfg)
    timeout_s = timeout_s if timeout_s is not None else cfg.discover_timeout_s
    if timeout_s and timeout_s > 0:
        # Bound EACH extraction call by timeout_s. The feed/channel-list call is
        # where the Chrome-cookie Keychain hang bites and fails fast to the CLI;
        # per-video fallback lookups are also bounded but their DiscoverTimeout is
        # caught by _published_ts's best-effort handler (kept, ts -> None).
        _raw = extract_fn

        def timed_extract_fn(url: str, flat: bool) -> dict:
            try:
                return _run_with_timeout(lambda: _raw(url, flat), timeout_s)
            except DiscoverTimeout:
                blog("discover.timeout", level="error", msg="extraction timed out",
                     url=url, timeout_s=timeout_s)
                raise

        extract_fn = timed_extract_fn

    if after_ts is not None:
        cutoff_ts = after_ts - overlap_s
    elif after:
        cutoff_ts = _day_epoch(after) - overlap_s
    else:
        cutoff_ts = None  # no lower bound

    out: list[Video] = []
    for entries in _sources(extract_fn, deep):
        for entry in entries:
            # approximate_date puts a `timestamp` on each flat entry, so this
            # resolves inline with no network. The per-video fallback only fires
            # for the rare entry that still lacks a date.
            ts = _published_ts(entry, extract_fn)
            if cutoff_ts is not None and ts is not None and ts < cutoff_ts:
                break  # source is newest-first: the rest are older
            if not _keep_duration(entry, min_duration):
                continue
            out.append(_entry_to_video(entry, ts))
    return out
