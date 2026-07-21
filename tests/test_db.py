from yt_summary.store.models import Video, Segment, TranscriptRow


def test_video_dataclass_defaults():
    v = Video(video_id="abc", url="https://y/abc")
    assert v.video_id == "abc"
    assert v.status == "discovered"
    assert v.channel_id is None


def test_segment_and_transcript():
    s = Segment(video_id="abc", start_s=0.0, end_s=1.5, text="hi")
    assert s.id is None and s.end_s == 1.5
    t = TranscriptRow(
        video_id="abc",
        source="captions",
        lang="en",
        full_text="hi there",
        created_at="2026-07-21T00:00:00+00:00",
    )
    assert t.source == "captions"
