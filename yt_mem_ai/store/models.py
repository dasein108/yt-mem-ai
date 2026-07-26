from __future__ import annotations
from dataclasses import dataclass

from lancedb.pydantic import LanceModel, Vector


@dataclass
class Video:
    video_id: str
    url: str
    channel_id: str | None = None
    channel: str | None = None
    title: str | None = None
    duration_s: int | None = None
    published_at: str | None = None
    description: str | None = None
    tags: str | None = None  # comma-joined
    fetched_at: str | None = None
    audio_path: str | None = None
    status: str = "discovered"
    # yt-dlp live_status (is_live / is_upcoming / post_live / was_live / not_live /
    # None). Persisted so batch ingestion can mark + skip streams. See is_stream().
    live_status: str | None = None
    # Approximate publish epoch (seconds, UTC) carried through discovery for the
    # incremental high-water mark. NOT in VideoSchema, so it is never persisted —
    # `_VIDEO_FIELDS` (schema-derived) skips it on read/write.
    published_ts: float | None = None


# Live-stream live_status values: batch ingestion marks these and skips
# transcription (they're long + usually caption-less); transcribe on demand.
_STREAM_LIVE_STATUSES = {"is_live", "is_upcoming", "post_live", "was_live"}


def is_stream(video) -> bool:
    """True if the video is a live stream (live now / upcoming / just-ended / a
    past-live VOD)."""
    return getattr(video, "live_status", None) in _STREAM_LIVE_STATUSES


@dataclass
class Segment:
    video_id: str
    start_s: float
    end_s: float
    text: str
    id: int | None = None


@dataclass
class TranscriptRow:
    video_id: str
    source: str
    lang: str | None
    full_text: str
    created_at: str


class VideoSchema(LanceModel):
    video_id: str
    channel_id: str | None = None
    channel: str | None = None
    title: str | None = None
    url: str | None = None
    duration_s: int | None = None
    published_at: str | None = None
    description: str | None = None
    tags: str | None = None
    fetched_at: str | None = None
    audio_path: str | None = None
    status: str = "discovered"
    live_status: str | None = None


class ChannelSchema(LanceModel):
    channel_id: str
    title: str | None = None
    subscribed: int = 0


class TranscriptSchema(LanceModel):
    video_id: str
    source: str | None = None
    lang: str | None = None
    full_text: str = ""
    created_at: str | None = None


class SummarySchema(LanceModel):
    video_id: str
    summary_md: str = ""
    highlights: str | None = None
    qa: str | None = None
    model: str | None = None
    created_at: str | None = None


class FeedbackSchema(LanceModel):
    video_id: str
    signal: int
    created_at: str


class StateSchema(LanceModel):
    key: str
    value: str | None = None


class JobSchema(LanceModel):
    id: str
    kind: str
    video_id: str | None = None
    status: str = "queued"
    progress: float | None = None
    error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


def chunk_schema(embedder) -> type[LanceModel]:
    class ChunkSchema(LanceModel):
        id: str
        video_id: str
        start_s: float
        end_s: float
        text: str = embedder.SourceField()
        vector: Vector(embedder.ndims()) = embedder.VectorField()

    return ChunkSchema
