# yt_summary/supercut.py
from __future__ import annotations
from .download import build_opts

_FORMAT = "bestvideo[height<=720]+bestaudio/best[height<=720]"


def _fmt_ts(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60:02d}:{s % 60:02d}"


def label_text(clip) -> str:
    return f"{clip.label}  ·  {_fmt_ts(clip.start_s)}  ·  {clip.title or clip.video_id}"


def download_section_opts(clip, cfg, out_path: str) -> dict:
    from yt_dlp.utils import download_range_func
    opts = build_opts(cfg, download_audio=False)
    opts["format"] = _FORMAT
    opts["download_ranges"] = download_range_func(None, [(clip.start_s, clip.end_s)])
    opts["force_keyframes_at_cuts"] = True
    opts["outtmpl"] = out_path
    return opts


def normalize_label_cmd(in_path: str, out_path: str, label_file: str,
                        width: int = 1280, height: int = 720, fps: int = 30) -> list[str]:
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        f"fps={fps},"
        f"drawtext=textfile={label_file}:x=(w-text_w)/2:y=h-th-20:"
        f"fontsize=24:fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=8"
    )
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", in_path,
            "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac",
            "-r", str(fps), "-y", out_path]


def write_concat_list(list_file: str, clip_paths: list[str]) -> None:
    with open(list_file, "w") as f:
        for p in clip_paths:
            f.write(f"file '{p}'\n")


def concat_cmd(list_file: str, out_path: str) -> list[str]:
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "concat",
            "-safe", "0", "-i", list_file, "-c", "copy", "-y", out_path]


def refs_markdown(rendered, failed) -> str:
    lines = ["# Supercut refs", ""]
    for c in rendered:
        lines.append(f"- [{_fmt_ts(c.start_s)}] {c.label} — "
                     f"https://www.youtube.com/watch?v={c.video_id}&t={int(c.start_s)}s "
                     f"({c.title or c.video_id})")
    if failed:
        lines += ["", "## Skipped (download/render failed)"]
        for c in failed:
            lines.append(f"- {c.video_id}: {c.label}")
    return "\n".join(lines)
