# tests/test_discovery.py
import time
from datetime import datetime, UTC
from pathlib import Path
import pytest
from yt_mem_ai.config import Config
from yt_mem_ai import discovery


def _epoch(y, mo, d, h=0):
    return datetime(y, mo, d, h, tzinfo=UTC).timestamp()


def _cfg():
    return Config(downloads_dir=Path("dl"), proxy_username=None, proxy_password=None,
                  cookies_browser=None, whisper_model="small", whisper_device="cpu",
                  whisper_compute_type="int8", openrouter_api_key=None, openrouter_model="openai/gpt-4o-mini",
                  store_path=Path("lance"), embedding_backend="local", embedding_model=None,
                  chunk_target_s=45.0, openai_api_key=None)


def _feed(entries):
    """Return a fake extract_fn serving a subscriptions feed of `entries`."""
    def extract_fn(url, flat):
        if url == discovery.FEED_URL:
            return {"entries": entries}
        # per-video fallback keyed by id in the url
        for e in entries:
            if e["id"] in url:
                return e
        return {}
    return extract_fn


def test_discover_filters_by_date_and_stops():
    entries = [
        {"id": "new1", "title": "New", "duration": 600, "channel_id": "c", "upload_date": "20260721"},
        {"id": "new2", "title": "New2", "duration": 600, "channel_id": "c", "upload_date": "20260720"},
        {"id": "old1", "title": "Old", "duration": 600, "channel_id": "c", "upload_date": "20260701"},
        {"id": "old2", "title": "Older", "duration": 600, "channel_id": "c", "upload_date": "20260601"},
    ]
    out = discovery.discover(_cfg(), after="2026-07-15", extract_fn=_feed(entries))
    ids = [v.video_id for v in out]
    assert ids == ["new1", "new2"]  # stops at first older-than-cutoff
    assert out[0].status == "discovered"
    assert out[0].published_at == "2026-07-21"
    assert out[0].channel_id == "c"


def test_discover_drops_short_keeps_live():
    entries = [
        {"id": "short", "title": "S", "duration": 30, "channel_id": "c", "upload_date": "20260721"},
        {"id": "live", "title": "L", "duration": None, "channel_id": "c", "upload_date": "20260721"},
        {"id": "long", "title": "Lo", "duration": 300, "channel_id": "c", "upload_date": "20260721"},
    ]
    out = discovery.discover(_cfg(), after="2026-07-01", min_duration=120, extract_fn=_feed(entries))
    ids = [v.video_id for v in out]
    assert "short" not in ids
    assert "live" in ids and "long" in ids


def test_discover_uses_timestamp_then_fallback():
    # entry with neither date field triggers a per-video fallback lookup
    entries = [{"id": "vid", "title": "T", "duration": 600, "channel_id": "c"}]
    def extract_fn(url, flat):
        if url == discovery.FEED_URL:
            return {"entries": entries}
        return {"id": "vid", "upload_date": "20260721"}  # fallback provides the date
    out = discovery.discover(_cfg(), after="2026-07-01", extract_fn=extract_fn)
    assert out and out[0].published_at == "2026-07-21"


def test_discover_survives_fallback_extract_raising():
    # entry with no date fields; the per-video fallback lookup raises (e.g. a
    # private/deleted/geo-blocked video). discover() must not propagate the
    # exception, and the entry must still be kept (unresolved date -> None).
    entries = [{"id": "vid", "title": "T", "duration": 600, "channel_id": "c"}]
    def extract_fn(url, flat):
        if url == discovery.FEED_URL:
            return {"entries": entries}
        raise RuntimeError("video unavailable")
    out = discovery.discover(_cfg(), after="2026-07-01", extract_fn=extract_fn)
    assert [v.video_id for v in out] == ["vid"]
    assert out[0].published_at is None


def test_discover_uses_inline_timestamp_without_fallback():
    # approximate_date puts an epoch `timestamp` on each flat entry, so discover
    # resolves the date inline and never calls the per-video fallback.
    entries = [{"id": "vid", "title": "T", "duration": 600, "channel_id": "c",
                "timestamp": _epoch(2026, 7, 21, 14)}]
    def extract_fn(url, flat):
        if url == discovery.FEED_URL:
            return {"entries": entries}
        raise AssertionError("inline timestamp present → no per-video fallback")
    out = discovery.discover(_cfg(), after="2026-07-01", extract_fn=extract_fn)
    assert out and out[0].published_at == "2026-07-21"
    assert out[0].published_ts == _epoch(2026, 7, 21, 14)  # epoch carried through


