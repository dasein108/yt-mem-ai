from __future__ import annotations
from pydantic import BaseModel


class VideoOut(BaseModel):
    video_id: str
    title: str | None = None
    url: str | None = None
    status: str | None = None
    published_at: str | None = None
    duration_s: int | None = None
    channel_id: str | None = None
    channel: str | None = None
    tags: str | None = None
    description: str | None = None


class VideoDetailOut(VideoOut):
    transcript: str | None = None
    summary: dict | None = None


class SearchHit(BaseModel):
    video_id: str
    start_s: float | None = None
    end_s: float | None = None
    text: str | None = None


class RecommendItem(VideoOut):
    score: float


class FeedbackIn(BaseModel):
    video_id: str
    signal: int


class JobOut(BaseModel):
    id: str
    kind: str
    status: str
    progress: float | None = None
    result: dict | None = None
    error: str | None = None
    created_at: str
    video_id: str | None = None
    updated_at: str | None = None


class VideoPageOut(BaseModel):
    items: list[VideoOut]
    total: int


class StatusOut(BaseModel):
    counts: dict[str, int]


class FetchIn(BaseModel):
    url: str
    force: bool = False


class DiscoverIn(BaseModel):
    after: str | None = None
    deep: bool = False
    min_duration: int = 120


class FetchPendingIn(BaseModel):
    since: str | None = None
    limit: int | None = None


class SummarizeIn(BaseModel):
    video_id: str


class LogIn(BaseModel):
    event: str
    level: str | None = None
    msg: str | None = None
    ctx: dict | None = None
