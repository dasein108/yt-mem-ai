# yt_summary/recommend.py
from __future__ import annotations
import numpy as np
from .store import db as store


def latest_signals(feedback_rows: list[dict]) -> dict[str, int]:
    latest: dict[str, tuple[str, int]] = {}
    for row in feedback_rows:
        vid = row["video_id"]
        ts = row.get("created_at") or ""
        if vid not in latest or ts >= latest[vid][0]:
            latest[vid] = (ts, int(row["signal"]))
    return {vid: sig for vid, (_, sig) in latest.items()}


def mean_vector(vectors: list[list[float]]) -> list[float] | None:
    if not vectors:
        return None
    return np.mean(np.array(vectors, dtype=float), axis=0).tolist()


def cosine(a, b) -> float:
    va = np.array(a, dtype=float)
    vb = np.array(b, dtype=float)
    na = float(np.linalg.norm(va))
    nb = float(np.linalg.norm(vb))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


def video_mean_vector(db, video_id: str) -> list[float] | None:
    chunks = store.list_chunks(db, video_id)
    vecs = [c["vector"] for c in chunks if c.get("vector") is not None]
    return mean_vector(vecs)


def score_candidates(cand_vecs: dict[str, list], like_centroid, dislike_centroid) -> dict[str, float]:
    scores: dict[str, float] = {}
    for vid, vec in cand_vecs.items():
        s = 0.0
        if like_centroid is not None:
            s += cosine(vec, like_centroid)
        if dislike_centroid is not None:
            s -= cosine(vec, dislike_centroid)
        scores[vid] = s
    return scores


def _centroid(db, video_ids: list[str]) -> list[float] | None:
    means = [mv for vid in video_ids if (mv := video_mean_vector(db, vid)) is not None]
    return mean_vector(means)


def recommend(db, limit: int = 20) -> list[tuple[str, float]]:
    signals = latest_signals(store.list_feedback(db))
    liked = [v for v, s in signals.items() if s > 0]
    disliked = [v for v, s in signals.items() if s < 0]
    like_centroid = _centroid(db, liked)
    dislike_centroid = _centroid(db, disliked)

    candidates = store.list_videos_by_status(db, "transcribed") \
        + store.list_videos_by_status(db, "summarized")
    published = {v.video_id: (v.published_at or "") for v in candidates}
    cand_vecs: dict[str, list] = {}
    for v in candidates:
        if v.video_id in signals:
            continue
        mv = video_mean_vector(db, v.video_id)
        if mv is not None:
            cand_vecs[v.video_id] = mv

    if not liked and not disliked:
        ranked_ids = sorted(cand_vecs.keys(),
                            key=lambda vid: published.get(vid, ""), reverse=True)
        return [(vid, 0.0) for vid in ranked_ids[:limit]]

    scores = score_candidates(cand_vecs, like_centroid, dislike_centroid)
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return ranked[:limit]
