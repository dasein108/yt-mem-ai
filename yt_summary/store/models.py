from __future__ import annotations
from dataclasses import dataclass


@dataclass
class Video:
    video_id: str
    url: str
    channel_id: str | None = None
    title: str | None = None
    duration_s: int | None = None
    published_at: str | None = None
    fetched_at: str | None = None
    audio_path: str | None = None
    status: str = "discovered"


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
