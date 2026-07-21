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
    return opts


def _fmt_date(upload_date: str | None) -> str | None:
    if not upload_date:
        return None
    return datetime.strptime(upload_date, "%Y%m%d").strftime("%Y-%m-%d")


def video_from_info(info: dict, url: str) -> Video:
    return Video(
        video_id=info["id"],
        url=info.get("webpage_url") or url,
        channel_id=info.get("channel_id"),
        title=info.get("title"),
        duration_s=info.get("duration"),
        published_at=_fmt_date(info.get("upload_date")),
        fetched_at=datetime.now(UTC).isoformat(),
        status="downloaded",
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
