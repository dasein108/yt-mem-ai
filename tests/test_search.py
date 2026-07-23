import lancedb
from tests.support import fake_embedder
from yt_summary.config import Config
from yt_summary import cli
from yt_summary.store import db as store


def _db(tmp_path):
    conn = lancedb.connect(str(tmp_path / "lance"))
    store.init_db(conn, fake_embedder())
    return conn


def _seed(conn):
    rows = [
        {"id": "v1:0", "video_id": "v1", "start_s": 0.0, "end_s": 10.0, "text": "python async programming"},
        {"id": "v1:1", "video_id": "v1", "start_s": 10.0, "end_s": 20.0, "text": "database indexing strategies"},
        {"id": "v2:0", "video_id": "v2", "start_s": 0.0, "end_s": 10.0, "text": "machine learning models"},
    ]
    store.replace_chunks(conn, "v1", rows[:2])
    store.replace_chunks(conn, "v2", rows[2:])


def test_vector_search_returns_hits(tmp_path):
    conn = _db(tmp_path)
    _seed(conn)
    hits = store.search_chunks(conn, "database indexing strategies", k=1, mode="vector")
    assert hits and hits[0]["video_id"] == "v1"
    assert "vector" not in hits[0]
    assert "start_s" in hits[0]


def test_fts_search_finds_keyword(tmp_path):
    conn = _db(tmp_path)
    _seed(conn)
    hits = store.search_chunks(conn, "machine", k=5, mode="fts")
    assert any(h["video_id"] == "v2" for h in hits)


def test_hybrid_search_runs(tmp_path):
    conn = _db(tmp_path)
    _seed(conn)
    hits = store.search_chunks(conn, "python", k=5, mode="hybrid")
    assert isinstance(hits, list)


def _cfg(tmp_path):
    return Config(downloads_dir=tmp_path / "dl", proxy_username=None, proxy_password=None,
                  cookies_browser=None, whisper_model="small", whisper_device="cpu",
                  whisper_compute_type="int8", openrouter_api_key=None, openrouter_model="openai/gpt-4o-mini",
                  store_path=tmp_path / "lance", embedding_backend="local",
                  embedding_model=None, chunk_target_s=45.0, openai_api_key=None)


def test_run_search_returns_hits(tmp_path):
    conn = _db(tmp_path)
    _seed(conn)
    hits = cli.run_search(_cfg(tmp_path), "machine learning models", mode="vector", k=1, db=conn)
    assert hits and hits[0]["video_id"] == "v2"
