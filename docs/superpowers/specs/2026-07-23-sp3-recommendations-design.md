# SP3 — Recommendations Design

**Date:** 2026-07-23
**Status:** Approved (brainstorming complete)
**Builds on:** SP0.5 (chunk embeddings) + the existing `feedback` table.

## Vision

Let the user like/dislike videos, then rank their unrated fetched videos by how
well they match that taste — using the per-chunk embeddings that already exist.
This is the "shrunk" SP3: the storage/embeddings/search infrastructure was built
in SP0.5, so this adds only feedback commands + a small ranking module.

## Locked Decisions

| Concern | Choice |
|---|---|
| Feedback entry | `yt-ai like <video_id>` / `yt-ai dislike <video_id>` (signal +1/−1) |
| Re-rating | append to `feedback`; latest signal per video wins (history kept) |
| Scoring | taste centroid: `cos(v, like_centroid) − cos(v, dislike_centroid)` |
| Centroid weighting | per-video mean first, then average across videos (equal weight per video) |
| Candidate pool | status `transcribed`/`summarized`, unrated, having chunks |
| Cold start (no likes) | fall back to ranking candidates by `published_at` desc |
| Vector math | `numpy` (added as an explicit dependency) |

## Scope

Recommendations rank videos that already have embeddings (i.e. the user has
fetched/transcribed them) and hasn't rated — answering "of what I've pulled, what
best matches my taste, so I know what to watch." Discovered-but-unfetched videos
have no vectors and are out of scope for scoring.

## Architecture

```
yt_summary/
  store/db.py    + list_feedback(db) -> list[dict]
  recommend.py   NEW: latest_signals, mean_vector, cosine, score_candidates, recommend
  cli.py         + like / dislike / recommend commands + run_recommend
pyproject.toml   + numpy
```

### store/db.py

`list_feedback(db) -> list[dict]` — all `feedback` rows (`video_id`, `signal`, `created_at`).
Reuse existing `list_chunks` (returns rows including `vector`) and
`list_videos_by_status` for candidates; reuse `insert_feedback` for writes.

### recommend.py (pure helpers + orchestrator)

- `latest_signals(feedback_rows) -> dict[str, int]` — for each `video_id`, the
  `signal` of the row with the greatest `created_at` (latest wins).
- `mean_vector(vectors: list[list[float]]) -> list[float] | None` — element-wise
  mean; `None` for empty input. (numpy.)
- `cosine(a, b) -> float` — cosine similarity; `0.0` if either norm is 0.
- `video_mean_vector(db, video_id) -> list[float] | None` — mean of the video's
  chunk vectors (via `list_chunks`); `None` if it has no chunks.
- `score_candidates(cand_vecs, like_centroid, dislike_centroid) -> dict[str,float]`
  — pure scoring given precomputed vectors; missing centroid → that term contributes 0.
- `recommend(db, limit=20) -> list[tuple[str, float]]` — orchestrates:
  1. `signals = latest_signals(list_feedback(db))`.
  2. `liked = [vid for vid, s in signals.items() if s > 0]`; `disliked` (s < 0).
  3. `like_centroid = mean_vector([video_mean_vector(db, v) for v in liked if ...])`
     (skip videos with no chunks); same for `dislike_centroid`.
  4. candidates = `list_videos_by_status(transcribed) + list_videos_by_status(summarized)`,
     excluding any `video_id` in `signals`; keep only those with a `video_mean_vector`.
  5. If `not liked and not disliked` → cold start: return candidates sorted by
     `published_at` desc (score `0.0`), limited.
  6. Else score each candidate = `cos(mean, like_centroid) − cos(mean, dislike_centroid)`;
     sort desc; apply `limit`.

### cli.py

- `like` / `dislike` commands: `insert_feedback(db, video_id, +1|-1, datetime.now(UTC).isoformat())`;
  echo confirmation. Testable cores `run_like`/`run_dislike` (or one `run_feedback(cfg, video_id, signal, db=None)`).
- `recommend` command: `--limit 20`, `--json`. Human = table (score · published · title · url);
  `--json` = `[{video_id, title, url, published_at, score}]`. Testable `run_recommend(cfg, limit=20, db=None) -> list[tuple[str,float]]`.
- If `recommend` returns empty → print "no candidates — fetch and rate some videos first".

### Data Flow

```
yt-ai like <id> / dislike <id>   → feedback rows
yt-ai recommend
  → latest_signals → like/dislike centroids (per-video mean of chunk vectors)
  → candidates (transcribed/summarized, unrated, with chunks)
  → score = cos(cand, like) − cos(cand, dislike)  [or cold-start: by published_at]
  → ranked table / --json
```

### Error Handling

- `like`/`dislike` on an unknown `video_id`: still records the feedback (the video may
  be fetched later); no hard failure. (Feedback is keyed on `video_id` text.)
- `recommend` with no candidates (nothing fetched, or all rated): clear message, empty list.
- Degenerate vectors (zero norm): `cosine` returns `0.0` rather than dividing by zero.

### Testing (offline)

The `FakeEmbedder` is deterministic but hash-based (not semantic), so tests exploit
**identical text → identical vector**:
- Pure helpers: `latest_signals` (like-then-dislike → disliked; latest wins), `cosine`
  (orthogonal → 0, identical → 1, zero-norm → 0), `mean_vector` (empty → None).
- `run_recommend` (temp-dir LanceDB + fake embedder):
  - Seed liked video L and candidate C1 with the SAME chunk text (→ same vector), and C2
    with different text. Like L → assert C1 outranks C2.
  - Dislike a video whose text matches candidate C2 → assert C2's score drops below C1.
  - Cold start: no feedback → candidates returned ordered by `published_at` desc.
  - Rated videos are excluded from candidates.
- `like`/`dislike` commands write the expected `feedback` signal.

## Documentation Updates

- README: add `like` / `dislike` / `recommend` to the command list + a "rate & recommend" note.
- `CLAUDE.md`: add the feedback → recommend flow and `recommend.py` to the module map.
- Roadmap memory: mark SP3 done.

## Out of Scope

- Recommending unfetched/discovered videos (no embeddings; would need pre-fetch metadata scoring).
- Time-decay / recency weighting of feedback (latest-signal-wins is the only recency rule).
- Diversity/MMR re-ranking, multi-taste clustering (single centroid pair).
- Frontend (SP4), compilation (SP5).
