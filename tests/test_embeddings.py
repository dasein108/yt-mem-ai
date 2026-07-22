import pytest
from pathlib import Path
from yt_summary.config import Config
from yt_summary.store.models import Segment
from yt_summary.store import embeddings


def _cfg(**over):
    base = dict(downloads_dir=Path("dl"), proxy_username=None,
                proxy_password=None, cookies_browser=None, whisper_model="small",
                whisper_device="cpu", whisper_compute_type="int8", openrouter_api_key=None,
                store_path=Path("s"), embedding_backend="local", embedding_model=None,
                chunk_target_s=45.0, openai_api_key=None)
    base.update(over)
    return Config(**base)


def test_chunk_segments_merges_into_windows():
    segs = [Segment("v", i * 10.0, i * 10.0 + 10.0, f"s{i}") for i in range(6)]  # 0..60s
    chunks = embeddings.chunk_segments("v", segs, target_s=25.0)
    # windows accumulate until >= 25s span, so ~3 chunks of 3 segments (0-30) etc.
    assert len(chunks) >= 2
    assert chunks[0]["video_id"] == "v"
    assert chunks[0]["start_s"] == 0.0
    assert chunks[0]["text"].startswith("s0")
    assert all(c["id"].startswith("v:") for c in chunks)
    # spans are contiguous and cover all text
    assert chunks[-1]["end_s"] == 60.0


def test_chunk_segments_empty():
    assert embeddings.chunk_segments("v", [], 45.0) == []


def test_build_embedder_unknown_backend():
    with pytest.raises(ValueError):
        embeddings.build_embedder(_cfg(embedding_backend="nope"))


def test_build_embedder_openai_requires_key():
    with pytest.raises(ValueError):
        embeddings.build_embedder(_cfg(embedding_backend="openai", openai_api_key=None))
