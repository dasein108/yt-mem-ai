from __future__ import annotations
from ..config import Config
from ..proxy import webshare_config
from ..store.models import Segment
from . import TranscriptResult, CaptionsBlocked

# YouTube rate-limit / IP-block errors. Distinct from "no captions" — the
# transcript may exist; we surface these as CaptionsBlocked (retry / use a proxy).
try:
    from youtube_transcript_api._errors import (
        RequestBlocked, IpBlocked, YouTubeRequestFailed,
    )
    _BLOCK_ERRORS: tuple = (RequestBlocked, IpBlocked, YouTubeRequestFailed)
except Exception:  # library missing or renamed — degrade to old behavior
    _BLOCK_ERRORS = ()


def _fetch_preferred_or_any(api, video_id: str, langs: tuple[str, ...]):
    """Fetch the preferred caption track; else fall back to ANY available track
    (manually-created preferred over auto-generated). Returns a FetchedTranscript
    (iterable of snippets, with `.language_code`) or None. Raises CaptionsBlocked
    when YouTube blocks the request (as opposed to captions being absent)."""
    try:
        return api.fetch(video_id, languages=langs)
    except _BLOCK_ERRORS as exc:
        raise CaptionsBlocked(f"{video_id}: {exc}") from exc
    except Exception:
        pass  # not available in the preferred languages — try any track
    try:
        transcripts = list(api.list(video_id))
    except _BLOCK_ERRORS as exc:
        raise CaptionsBlocked(f"{video_id}: {exc}") from exc
    except Exception:
        return None
    # manual (is_generated == False) first, then auto-generated
    transcripts.sort(key=lambda t: bool(getattr(t, "is_generated", True)))
    for t in transcripts:
        try:
            return t.fetch()
        except _BLOCK_ERRORS as exc:
            raise CaptionsBlocked(f"{video_id}: {exc}") from exc
        except Exception:
            continue
    return None


def fetch_captions(video_id: str, cfg: Config, api_factory=None) -> TranscriptResult | None:
    if api_factory is None:
        from youtube_transcript_api import YouTubeTranscriptApi as api_factory  # noqa: N813
    proxy = webshare_config(cfg)
    api = api_factory(proxy_config=proxy) if proxy else api_factory()
    langs = tuple(cfg.caption_langs) or ("en",)
    fetched = _fetch_preferred_or_any(api, video_id, langs)
    if fetched is None:
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
