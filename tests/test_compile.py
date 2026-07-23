from types import SimpleNamespace
import json
from yt_summary import compile as C


def _chunks(spans):
    return [{"video_id": "v", "start_s": s, "end_s": e, "text": "t"} for s, e in spans]


def test_deep_link_floors_int():
    assert C.deep_link("abc", 11.7) == "https://www.youtube.com/watch?v=abc&t=11s"


def test_chunk_span_containing():
    assert C.chunk_span(_chunks([(0, 10), (10, 20)]), 12.0, 45.0) == (10.0, 20.0)


def test_chunk_span_nearest_when_none_contains():
    # 8.0 is not inside [0,5] or [10,15]; nearest by start_s is (10,15)? |10-8|=2 < |0-8|=8
    assert C.chunk_span(_chunks([(0, 5), (10, 15)]), 8.0, 45.0) == (10.0, 15.0)


def test_chunk_span_empty_fallback():
    assert C.chunk_span([], 30.0, 45.0) == (30.0, 75.0)


def test_video_clips_builds_from_highlights():
    v = SimpleNamespace(video_id="v", title="Title")
    summary = {"highlights": json.dumps([{"start_s": 10, "label": "A"}, {"start_s": 0, "label": "B"}])}
    clips = C.video_clips(v, summary, _chunks([(0, 8), (10, 20)]))
    assert [c.label for c in clips] == ["B", "A"]           # sorted by start_s
    assert clips[1].link == "https://www.youtube.com/watch?v=v&t=10s"
    assert clips[1].duration_s == 10.0


def test_video_clips_bad_json_empty():
    v = SimpleNamespace(video_id="v", title="T")
    assert C.video_clips(v, {"highlights": "not json"}, []) == []
    assert C.video_clips(v, {"highlights": None}, []) == []
    assert C.video_clips(v, None, []) == []


def test_accumulate_budget():
    mk = lambda d: C.Clip("v", "T", "l", 0, d, d, "u")  # noqa: E731
    clips = [mk(10), mk(10), mk(10)]
    got = C.accumulate(clips, 15)          # 10 -> 20 crosses 15 → include the crosser, stop
    assert [c.duration_s for c in got] == [10, 10]
    assert C.accumulate(clips, 0) == [clips[0]]   # always >= 1


def test_render_markdown_groups_and_links():
    clips = [C.Clip("v1", "First", "hi", 10, 20, 10, "https://www.youtube.com/watch?v=v1&t=10s")]
    md = C.render_markdown(clips, "2026-07-23", 20)
    assert "# Highlights" in md
    assert "## First" in md
    assert "[00:10] hi" in md
    assert "watch?v=v1&t=10s" in md
