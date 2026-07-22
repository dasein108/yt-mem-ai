# SP2 — Daily Digest Design

**Date:** 2026-07-22
**Status:** Approved (brainstorming complete)
**Builds on:** SP0 (fetch pipeline) + SP0.5 (LanceDB + search) + SP1 (discover).

## Vision

Turn a day's discovered subscription videos into a consumable digest: batch-fetch
them (download + transcribe + embed), then produce per-video summaries/highlights/Q&A
and a combined dated digest — separating heavy IO (CLI) from intelligence (a Claude
Code skill), per the project's skills-primary decision.

## Locked Decisions

| Concern | Choice |
|---|---|
| Structure | Batch-fetch CLI command + a `daily-digest` skill (heavy IO vs intelligence) |
| Batch selection | `status="discovered"` videos, `published_at >= --since` (default today), optional `--limit N` |
| Batch robustness | continue-on-error — one failing video is logged + skipped, never aborts; per-video outcome summary at the end |
| Skill input | `yt-ai list --status transcribed --since DATE --json` |
| Per-video output | `summaries` table via existing `save-summary` |
| Combined digest | dated markdown file `digests/YYYY-MM-DD.md` (`digests/` gitignored) |
| Summarization | skills-primary (no OpenRouter path) |

## Architecture

```
yt_summary/
  store/db.py    + list_videos_by_status(db, status, since=None, limit=None) -> list[Video]
  cli.py         + list command + run_list; + fetch-pending command + run_fetch_pending
skills/
  daily-digest/SKILL.md   NEW
.gitignore       + digests/
```

### store/db.py

`list_videos_by_status(db, status, since=None, limit=None) -> list[Video]`:
- Filter `videos` where `status == status` and (`since is None` or `published_at >= since`).
- Sort by `published_at` descending; apply `limit` if given.
- Implemented via `to_list()` + Python filter/sort (tables are small, single-user).

### cli.py

`run_list(cfg, status=None, since=None, db=None) -> list[Video]`:
- If `status` given, `list_videos_by_status(db, status, since)`; else all videos (`list_videos`) filtered by `since`.

`list` command: `--status`, `--since`, `--json`. Human = table (published · status · title · url); `--json` = list of `{video_id, title, url, status, published_at, duration_s}`.

`run_fetch_pending(cfg, since=None, limit=None, db=None) -> list[tuple[str, str]]`:
- `since = since or date.today().isoformat()`.
- `pending = list_videos_by_status(db, "discovered", since=since, limit=limit)`.
- For each: `try: run_fetch(v.url, cfg, db=db, video_id=v.video_id); outcome="ok"` (run_fetch already skips already-seen) `except Exception as e: outcome=f"failed: {e}"`. Collect `(video_id, outcome)`.
- Return the outcomes list (no state mutation beyond what run_fetch does).

`fetch-pending` command: `--since`, `--limit`. Prints per-video outcome + a summary (`N ok / M failed`).

### daily-digest skill (`skills/daily-digest/SKILL.md`)

Inputs: optional `--since` date (default today).
Steps:
1. `yt-ai list --status transcribed --since <DATE> --json` → the videos to digest. If empty, tell the user to run `fetch-pending` first and stop.
2. For each video: `yt-ai show <id> --json` (metadata + transcript); anchor highlights via `yt-ai search "<phrase>" --vector -k 3`; produce summary/highlights/Q&A; persist with `yt-ai save-summary <id> "<md>" '<highlights>' '<qa>'`.
3. Compose `digests/<DATE>.md`: a top executive digest (what happened across the day, cross-video themes) + one section per video (title, link, 2–4 sentence summary, top highlights as `MM:SS — label`, 2–3 Q&A).
4. Report the digest path + the executive summary in chat.
Notes: everything grounded in transcripts; highlight timestamps come from `yt-ai search`, never invented.

### Data Flow

```
discover  → status=discovered
  └─ fetch-pending --since DATE  → run_fetch each (continue-on-error) → status=transcribed
       └─ daily-digest skill: list transcribed --since DATE
            → per video: show + search + save-summary
            → digests/DATE.md (executive + per-video)
```

### Error Handling

- `fetch-pending`: per-video `try/except` — private/members/deleted/geo-blocked/whisper failures are captured as `failed: <msg>` and the batch continues. `run_fetch`'s own resumability (status-based `is_seen`) means re-running retries only the not-yet-transcribed ones.
- `list`/`run_list`: empty result prints a clear "no videos" message.
- The skill halts with guidance if `list` returns empty (nothing fetched yet).

### Testing

- `list_videos_by_status`: status filter + `since` lower-bound + `limit` + ordering (temp-dir LanceDB, fake embedder).
- `run_list`: status vs all, `since` filtering, `--json` shape (via the command or core).
- `run_fetch_pending`: monkeypatch `cli.run_fetch` to return normally for some ids and raise for others → assert continue-on-error, the full outcome list (ok/failed), and that `--limit`/`--since` bound the selection. Offline (no real fetch).
- No automated test of the skill (Claude-Code-driven) or of a real batch fetch (network/whisper) — manual smoke only.

## Documentation Updates

- README: add `list` + `fetch-pending` to the command list; extend the daily-routine note to the 3-step flow (discover → fetch-pending → daily-digest).
- `.gitignore`: add `digests/`.
- Roadmap memory: mark SP2 done.

## Out of Scope

- Scheduling/cron (user runs the three steps or wraps them).
- OpenRouter/automated summarization (digest is skills-primary).
- Cross-day digest dedup / "already digested" tracking (re-running overwrites summaries idempotently and rewrites the dated file).
- Recommendations (SP3), frontend (SP4), compilation (SP5).
