from tests.support import fake_embedder
from yt_summary.store import models
from yt_summary.store.models import Video, Segment, TranscriptRow


def test_dataclasses_still_present():
    v = Video(video_id="abc", url="u")
    assert v.status == "discovered"
    s = Segment(video_id="abc", start_s=0.0, end_s=1.0, text="hi")
    assert s.end_s == 1.0
    t = TranscriptRow("abc", "captions", "en", "hi", "2026-07-22T00:00:00+00:00")
    assert t.source == "captions"


def test_lance_schemas_have_expected_fields():
    assert set(models.VideoSchema.model_fields) == {
        "video_id", "channel_id", "title", "url", "duration_s",
        "published_at", "fetched_at", "audio_path", "status"}
    assert set(models.TranscriptSchema.model_fields) == {
        "video_id", "source", "lang", "full_text", "created_at"}
    assert set(models.StateSchema.model_fields) == {"key", "value"}


def test_chunk_schema_carries_vector():
    Chunk = models.chunk_schema(fake_embedder())
    fields = set(Chunk.model_fields)
    assert {"id", "video_id", "start_s", "end_s", "text", "vector"} <= fields
