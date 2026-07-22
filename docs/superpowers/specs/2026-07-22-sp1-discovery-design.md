# SP1 — Discovery Design

**Date:** 2026-07-22
**Status:** Approved (brainstorming complete)
**Builds on:** SP0 foundation + SP0.5 LanceDB store.

## Vision

A `yt-ai discover` command that lists new uploads from the user's YouTube
subscriptions published after a cutoff date, storing them as `status="discovered"`
videos (metadata only — no audio/transcription). Designed as a daily routine that
feeds SP0 `fetch` and future SP2 batch digest.

## Locked Decisions

| Concern | Choice |
|---|---|
| Scope | Discover + **list only** (no download/transcribe — that stays `fetch`/SP2) |
| Feed source | yt-dlp on `https://www.youtube.com/feed/subscriptions` (cookies + Webshare proxy); `--deep` enumerates subscribed channels for backfill |
| Cutoff | `--after YYYY-MM-DD` → else stored `last_discover_at` → else **now − 7 days** (first run) |
| Filtering | `--min-duration` (default 120s): drop `duration < min`; keep `None` duration (live/upcoming) |
| Output | Human table by default; `--json` emits the full list (feeds SP2 batch) |
| Dedup | insert-only — never downgrade an already-fetched video's status |
| Store | LanceDB (`app_state` for `last_discover_at`; `videos`/`channels` tables exist) |

## Architecture

```
yt_summary/
  discovery.py   NEW: discover(cfg, after, deep, min_duration, ydl_factory=None) -> list[Video]
  download.py    reuse build_opts(cfg, download_audio=False) for proxy+cookies base
  store/db.py    + upsert_channel(...), insert_discovered_video(...) (insert-only)
  cli.py         + discover command + run_discover(cfg, ..., db=None) -> list[Video]
```

### discovery.py

`discover(cfg, after, deep, min_duration, ydl_factory=None) -> list[Video]`:
- Build yt-dlp opts from `build_opts(cfg, download_audio=False)` (proxy + cookies)
  plus discovery options: non-flat lazy extraction with a date lower-bound and
  break-on-reject, so the newest-first feed stops as soon as it passes the cutoff.
- Source URL: `https://www.youtube.com/feed/subscriptions`. With `deep=True`,
  enumerate the user's subscribed channels and extract each channel's uploads tab.
- Map each playlist entry dict → `Video(status="discovered")` (id, title, url,
  channel_id, duration_s, published_at). Reuse SP0's date-format conversion.
- Apply the duration filter (`duration_s is None or duration_s >= min_duration`).
- `ydl_factory` is injectable (defaults to lazy `yt_dlp.YoutubeDL`) so unit tests
  feed fake entry dicts and never hit the network.

Exact yt-dlp option names for the date lower-bound + break-on-reject
(`daterange`/`DateRange`, `break_on_reject` vs `--break-match-filters`/match_filter)
are grounded against current yt-dlp docs at plan-writing time.

### store/db.py additions

- `upsert_channel(db, channel_id, title, subscribed=1)` — merge_insert on `channel_id`.
- `insert_discovered_video(db, v: Video)` — `merge_insert("video_id").when_not_matched_insert_all().execute([row])` with **no** `when_matched_update_all()`, so an existing row (any status) is left untouched. This is the dedup + no-downgrade guarantee.

### cli.py

`run_discover(cfg, after, deep, min_duration, db=None) -> list[Video]`:
1. Resolve cutoff: `after` → `get_state(db, "last_discover_at")` → `now − 7 days` (ISO date).
2. `videos = discovery.discover(cfg, cutoff, deep, min_duration)`.
3. For each: `upsert_channel(...)`, `insert_discovered_video(...)`.
4. On success: `set_state(db, "last_discover_at", now_iso)`.
5. Return the discovered `Video` list (new + already-known distinguished by pre-checking existence, so the CLI can report N new / M known).

`discover` Typer command: `--after`, `--deep`, `--min-duration 120`, `--json`.
Human output: a table (published · channel · title · duration). `--json`: the full list.

### Data Flow

```
cutoff = --after | last_discover_at | now-7d
  └─ discovery.discover  → yt-dlp feed (proxy+cookies), date-stop, min-duration filter
       └─ per video: upsert_channel(subscribed=1) + insert_discovered_video (insert-only)
           └─ set_state("last_discover_at", now) on success
               └─ print table / --json
```

### Error Handling

- Missing cookies → yt-dlp can't read the authenticated feed → clear error naming the cause; do NOT advance `last_discover_at` (so the next run retries the same window).
- Feed/network failure → surface the error; `last_discover_at` unchanged.
- `--deep` channel enumeration failure on one channel → log and continue with the rest (best-effort backfill).
- Idempotency: re-running the same window re-discovers the same videos, but `insert_discovered_video` is insert-only so no rows change and already-fetched videos keep their status.

### Testing

- Unit (`discovery.discover`, offline via injected fake entries):
  - date-stop respected (entries older than cutoff excluded / extraction stops);
  - min-duration filter drops shorts, keeps `None`-duration (live);
  - entry→Video mapping (id/title/url/channel/duration/published_at, status="discovered");
  - `--deep` path enumerates channels (fake).
- Unit (store): `upsert_channel` roundtrip; `insert_discovered_video` insert-only — a pre-existing `transcribed` video is NOT downgraded on re-discover.
- Unit (cli `run_discover`, temp-dir LanceDB + fake embedder): cutoff resolution precedence (after > state > 7d); writes channels+videos; `set_state` advances; N-new/M-known reporting.
- Integration (opt-in, network): real subscriptions feed discovery is NOT in scope for automated tests (requires real cookies); manual smoke only.

## Documentation Updates

- README: add `discover` to the command list + a short "daily routine" note.
- `.env.example`: no new keys (reuses cookies + proxy + store).
- Roadmap memory: mark SP1 done; note SP2 can consume `discover --json`.

## Out of Scope

- Downloading/transcribing discovered videos (SP0 `fetch` / SP2 batch).
- Scheduling/cron (user runs `discover` manually or via their own cron).
- Per-channel subscription management UI (SP4 frontend).
