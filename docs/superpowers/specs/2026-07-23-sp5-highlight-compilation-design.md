# SP5 — Highlight Compilation Design

**Date:** 2026-07-23
**Status:** Approved (brainstorming complete)
**Builds on:** the `summaries` (highlights) + `chunks` (spans) tables.

## Vision

Turn the highlights across a batch of summarized videos into a single
**deep-linked compilation document** — each highlight is a YouTube link that
jumps straight to its timestamp (`watch?v=ID&t=<start>s`), budget-bounded so a
day's ~5h of videos becomes a ~20-minute curated list of the best moments you
can click into. No media rendering: you watch the real videos in context.

## Locked Decisions

| Concern | Choice |
|---|---|
| Output | a **deep-linked document** (markdown default + `--json`), NOT a rendered media file |
| Link form | `https://www.youtube.com/watch?v=<video_id>&t=<int(start_s)>s` |
| Clip span | the highlight's **containing chunk** `[start_s, end_s]` (highlights are already snapped to chunk starts); fallback duration if no chunk |
| Selection | **summarized** videos published since `--since`; newest-video-first, then by `start_s` |
| Budget | `--max-minutes` (default 20) — accumulate clips until summed span durations reach the budget |
| Source of highlights | `summaries.highlights` (run `/daily-digest` or the summarize path first) |

## Scope note

Highlights only exist for **summarized** videos (the `summaries` table). `compile`
reads those; it does not summarize. The natural flow is
`discover → fetch-pending → /daily-digest (or the summarize endpoint) → compile`.

## Architecture

```
yt_summary/
  compile.py   NEW: deep_link, chunk-span mapping, budget accumulation, render_markdown, compile()
  cli.py       + compile command + run_compile
```

No new store functions — reuse `list_videos_by_status("summarized", since)`,
`get_summary`, `list_chunks`.

### compile.py (pure + orchestrator)

- `deep_link(video_id, start_s) -> str` — `f"https://www.youtube.com/watch?v={video_id}&t={int(start_s)}s"`.
- `chunk_span(chunks, start_s, fallback_s) -> tuple[float, float]` — find the chunk containing
  `start_s` (`c.start_s <= start_s <= c.end_s`), else the nearest by `start_s`; return its
  `(start_s, end_s)`. If no chunks → `(start_s, start_s + fallback_s)`.
- `Clip` dataclass: `video_id, title, label, start_s, end_s, duration_s, link`.
- `video_clips(video, summary, chunks, fallback_s) -> list[Clip]` — parse `summary["highlights"]`
  (JSON string) → for each `{start_s, label}` build a `Clip` via `chunk_span` + `deep_link`;
  `duration_s = end_s - start_s`.
- `accumulate(clips, max_seconds) -> list[Clip]` — take clips in order until the running sum of
  `duration_s` reaches `max_seconds` (always include at least the first clip; the clip that crosses
  the budget is the last one included).
- `render_markdown(clips, since, max_minutes) -> str` — a `# Highlights` doc, grouped by video
  (`## <title>` with the video link), each highlight a line `- [MM:SS] <label> — <deep link>`,
  plus a header line with the date range + total minutes.
- `compile(db, since, max_minutes, fallback_s=45) -> list[Clip]` — orchestrates:
  `list_videos_by_status(db, "summarized", since)` (newest-first) → for each, `get_summary` +
  `list_chunks` → `video_clips` → flatten → `accumulate(max_minutes*60)`.

### cli.py

- `run_compile(cfg, since=None, max_minutes=20, db=None) -> list[Clip]` — opens the store if needed;
  `since` defaults to today; returns the accumulated clips.
- `compile` Typer command: `--since`, `--max-minutes 20`, `--json`, `--out FILE`.
  - Default: print the markdown (or write to `--out`, e.g. `compilations/<since>.md`).
  - `--json`: emit the clips array (`video_id, title, label, start_s, end_s, duration_s, link`).
  - Empty → "no highlights — summarize some videos first".

### Data Flow

```
compile --since D --max-minutes 20
  → list_videos_by_status("summarized", D)  (newest-first)
     → per video: get_summary.highlights + list_chunks → chunk_span + deep_link → Clip[]
  → flatten, accumulate until Σ duration ≥ 20min
  → render_markdown (or --json)  [→ compilations/<D>.md with --out]
```

### Error Handling

- A video whose `summary.highlights` is missing/`null`/bad JSON → contributes no clips (guarded parse).
- A highlight `start_s` with no chunks → fallback span `[start_s, start_s + fallback_s]`.
- No summarized videos in range → clear "nothing to compile" message, empty output.
- `--out` writes create the parent dir; `compilations/` is gitignored.

### Testing (offline)

- `deep_link` format (`&t=<int>s`; floats floored).
- `chunk_span`: containing chunk, nearest-when-none-contains, empty→fallback.
- `video_clips`: parses the highlights JSON string, builds correct links + durations; bad JSON → [].
- `accumulate`: stops at the budget, always includes ≥1, includes the budget-crossing clip.
- `render_markdown`: groups by video, `[MM:SS]` formatting, contains the deep links.
- `run_compile` (temp-dir LanceDB + fake embedder): seed 2 summarized videos with highlights +
  chunks; assert clips ordered newest-first, links correct, and `--max-minutes` trims the total.
- No ffmpeg, no network in the suite.

## Documentation Updates

- README: add `yt-ai compile` to the commands + a note in the daily routine (after summarizing).
- `CLAUDE.md`: add `compile.py` to the module map + the deep-link/budget behavior.
- Roadmap memory: mark SP5 done → the roadmap is complete.

## Out of Scope (future improvements)

- **Video-fragment supercut** (kept for later, per the user): re-download highlight sections via
  `yt-dlp --download-sections` and stitch a rendered video reel with burned-in labels/refs via ffmpeg.
- Audio supercut from the stored mp3s.
- Cross-day dedup of repeated highlights; ranking/curation beyond newest-first + budget.
- Embedding chapter markers / exporting to a real YouTube playlist.
