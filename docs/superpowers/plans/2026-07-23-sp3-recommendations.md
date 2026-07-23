# SP3 Recommendations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `like`/`dislike` feedback and a `recommend` command that ranks the user's unrated fetched videos by a taste centroid (`cos(v, like) − cos(v, dislike)`) over the existing chunk embeddings.

**Architecture:** A `list_feedback` store read + a pure-function `recommend.py` (latest-signal-wins, mean vector, cosine, candidate scoring) orchestrated into `recommend(db, limit)`. The CLI adds `like`/`dislike`/`recommend` over thin testable cores. Vector math uses `numpy`. Tests are offline: the deterministic `FakeEmbedder` gives identical vectors for identical text, so ranking mechanics are verified deterministically.

**Tech Stack:** Python 3.11+, LanceDB, numpy, Typer, pytest, uv.

## Global Constraints

- Python 3.11+, `X | None` unions. uv; console script `yt-ai`.
- Store handle is `db`; reuse `store` (`yt_summary.store.db`) — `list_chunks` (returns rows including `vector`), `list_videos_by_status`, `insert_feedback`, `get_video`, `open_store`.
- Latest-signal-wins: for each `video_id`, the `feedback` row with the greatest `created_at` determines the current signal.
- Centroid weighting: per-video mean of chunk vectors first, then average across videos (equal weight per video).
- Candidate pool: status `transcribed` or `summarized`, not in the feedback set, and having at least one chunk vector.
- Cold start (no likes AND no dislikes): rank candidates by `published_at` desc (score `0.0`).
- `cosine` returns `0.0` on a zero-norm vector (no division by zero). A missing centroid contributes `0` to the score.
- Offline tests only: temp-dir LanceDB + registered `FakeEmbedder`; exploit identical-text→identical-vector. No network, no model download.
- Every task ends green (`uv run pytest -q`), `uv run --with ruff ruff check .` clean, `-W error::DeprecationWarning` clean, and is committed.

---

## File Structure

```
yt_summary/
  store/db.py    + list_feedback(db) -> list[dict]
  recommend.py   NEW: latest_signals, mean_vector, cosine, video_mean_vector, score_candidates, recommend
  cli.py         + like / dislike / recommend commands + run_feedback + run_recommend
pyproject.toml   + numpy
tests/
  test_db.py         + list_feedback test
  test_recommend.py  NEW: pure helpers + recommend orchestration
  test_cli.py        + like/dislike/recommend command tests
```

---

## Task 1: Store — list_feedback + numpy dependency

**Files:**
- Modify: `pyproject.toml` (+ `numpy`), `yt_summary/store/db.py` (append)
- Test: `tests/test_db.py` (append)

**Interfaces:**
- Produces: `list_feedback(db) -> list[dict]` — all `feedback` rows (`video_id`, `signal`, `created_at`).

- [ ] **Step 1: Add `numpy` to `pyproject.toml`**

In `[project].dependencies`, add (after `"openai>=1.40",`):
```toml
    "numpy>=1.26",
```

- [ ] **Step 2: Write the failing test (append to `tests/test_db.py`)**

```python
def test_list_feedback_returns_rows(tmp_path):
    conn = _db(tmp_path)
    store.insert_feedback(conn, "v1", 1, "2026-07-23T00:00:00+00:00")
    store.insert_feedback(conn, "v1", -1, "2026-07-23T01:00:00+00:00")
    store.insert_feedback(conn, "v2", 1, "2026-07-23T00:00:00+00:00")
    rows = store.list_feedback(conn)
    assert len(rows) == 3
    assert {r["signal"] for r in rows if r["video_id"] == "v1"} == {1, -1}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_db.py -q`
Expected: FAIL (`AttributeError: list_feedback`)

- [ ] **Step 4: Append to `yt_summary/store/db.py`**

```python
def list_feedback(db) -> list[dict]:
    tbl = db.open_table("feedback")
    return tbl.search().limit(1_000_000).to_list()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_db.py -q`
