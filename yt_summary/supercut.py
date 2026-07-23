# yt_summary/supercut.py
from __future__ import annotations
import os
from dataclasses import dataclass, field

from .compile import compile_highlights
from .download import build_opts

_FORMAT = (
    "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/"
    "best[height<=720][ext=mp4]/best[height<=720]/best"
)

_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


def _fmt_ts(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60:02d}:{s % 60:02d}"


def label_text(clip) -> str:
    return f"{clip.label}  ·  {_fmt_ts(clip.start_s)}  ·  {clip.title or clip.video_id}"


def download_section_opts(clip, cfg, out_path: str) -> dict:
    from yt_dlp.utils import download_range_func
    opts = build_opts(cfg, download_audio=False)
    opts["format"] = _FORMAT
    opts["merge_output_format"] = "mp4"
    opts["download_ranges"] = download_range_func(None, [(clip.start_s, clip.end_s)])
    opts["force_keyframes_at_cuts"] = True
    opts["outtmpl"] = out_path
    return opts


def _scale_pad_fps_vf(width: int, height: int, fps: int) -> str:
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        f"fps={fps}"
    )


def normalize_label_cmd(in_path: str, out_path: str, label_file: str,
                        width: int = 1280, height: int = 720, fps: int = 30,
                        fontfile: str | None = None) -> list[str]:
    vf = (
        f"{_scale_pad_fps_vf(width, height, fps)},"
        f"drawtext=textfile={label_file}:x=(w-text_w)/2:y=h-th-20:"
        f"fontsize=24:fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=8"
    )
    if fontfile:
        vf += f":fontfile={fontfile}"
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", in_path,
            "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac",
            "-r", str(fps), "-y", out_path]


def normalize_cmd(in_path: str, out_path: str,
                  width: int = 1280, height: int = 720, fps: int = 30) -> list[str]:
    vf = _scale_pad_fps_vf(width, height, fps)
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", in_path,
            "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac",
            "-r", str(fps), "-y", out_path]


def _default_ffmpeg_filters_probe() -> bool:
    import subprocess
    result = subprocess.run(["ffmpeg", "-hide_banner", "-filters"],
                            capture_output=True, text=True, check=False)
    return "drawtext" in (result.stdout + result.stderr)


def ffmpeg_has_drawtext(probe_fn=None) -> bool:
    probe_fn = probe_fn or _default_ffmpeg_filters_probe
    try:
        return bool(probe_fn())
    except Exception:  # noqa: BLE001 - any probe failure means "assume unavailable"
        return False


def find_font() -> str | None:
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


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
    workdir: str = ""
    labeled: bool = True
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
                   workdir: str | None = None, download_fn=None, ffmpeg_fn=None,
                   drawtext_probe=None) -> Result:
    download_fn = download_fn or _default_download
    ffmpeg_fn = ffmpeg_fn or _default_ffmpeg
    out_path = os.path.abspath(out_path)
    workdir = os.path.abspath(workdir or (out_path + ".work"))
    os.makedirs(workdir, exist_ok=True)

    use_labels = ffmpeg_has_drawtext(drawtext_probe)
    fontfile = find_font() if use_labels else None

    clips = compile_highlights(db, since, max_minutes)
    rendered, failed, normalized_paths = [], [], []
    for i, clip in enumerate(clips):
        raw = os.path.join(workdir, f"{i:03d}_raw.mp4")
        norm = os.path.join(workdir, f"{i:03d}.mp4")
        label_file = os.path.join(workdir, f"{i:03d}.txt")
        try:
            download_fn(clip, cfg, raw)
            if use_labels:
                with open(label_file, "w") as f:
                    f.write(label_text(clip))
                ffmpeg_fn(normalize_label_cmd(raw, norm, label_file, fontfile=fontfile))
            else:
                ffmpeg_fn(normalize_cmd(raw, norm))
            normalized_paths.append(norm)
            rendered.append(clip)
        except Exception:  # noqa: BLE001 - continue-on-error per clip
            failed.append(clip)

    if not rendered:
        raise RuntimeError("no clips rendered (all downloads/renders failed or no highlights)")

    list_file = os.path.join(workdir, "concat.txt")
    write_concat_list(list_file, normalized_paths)
    try:
        ffmpeg_fn(concat_cmd(list_file, out_path))
    except Exception as exc:
        raise RuntimeError(f"concat failed: {exc}") from exc

    with open(out_path + ".refs.md", "w") as f:
        f.write(refs_markdown(rendered, failed))
    return Result(out_path=out_path, workdir=workdir, labeled=use_labels,
                  rendered=rendered, failed=failed)
