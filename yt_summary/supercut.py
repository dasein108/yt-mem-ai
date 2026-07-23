# yt_summary/supercut.py
from __future__ import annotations
import os
from dataclasses import dataclass, field

from .compile import compile_highlights
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


@dataclass
class Result:
    out_path: str
    rendered: list = field(default_factory=list)
    failed: list = field(default_factory=list)


def _default_download(clip, cfg, out_path: str) -> None:
    from yt_dlp import YoutubeDL
    opts = download_section_opts(clip, cfg, out_path)
    with YoutubeDL(opts) as ydl:
        ydl.download([f"https://www.youtube.com/watch?v={clip.video_id}"])


def _default_ffmpeg(argv: list[str]) -> None:
    import subprocess
    subprocess.run(argv, check=True)


def build_supercut(db, since: str, max_minutes: float, out_path: str, cfg=None,
                   workdir: str | None = None, download_fn=None, ffmpeg_fn=None) -> Result:
    download_fn = download_fn or _default_download
    ffmpeg_fn = ffmpeg_fn or _default_ffmpeg
    workdir = workdir or (out_path + ".work")
    os.makedirs(workdir, exist_ok=True)

    clips = compile_highlights(db, since, max_minutes)
    rendered, failed, normalized_paths = [], [], []
    for i, clip in enumerate(clips):
        raw = os.path.join(workdir, f"{i:03d}_raw.mp4")
        norm = os.path.join(workdir, f"{i:03d}.mp4")
        label_file = os.path.join(workdir, f"{i:03d}.txt")
        try:
            download_fn(clip, cfg, raw)
            with open(label_file, "w") as f:
                f.write(label_text(clip))
            ffmpeg_fn(normalize_label_cmd(raw, norm, label_file))
            normalized_paths.append(norm)
            rendered.append(clip)
        except Exception:  # noqa: BLE001 - continue-on-error per clip
            failed.append(clip)

    if not rendered:
        raise RuntimeError("no clips rendered (all downloads/renders failed or no highlights)")

    list_file = os.path.join(workdir, "concat.txt")
    write_concat_list(list_file, normalized_paths)
    ffmpeg_fn(concat_cmd(list_file, out_path))

    with open(out_path + ".refs.md", "w") as f:
        f.write(refs_markdown(rendered, failed))
    return Result(out_path=out_path, rendered=rendered, failed=failed)