Expected: PASS (numpy installs on first `uv run`).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml yt_summary/store/db.py tests/test_db.py uv.lock
git commit -m "feat: list_feedback + numpy dep"
```

---

## Task 2: recommend.py — taste-centroid ranking

**Files:**
- Create: `yt_summary/recommend.py`
- Test: `tests/test_recommend.py`

**Interfaces:**
- Consumes: `store.list_feedback`, `store.list_chunks`, `store.list_videos_by_status`.
- Produces:
  - `latest_signals(feedback_rows) -> dict[str, int]`
  - `mean_vector(vectors) -> list[float] | None`
  - `cosine(a, b) -> float`
  - `video_mean_vector(db, video_id) -> list[float] | None`
  - `score_candidates(cand_vecs, like_centroid, dislike_centroid) -> dict[str, float]`
  - `recommend(db, limit=20) -> list[tuple[str, float]]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_recommend.py
import lancedb
from tests.support import fake_embedder
from yt_summary.store import db as store
from yt_summary.store.models import Video
from yt_summary import recommend


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_recommend.py -q`
Expected: FAIL (`ModuleNotFoundError: yt_summary.recommend`)

- [ ] **Step 3: Implement `yt_summary/recommend.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_recommend.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add yt_summary/recommend.py tests/test_recommend.py
git commit -m "feat: taste-centroid recommendation engine"
```

---

## Task 3: CLI — like / dislike / recommend

**Files:**
- Modify: `yt_summary/cli.py`
- Test: `tests/test_cli.py` (append)

**Interfaces:**
- Produces:
  - `run_feedback(cfg, video_id, signal, db=None) -> None`
  - `run_recommend(cfg, limit=20, db=None) -> list[tuple[str, float]]`
  - `like`, `dislike`, `recommend` Typer commands.

- [ ] **Step 1: Write the failing test (append to `tests/test_cli.py`)**

```python
def test_run_feedback_writes_signal(tmp_path):
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)
    cli.run_feedback(cfg, "v1", 1, db=conn)
    cli.run_feedback(cfg, "v1", -1, db=conn)
    rows = store.list_feedback(conn)
    assert len(rows) == 2
    assert {r["signal"] for r in rows} == {1, -1}


