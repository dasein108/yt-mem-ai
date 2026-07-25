# tests/test_recommend.py
import lancedb
from tests.support import fake_embedder
from yt_mem_ai.store import db as store
from yt_mem_ai.store.models import Video
from yt_mem_ai import recommend


def _db(tmp_path):
    conn = lancedb.connect(str(tmp_path / "lance"))
    store.init_db(conn, fake_embedder())
    return conn


def _seed(conn, vid, text, status="transcribed", published_at="2026-07-20"):
    store.upsert_video(conn, Video(video_id=vid, url="u", status=status, published_at=published_at))
    store.replace_chunks(conn, vid, [
        {"id": f"{vid}:0", "video_id": vid, "start_s": 0.0, "end_s": 10.0, "text": text}])


# --- pure helpers ---

def test_latest_signals_latest_wins():
    rows = [
        {"video_id": "v1", "signal": 1, "created_at": "2026-07-23T00:00:00+00:00"},
        {"video_id": "v1", "signal": -1, "created_at": "2026-07-23T02:00:00+00:00"},
        {"video_id": "v2", "signal": 1, "created_at": "2026-07-23T00:00:00+00:00"},
    ]
    assert recommend.latest_signals(rows) == {"v1": -1, "v2": 1}


def test_cosine_bounds():
    assert recommend.cosine([1, 0], [1, 0]) == 1.0
    assert recommend.cosine([1, 0], [0, 1]) == 0.0
    assert recommend.cosine([0, 0], [1, 0]) == 0.0  # zero norm safe


def test_mean_vector_empty_none():
    assert recommend.mean_vector([]) is None
    assert recommend.mean_vector([[2.0, 4.0], [4.0, 8.0]]) == [3.0, 6.0]


# --- orchestration ---

def test_recommend_ranks_similar_above_dissimilar(tmp_path):
    conn = _db(tmp_path)
    _seed(conn, "liked", "alpha topic")
    _seed(conn, "cand_same", "alpha topic")     # identical text → identical vector
    _seed(conn, "cand_diff", "zeta unrelated")
    store.insert_feedback(conn, "liked", 1, "2026-07-23T00:00:00+00:00")
    ranked = recommend.recommend(conn, limit=10)
    ids = [vid for vid, _ in ranked]
    assert "liked" not in ids                     # rated → excluded
    assert ids.index("cand_same") < ids.index("cand_diff")


def test_recommend_dislike_penalizes(tmp_path):
    conn = _db(tmp_path)
    _seed(conn, "liked", "alpha topic")
    _seed(conn, "disliked", "zeta unrelated")
    _seed(conn, "cand_like", "alpha topic")
    _seed(conn, "cand_dislike", "zeta unrelated")
    store.insert_feedback(conn, "liked", 1, "2026-07-23T00:00:00+00:00")
    store.insert_feedback(conn, "disliked", -1, "2026-07-23T00:00:00+00:00")
    ranked = dict(recommend.recommend(conn, limit=10))
    assert ranked["cand_like"] > ranked["cand_dislike"]


def test_recommend_cold_start_by_recency(tmp_path):
    conn = _db(tmp_path)
    _seed(conn, "old", "a", published_at="2026-07-01")
    _seed(conn, "new", "b", published_at="2026-07-22")
    ranked = recommend.recommend(conn, limit=10)   # no feedback
    assert [vid for vid, _ in ranked] == ["new", "old"]
