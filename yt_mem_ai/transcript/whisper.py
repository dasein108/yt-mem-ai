from __future__ import annotations
from ..config import Config
from ..store.models import Segment
from . import TranscriptResult


def transcribe_audio(audio_path: str, video_id: str, cfg: Config,
                     model_factory=None) -> TranscriptResult:
    if model_factory is None:
        from faster_whisper import WhisperModel as model_factory  # noqa: N813
    model = model_factory(cfg.whisper_model, device=cfg.whisper_device,
                          compute_type=cfg.whisper_compute_type)
    segments_iter, info = model.transcribe(audio_path, beam_size=5)
    segments: list[Segment] = []
    texts: list[str] = []
    for seg in segments_iter:
        text = seg.text.strip()
        segments.append(Segment(video_id=video_id, start_s=float(seg.start),
                                end_s=float(seg.end), text=text))
        texts.append(text)
    return TranscriptResult(source="whisper", lang=getattr(info, "language", None),
                            full_text=" ".join(texts), segments=segments)
