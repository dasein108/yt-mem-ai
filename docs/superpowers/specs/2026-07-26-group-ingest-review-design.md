# Group ingest + group review

**Date:** 2026-07-26 · **Repo:** engine `yt-mem-ai` (CLI) + `yt` skill

## Purpose

Process an **arbitrary user-specified set** of videos — a comma list of ids/URLs, a
channel's recent uploads, or a published-date range — then produce per-video
analysis **plus** a top-level group synthesis (the daily-digest shape generalized
beyond "today's subscriptions").

## Input forms

1. **Comma ids/URLs:** `id1,id2,https://youtu.be/id3` — the group is exactly those
   (parsed skill-side; each `fetch`ed).
2. **Channel:** a channel URL / `@handle` — its newest **N** uploads (default cap
   **20**, `--limit` override).
3. **Date range:** `--from YYYY-MM-DD --to YYYY-MM-DD` — filters a channel's uploads
   (or an id-set) to that publish window.

## New CLI: `channel-list`

`yt-ai channel-list <url> [--limit N=20] [--from D] [--to D] [--json]`

- Flat-extracts a channel's uploads playlist, newest-first, reusing discovery's
  approach: `extract_flat` + `playlistend=limit` + `youtubetab:approximate_date`
  stamping (see `discovery.py`). Resolve `<url>` to the channel's `/videos` tab.
- Filter to `[from, to]` by the per-entry approximate `published_at` (string date
  compare, like the rest of the codebase).
- Output (human): `published  video_id  duration  title` newest-first; `--json`: a
  list of `{video_id, url, title, published_at, duration_s}`.
- **Core:** `run_channel_list(cfg, url, limit=20, after=None, before=None,
  extract_fn=None) -> list[Video]` — injectable `extract_fn` seam for offline tests
  (mirrors `discovery.discover`). Does NOT ingest — enumeration only; the skill
  drives ingestion via `fetch`.
- Streams are handled at fetch time (already marked/skipped), so `channel-list`
  needs no stream logic.

Comma-id and id-set date-filtering need no CLI — the skill parses the list and, for
a date range over an id-set, filters via each video's `published_at` from
`show --json` / `channel-list`.

## `yt` skill — "group" scenario

Triggered by: "process/review these videos <ids/urls>", "review channel <url>",
"review <channel> from <date> to <date>", "summarize this list", etc.

1. **Resolve the group → a list of video ids/URLs:**
   - comma list → parse ids/URLs directly;
   - channel → `yt-ai channel-list <url> --limit N [--from --to] --json`;
   - date range over a channel → same with `--from/--to`.
   Report the resolved count before processing; if large (> ~15), note it and cap
   or confirm.
2. **Ingest each:** `yt-ai fetch <url>` (captions→whisper fallback; streams
   auto-marked `status=stream` and skipped; continue past failures, list any skipped).
3. **Per-video analysis** (the skill's existing *core*): for each transcribed video
   → summary + search-anchored highlights + Q&A (+ `presentation` → `slides/<id>.md`
   if the user asked for it), persisted via `save-summary`. Produced in each video's
   **original language** (user's saved default), FTS-anchored for non-English.
4. **Group synthesis** → `groups/<label>.md` (label = channel handle, or a slug of
   the date range, or a timestamp):
   - **Executive synthesis:** cross-video themes, standouts, what's worth watching.
   - **One section per video:** `## <title>` + link, the 2–4 sentence summary, top
     highlights (`MM:SS — label` deep links), 2–3 Q&A.
5. **Report** the `groups/<label>.md` path + the executive synthesis in chat.

Add `groups/` to `.gitignore`.

## Relationship to existing scenarios

- **B (process subscriptions → digest):** same per-video + exec structure, but over
  *today's discovered subscriptions*. The group scenario is the same shape over an
  *arbitrary* set. Implementation shares the digest composition; only the
  video-set resolution differs.
- **C (subscriptions review):** cross-video *themes essay only*, no per-video
  sections. Different deliverable.

## Data flow

```
group: channel @SomeChannel, last 10
  → yt-ai channel-list https://youtube.com/@SomeChannel --limit 10 --json
  → for each: yt-ai fetch <url>   (skip/mark streams, continue on error)
  → for each transcribed: core analysis → save-summary (+ slides/<id>.md)
  → compose groups/SomeChannel.md (exec synthesis + per-video sections)
  → report path + exec synthesis
```

## Error handling

| Case | Behavior |
|---|---|
| a video fails to ingest (blocked/unavailable) | skip, list it in the group doc's "skipped" note; continue |
| a video is a stream | marked `status=stream`, excluded from the group review (note it) |
| channel URL invalid / no uploads | `channel-list` prints "no videos"/error, exit 1 |
| empty resolved group | skill reports nothing to do |
| large group (>15) | skill surfaces the count + caps or asks before mass-whispering |

## Testing

- **`channel-list`** (`tests/test_cli.py` / a discovery-style test): injected
  `extract_fn` returns fake channel entries → `run_channel_list` returns them
  newest-first, respects `--limit`, and filters by `--from/--to`. Offline, no network.
- Skill behavior is not unit-tested (it's a skill), but the CLI seam it relies on is.

## Scope / non-goals

Engine CLI (`channel-list` + `run_channel_list`) + `yt` skill (group scenario) +
`.gitignore` + docs. Non-goals: ingesting entire channel histories by default
(capped), a bespoke group-analysis CLI (analysis stays skills-primary), parallel
ingestion (sequential, continue-on-error), and de-duping across prior runs (fetch's
`is_seen` already makes re-runs cheap).