def test_discover_overlap_keeps_boundary_video():
    # after_ts cutoff = start of 2026-07-23; a video timestamped 23:30 the prior
    # day would be dropped by an exact cutoff, but the 1h overlap keeps it.
    cutoff = _epoch(2026, 7, 23)
    entries = [{"id": "boundary", "title": "B", "duration": 600, "channel_id": "c",
                "timestamp": _epoch(2026, 7, 22, 23)}]  # 23:00 prev day
    out = discovery.discover(_cfg(), after_ts=cutoff, overlap_s=3600,
                             extract_fn=_feed(entries))
    assert [v.video_id for v in out] == ["boundary"]
    # …and without the overlap it is correctly excluded (breaks newest-first).
    out2 = discovery.discover(_cfg(), after_ts=cutoff, overlap_s=0,
                              extract_fn=_feed(entries))
    assert out2 == []


def test_run_with_timeout_returns_fast_result():
    assert discovery._run_with_timeout(lambda: 42, 1.0) == 42


def test_run_with_timeout_raises_on_slow():
    with pytest.raises(discovery.DiscoverTimeout):
        discovery._run_with_timeout(lambda: time.sleep(0.5), 0.05)


def test_run_with_timeout_propagates_inner_error():
    def boom():
        raise ValueError("nope")
    with pytest.raises(ValueError):
        discovery._run_with_timeout(boom, 1.0)


def test_discover_times_out_on_hanging_extract():
    # a hanging feed extraction (e.g. blocked on a Chrome Keychain prompt) → DiscoverTimeout
    def hang(url, flat):
        time.sleep(0.5)
        return {}
    with pytest.raises(discovery.DiscoverTimeout):
        discovery.discover(_cfg(), after="2026-07-01", extract_fn=hang, timeout_s=0.05)


def test_channel_uploads_url_normalizes():
    from yt_mem_ai import discovery as d
    assert d._channel_uploads_url("https://youtube.com/@chan") == "https://youtube.com/@chan/videos"
    assert d._channel_uploads_url("https://youtube.com/@chan/") == "https://youtube.com/@chan/videos"
    assert d._channel_uploads_url("https://youtube.com/@chan/videos") == "https://youtube.com/@chan/videos"
    assert d._channel_uploads_url("https://youtube.com/channel/UC123/streams") == "https://youtube.com/channel/UC123/streams"


def test_channel_videos_maps_caps_and_filters():
    from yt_mem_ai import discovery as d
    from yt_mem_ai.config import Config
    from pathlib import Path
    cfg = Config(downloads_dir=Path("d"), proxy_username=None, proxy_password=None,
                 cookies_browser=None, whisper_model="s", whisper_device="cpu",
                 whisper_compute_type="int8", openrouter_api_key=None, openrouter_model="m",
                 store_path=Path("s"), embedding_backend="local", embedding_model=None,
                 chunk_target_s=45.0, openai_api_key=None)
    # newest-first fake channel: 3 entries with epoch timestamps
    entries = [
        {"id": "v3", "title": "Newest", "timestamp": 1753500000, "duration": 600},
        {"id": "v2", "title": "Middle",  "timestamp": 1753400000, "duration": 600},
        {"id": "v1", "title": "Oldest",  "timestamp": 1753300000, "duration": 600},
    ]

    def fake_extract(url, flat):
        assert url.endswith("/videos")   # normalized
        return {"entries": entries}

    got = d.channel_videos(cfg, "https://youtube.com/@chan", limit=2, extract_fn=fake_extract)
    assert [v.video_id for v in got] == ["v3", "v2"]            # newest-first, capped at 2
    assert got[0].title == "Newest" and got[0].url.endswith("v3")
    assert got[0].published_at is not None                       # date derived from timestamp

    # date filter (published_at strings)
    d3 = d.channel_videos(cfg, "https://youtube.com/@chan", limit=10,
                          after=got[0].published_at, before=got[0].published_at,
                          extract_fn=fake_extract)
    assert all(v.published_at == got[0].published_at for v in d3)

    # filter-then-cap: matching the OLDEST video with a small limit must still
    # return it (a naive cap-before-filter would slice it off and return []).
    v1 = d.channel_videos(cfg, "https://youtube.com/@chan", limit=10, extract_fn=fake_extract)[-1]
    oldest = d.channel_videos(cfg, "https://youtube.com/@chan", limit=1,
                              after=v1.published_at, before=v1.published_at,
                              extract_fn=fake_extract)
    assert [v.video_id for v in oldest] == ["v1"]
