from __future__ import annotations
from datetime import datetime, UTC
from .config import Config
from .proxy import ytdlp_proxy_url
from .cookies import cookie_opts
from .store.models import Video


def build_opts(cfg: Config, download_audio: bool) -> dict:
    opts: dict = {
        "quiet": True,
        "noprogress": True,
        "outtmpl": str(cfg.downloads_dir / "%(id)s.%(ext)s"),
    }
    proxy = ytdlp_proxy_url(cfg)
    if proxy:
        opts["proxy"] = proxy
    opts.update(cookie_opts(cfg))
    if download_audio:
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
        }]
        # Resolving audio stream URLs needs YouTube's n-challenge/signature
        # solved, which requires a JS runtime (deno) + the EJS solver script.
        # Enable the remote solver so real audio formats appear (otherwise only
        # image formats are offered → "Requested format is not available").
        opts["remote_components"] = ["ejs:github"]
    return opts


def _fmt_date(upload_date: str | None) -> str | None:
    if not upload_date:
        return None
    return datetime.strptime(upload_date, "%Y%m%d").strftime("%Y-%m-%d")


def video_from_info(info: dict, url: str) -> Video:
    tags = info.get("tags") or []
    return Video(
        video_id=info["id"],
        url=info.get("webpage_url") or url,
        channel_id=info.get("channel_id"),
        channel=info.get("channel") or info.get("uploader"),
        title=info.get("title"),
        duration_s=info.get("duration"),
        published_at=_fmt_date(info.get("upload_date")),
        description=info.get("description"),
        tags=",".join(tags) or None,
        fetched_at=datetime.now(UTC).isoformat(),
        status="downloaded",
        live_status=info.get("live_status"),
    )


def _audio_path(info: dict) -> str | None:
    reqs = info.get("requested_downloads") or []
    if reqs:
        return reqs[0].get("filepath")
    return None


def download(url: str, cfg: Config, ydl_factory=None) -> tuple[Video, str | None]:
    if ydl_factory is None:
        from yt_dlp import YoutubeDL as ydl_factory  # noqa: N813
    cfg.downloads_dir.mkdir(parents=True, exist_ok=True)
    opts = build_opts(cfg, download_audio=True)
    with ydl_factory(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    video = video_from_info(info, url)
    audio = _audio_path(info)
    video.audio_path = audio
    return video, audio


def download_metadata(url: str, cfg: Config, ydl_factory=None) -> Video:
    """Fetch video metadata only — no audio download. Used by the captions-only
    path, which never needs the audio (no whisper fallback)."""
    if ydl_factory is None:
        from yt_dlp import YoutubeDL as ydl_factory  # noqa: N813
    opts = build_opts(cfg, download_audio=False)
    opts["skip_download"] = True
    with ydl_factory(opts) as ydl:
        # process=False skips format selection, which needs the JS challenge
        # solver and otherwise raises "Requested format is not available" —
        # metadata (title/description/tags/upload_date) is still returned.
        info = ydl.extract_info(url, download=False, process=False) or {}
    return video_from_info(info, url)
