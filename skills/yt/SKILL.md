---
name: yt
description: One-shot YouTube request by URL in chat — "summarize: <url>", "highlight: <url>", "qa: <url>", or "summarize this video <url>". Ingests the video if not already cached (captions → whisper fallback), then produces the requested artifact from the cached transcript. Repeat requests on the same video reuse the cache — no re-download.
---

# yt — one-shot YouTube summarize / highlight / Q&A by URL

Turn a YouTube URL into a summary, highlights, or Q&A in one step. Ingests and
**caches** the transcript on first use; later requests on the same video read the
cache — no download.

## Inputs
- A YouTube URL (`watch?v=`, `youtu.be/`, `/shorts/`) — or a bare `video_id`
  (for a follow-up on a video already discussed).
- Intent from the phrasing: `summarize` (default), `highlight`, or `qa`.

## Steps

1. **Identify the video.** Extract the 11-char `video_id` and the URL. If the
   user gave only a bare id / said "this video" as a follow-up, reuse the id from
   the earlier turn — do not ask for the URL again.

2. **Ensure the transcript is cached** (idempotent — a no-op if already ingested):
   ```bash
   yt-ai fetch <url> --captions-only
   ```
   - If the video is already ingested, this prints the id and returns instantly
     (`is_seen` skips it — **no download**).
   - If it prints `no captions available: ...`, fall back to whisper (downloads
     audio + transcribes — slower, but always yields a transcript):
     ```bash
     yt-ai fetch <url> --whisper
     ```
   Never re-download a video that is already cached.

3. **Reuse the analysis if it exists.** Load the stored data:
   ```bash
   yt-ai show <video_id> --json
   ```
   If the JSON already has a non-null `summary` (from a prior call), **reuse it**
   and skip to step 5 — no recompute. Otherwise generate + save it by following
   **[[summarize-video]]** (semantic-search-anchored highlights, grounded in the
   transcript, persisted with `save-summary`).

4. **Present the requested artifact** in chat:
   - `summarize` → executive summary + key bullets (mention highlights/Q&A are
     available).
   - `highlight` → the highlights as `MM:SS — label`, each a deep link
     `https://www.youtube.com/watch?v=<id>&t=<start>s`.
   - `qa` → the Q&A pairs.

## Notes
- **The cache is the store.** After step 2 the transcript lives in LanceDB
  (`transcripts` + `chunks`); `is_seen` makes re-fetch a no-op, so follow-ups
  ("now highlight the important parts") never re-download — they read the cached
  transcript, and if already summarized, the cached highlights.
- Everything is grounded in the transcript; highlight timestamps come from
  `yt-ai search`, never invented.
- Related: [[summarize-video]] (the id-based analysis primitive this delegates
  to), [[yt-manager]] (any other yt-ai operation), [[daily-digest]] (a day's batch).
