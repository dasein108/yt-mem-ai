---
name: summarize-video
description: Use when the user wants a summary, highlights, or Q&A for a YouTube video already ingested by yt-ai (present in the SQLite DB). Reads the stored transcript and writes summary/highlights/Q&A back to the summaries table.
---

# Summarize Video

Generate a summary, timestamped highlights, and Q&A for an ingested video, then
persist to the `summaries` table.

## Inputs
- `video_id` (required)
- DB path: default `yt_summary.db` (or `YT_DB_PATH` from `.env`)

## Steps

1. **Load the transcript.** Query:
   ```sql
   SELECT v.title, v.url, t.full_text, t.lang
   FROM videos v JOIN transcripts t ON t.video_id = v.video_id
   WHERE v.video_id = :video_id;
   ```
   If no row, tell the user to run `yt-ai fetch <url>` first and stop.

2. **Load segments for timestamps** (for highlights):
   ```sql
   SELECT start_s, text FROM segments WHERE video_id = :video_id ORDER BY start_s;
   ```

3. **Produce the analysis** (you, the model, do this — no API call):
   - Executive summary (2–4 sentences) + key bullet points → `summary_md`.
   - 3–8 highlights: pick the most significant moments; map each to the nearest
     `start_s` from segments. Format as JSON `[{"start_s": float, "label": str}]`.
   - 3–6 Q&A pairs a viewer would ask. JSON `[{"q": str, "a": str}]`.

4. **Persist.** Upsert into `summaries`:
   ```sql
   INSERT INTO summaries (video_id, summary_md, highlights, qa, model, created_at)
   VALUES (:video_id, :summary_md, :highlights, :qa, 'claude-code-skill', :now)
   ON CONFLICT(video_id) DO UPDATE SET
     summary_md=excluded.summary_md, highlights=excluded.highlights,
     qa=excluded.qa, model=excluded.model, created_at=excluded.created_at;
   ```
   Use an ISO8601 UTC timestamp for `:now`.

5. **Report** the summary + highlights (as `MM:SS — label`) + Q&A to the user in chat.

## Notes
- Highlight timestamps must come from real `segments.start_s` values, never invented.
- Keep everything grounded in the transcript; do not hallucinate content.
