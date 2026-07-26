from __future__ import annotations
from dataclasses import dataclass, field
from ..store.models import Segment


@dataclass
class TranscriptResult:
    source: str
    lang: str | None
    full_text: str
    segments: list[Segment] = field(default_factory=list)


class TranscriptUnavailable(Exception):
    pass


class CaptionsBlocked(Exception):
    """YouTube rate-limited/blocked the transcript request — captions may well
    exist. Retry later, or route through a proxy (YT_USE_WEBSHARE=true). Distinct
    from TranscriptUnavailable (genuinely no captions)."""


def get_transcript(video, audio_path, cfg, captions_fn=None, whisper_fn=None,
                   force_whisper: bool = False) -> "TranscriptResult":
    if whisper_fn is None:
        from .whisper import transcribe_audio as whisper_fn
    if not force_whisper:
        if captions_fn is None:
            from .captions import fetch_captions as captions_fn
        try:
            result = captions_fn(video.video_id, cfg)
        except CaptionsBlocked:
            # Captions exist but were blocked. Fall back to whisper if we have
            # audio; otherwise surface the block (do NOT mislabel as "no captions").
            if not audio_path:
                raise
            result = None
        if result is not None:
            return result
    if audio_path:
        return whisper_fn(audio_path, video.video_id, cfg)
    raise TranscriptUnavailable(f"No captions and no audio for {video.video_id}")