def test_run_recommend_returns_ranked(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)
    monkeypatch.setattr(cli, "recommend_videos",
                        lambda db, limit=20: [("v2", 0.9), ("v1", 0.1)])
    ranked = cli.run_recommend(cfg, limit=20, db=conn)
    assert ranked == [("v2", 0.9), ("v1", 0.1)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -q`
Expected: FAIL (`AttributeError: run_feedback` / `recommend_videos`)

- [ ] **Step 3: Add to `yt_summary/cli.py`**

Add the import near the others:
```python
from .recommend import recommend as recommend_videos
```

Add cores + commands:
```python
def run_feedback(cfg, video_id: str, signal: int, db=None) -> None:
    if db is None:
        db = open_store(cfg)
    store.insert_feedback(db, video_id, signal, datetime.now(UTC).isoformat())


def run_recommend(cfg, limit: int = 20, db=None) -> list[tuple[str, float]]:
    if db is None:
        db = open_store(cfg)
    return recommend_videos(db, limit=limit)


@app.command()
def like(video_id: str):
    """Mark a video as liked (feeds recommendations)."""
    cfg = load_config()
    run_feedback(cfg, video_id, 1)
    typer.echo(f"liked {video_id}")


@app.command()
def dislike(video_id: str):
    """Mark a video as disliked (feeds recommendations)."""
    cfg = load_config()
    run_feedback(cfg, video_id, -1)
    typer.echo(f"disliked {video_id}")


@app.command()
def recommend(limit: int = typer.Option(20, "--limit"),
              as_json: bool = typer.Option(False, "--json")):
    """Rank your unrated fetched videos by learned taste."""
    cfg = load_config()
    db = open_store(cfg)
    ranked = run_recommend(cfg, limit=limit, db=db)
    if not ranked:
        typer.echo("no candidates — fetch and rate some videos first")
        return
    rows = [(store.get_video(db, vid), score) for vid, score in ranked]
    if as_json:
        typer.echo(json.dumps([
            {"video_id": v.video_id, "title": v.title, "url": v.url,
             "published_at": v.published_at, "score": round(score, 4)}
            for v, score in rows if v is not None]))
        return
    for v, score in rows:
        if v is None:
            continue
        typer.echo(f"{score:+.3f}  {v.published_at or '????-??-??'}  {(v.title or '')[:50]:50}  {v.url}")
```

Note: the command function `recommend` and the imported engine aliased as
`recommend_videos` do not clash. `run_recommend` calls `recommend_videos` (module-level
name so tests can monkeypatch `cli.recommend_videos`).

- [ ] **Step 4: Run tests + smoke**

Run: `uv run pytest tests/test_cli.py -q` → PASS
Run: `uv run pytest -q` → full suite PASS; `-W error::DeprecationWarning` clean.
Run: `uv run yt-ai --help` → confirm `like`/`dislike`/`recommend` listed. Report output.

- [ ] **Step 5: Commit**

```bash
git add yt_summary/cli.py tests/test_cli.py
git commit -m "feat: yt-ai like/dislike/recommend commands"
```

---

## Task 4: Documentation + final sweep

**Files:**
- Modify: `README.md`, `CLAUDE.md`

**Interfaces:** none (docs).

- [ ] **Step 1: Update `README.md`**

Add to the Commands block:
```markdown
yt-ai like <video_id>        # mark liked (feeds recommendations)
yt-ai dislike <video_id>     # mark disliked
yt-ai recommend              # rank your unrated fetched videos by taste (--limit/--json)
```
And a note:
```markdown
## Rate & recommend

Like/dislike videos you've fetched (`yt-ai like <id>` / `dislike <id>`), then
`yt-ai recommend` ranks your other fetched-but-unrated videos by similarity to
what you liked (minus what you disliked), using their transcript embeddings.
Before you've liked anything, it falls back to most-recently-published.
```

- [ ] **Step 2: Update `CLAUDE.md`**

- Add to the module map: `recommend.py — taste-centroid ranking over chunk embeddings (like − dislike)`.
- Add a line under Skills/commands or a new "Recommendations" note: `like`/`dislike` write the
  `feedback` table (latest signal per video wins); `recommend` builds like/dislike centroids from
  liked/disliked videos' chunk vectors and ranks unrated transcribed/summarized videos.

- [ ] **Step 3: Final sweep**

Run: `uv run pytest -q` → all PASS (+1 skipped integration). Report count.
Run: `uv run --with ruff ruff check .` → clean.
Run: `uv run yt-ai recommend --help` → shows `--limit/--json`. Report output.

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: document like/dislike/recommend"
```

- [ ] **Step 5: Report roadmap-memory update to the controller**

Report that the roadmap memory (`sp-roadmap-and-stack`) should mark SP3 done: `like`/`dislike`/
`recommend` commands + `recommend.py` (taste centroid like − dislike over chunk embeddings,
cold-start by recency); scores fetched-but-unrated videos only.

---

## Self-Review Notes

- **Spec coverage:** `like`/`dislike` feedback (T3), taste-centroid scoring `cos(like) − cos(dislike)` with per-video-equal-weight centroids (T2), candidate pool transcribed/summarized-unrated-with-chunks (T2 `recommend`), latest-signal-wins (T2 `latest_signals`), cold-start-by-recency (T2), `numpy` dep (T1), zero-norm-safe cosine (T2), docs incl. CLAUDE.md (T4). Out-of-scope items (unfetched scoring, decay, diversity) intentionally absent.
- **Placeholder scan:** none — every code step is complete.
- **Type/name consistency:** `recommend(db, limit)` matches `run_recommend`'s `recommend_videos(db, limit=limit)` call; `latest_signals`/`mean_vector`/`cosine`/`score_candidates` signatures match their tests; `list_feedback`/`list_chunks`/`list_videos_by_status`/`insert_feedback`/`get_video` are existing store functions. `video_mean_vector` relies on `list_chunks` returning the `vector` column (it does — only `search_chunks` strips it). Command `recommend` vs imported engine alias `recommend_videos` avoids the name clash and keeps the monkeypatch seam.
- **Fake-embedder test strategy:** ranking asserted via identical-text→identical-vector (cosine 1) rather than semantic similarity, so results are deterministic offline.
