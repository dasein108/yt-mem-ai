import os
import lancedb
import pytest
from yt_mem_ai.config import Config
from yt_mem_ai.store import db as store
from yt_mem_ai.store.embeddings import build_embedder

pytestmark = pytest.mark.skipif(
    os.environ.get("YT_RUN_INTEGRATION") != "1",
    reason="set YT_RUN_INTEGRATION=1 to run (downloads a real embedding model)",
)


def _cfg(tmp_path):
    return Config(downloads_dir=tmp_path / "dl", proxy_username=None, proxy_password=None,
                  cookies_browser=None, whisper_model="small", whisper_device="cpu",
                  whisper_compute_type="int8", openrouter_api_key=None, openrouter_model="openai/gpt-4o-mini",
                  store_path=tmp_path / "lance", embedding_backend="local",
                  embedding_model=None, chunk_target_s=45.0, openai_api_key=None)


def test_real_embeddings_hybrid_search(tmp_path):
    cfg = _cfg(tmp_path)
    db = lancedb.connect(str(cfg.store_path))
    store.init_db(db, build_embedder(cfg))
    store.replace_chunks(db, "v1", [
        {"id": "v1:0", "video_id": "v1", "start_s": 0.0, "end_s": 10.0,
         "text": "how to optimize database queries with indexes"},
        {"id": "v1:1", "video_id": "v1", "start_s": 10.0, "end_s": 20.0,
         "text": "training a neural network on GPUs"},
    ])
    hits = store.search_chunks(db, "speed up SQL lookups", k=1, mode="vector")
    assert hits and hits[0]["video_id"] == "v1" and hits[0]["start_s"] == 0.0
