from __future__ import annotations
from ..config import Config
from ..proxy import webshare_config
from ..store.models import Segment
from . import TranscriptResult


def fetch_captions(video_id: str, cfg: Config, api_factory=None) -> TranscriptResult | None:
    if api_factory is None:
        from youtube_transcript_api import YouTubeTranscriptApi as api_factory  # noqa: N813
    proxy = webshare_config(cfg)
    api = api_factory(proxy_config=proxy) if proxy else api_factory()
    try:
        fetched = api.fetch(video_id, languages=("en",))
    except Exception:
        return None
    segments: list[Segment] = []
    texts: list[str] = []
    for snip in fetched:
        start = float(snip.start)
        end = start + float(snip.duration)
        segments.append(Segment(video_id=video_id, start_s=start, end_s=end, text=snip.text))
        texts.append(snip.text)
    lang = getattr(fetched, "language_code", None)
    return TranscriptResult(source="captions", lang=lang,
                            full_text=" ".join(texts), segments=segments)
