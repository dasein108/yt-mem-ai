# tests/test_discovery.py
from pathlib import Path
from yt_summary.config import Config
from yt_summary import discovery


def _cfg():
    return Config(downloads_dir=Path("dl"), proxy_username=None, proxy_password=None,
                  cookies_browser=None, whisper_model="small", whisper_device="cpu",
                  whisper_compute_type="int8", openrouter_api_key=None,
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
