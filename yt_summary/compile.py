# yt_summary/compile.py
from __future__ import annotations
import json
from dataclasses import dataclass

DEFAULT_FALLBACK_S = 45.0


def deep_link(video_id: str, start_s: float) -> str:
    return f"https://www.youtube.com/watch?v={video_id}&t={int(start_s)}s"


def chunk_span(chunks: list[dict], start_s: float, fallback_s: float) -> tuple[float, float]:
    for c in chunks:
        cs, ce = c.get("start_s"), c.get("end_s")
        if cs is not None and ce is not None and float(cs) <= start_s <= float(ce):
            return float(cs), float(ce)
    with_start = [c for c in chunks if c.get("start_s") is not None]
    if with_start:
        nearest = min(with_start, key=lambda c: abs(float(c["start_s"]) - start_s))
        ns = float(nearest["start_s"])
        ne = float(nearest["end_s"]) if nearest.get("end_s") is not None else ns + fallback_s
        return ns, ne
    return start_s, start_s + fallback_s


@dataclass
class Clip:
    video_id: str
    title: str | None
    label: str
    start_s: float
    end_s: float
    duration_s: float
    link: str


def _parse_highlights(raw) -> list[dict]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        return []
    return value if isinstance(value, list) else []


def video_clips(video, summary, chunks: list[dict], fallback_s: float = DEFAULT_FALLBACK_S) -> list[Clip]:
    highlights = _parse_highlights(summary.get("highlights") if summary else None)
    clips: list[Clip] = []
    for h in highlights:
        start = h.get("start_s")
        if start is None:
            continue
        start = float(start)
        s, e = chunk_span(chunks, start, fallback_s)
        clips.append(Clip(
            video_id=video.video_id, title=video.title, label=str(h.get("label", "")),
            start_s=s, end_s=e, duration_s=max(0.0, e - s), link=deep_link(video.video_id, s)))
    clips.sort(key=lambda c: c.start_s)
    return clips


def accumulate(clips: list[Clip], max_seconds: float) -> list[Clip]:
    out: list[Clip] = []
    total = 0.0
    for clip in clips:
        out.append(clip)
        total += clip.duration_s
        if total >= max_seconds:
            break
    return out


def _fmt_ts(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60:02d}:{s % 60:02d}"


def render_markdown(clips: list[Clip], since: str | None, max_minutes: float) -> str:
    lines = ["# Highlights", "",
             f"_since {since or 'today'} · budget {int(max_minutes)} min · {len(clips)} clips_", ""]
    by_video: dict[str, list[Clip]] = {}
    for c in clips:
        by_video.setdefault(c.video_id, []).append(c)
    for vid, cs in by_video.items():
        lines.append(f"## {cs[0].title or vid}")
        lines.append(f"<https://www.youtube.com/watch?v={vid}>")
        for c in cs:
            lines.append(f"- [{_fmt_ts(c.start_s)}] {c.label} — {c.link}")
        lines.append("")
    return "\n".join(lines)
