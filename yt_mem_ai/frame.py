# yt_mem_ai/frame.py
from __future__ import annotations

import os

from .download import build_opts
from .supercut import _FORMAT


class FrameError(Exception):
    """Raised when a frame grab cannot be completed."""


def parse_timestamp(text: str) -> float:
    """Parse '90', '90.5', '1:30', or '1:02:03' into seconds."""
    text = (text or "").strip()
    if not text:
        raise ValueError(f"invalid timestamp: {text!r}")
    parts = text.split(":")
    if len(parts) > 3:
        raise ValueError(f"invalid timestamp: {text!r}")
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        raise ValueError(f"invalid timestamp: {text!r}")
    if any(n < 0 for n in nums):
        raise ValueError(f"invalid timestamp: {text!r}")
    seconds = 0.0
    for n in nums:
        seconds = seconds * 60 + n
    return seconds


def frame_download_opts(url: str, at_s: float, cfg, out_path: str) -> dict:
    """yt-dlp opts: a 1s 720p section at at_s, written to out_path."""
    from yt_dlp.utils import download_range_func
    opts = build_opts(cfg, download_audio=False)
    opts["format"] = _FORMAT
    opts["merge_output_format"] = "mp4"
    opts["download_ranges"] = download_range_func(None, [(at_s, at_s + 1.0)])
    opts["force_keyframes_at_cuts"] = True
    opts["outtmpl"] = out_path
    opts["quiet"] = True
    return opts


def extract_frame_cmd(clip_path: str, out_path: str) -> list[str]:
    """ffmpeg argv: grab the first frame of clip_path as an image."""
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", clip_path, "-frames:v", "1", "-q:v", "2", out_path]


def _default_download(url: str, at_s: float, cfg, out_path: str) -> None:
    from yt_dlp import YoutubeDL
    opts = frame_download_opts(url, at_s, cfg, out_path)
    with YoutubeDL(opts) as ydl:
        ydl.download([url])


def _default_ffmpeg(argv: list[str]) -> None:
    import subprocess
    subprocess.run(argv, check=True)
