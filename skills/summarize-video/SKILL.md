---
name: summarize-video
description: Use when the user wants a summary, highlights, or Q&A for a YouTube video already ingested by yt-ai (present in the LanceDB store). Reads the stored transcript via the CLI and writes summary/highlights/Q&A back.
---

# Summarize Video

Generate a summary, timestamped highlights, and Q&A for an ingested video, then persist it.

## Inputs
- `video_id` (required)

## Steps

1. **Load the video + transcript** (JSON):
   ```bash
   yt-ai show <video_id> --json
   ```
   If it prints `not found`, tell the user to run `yt-ai fetch <url>` first and stop.
   The JSON has `title`, `url`, `status`, `duration_s`, and `transcript` (full text).

2. **Find timestamps for highlights** with semantic search over the video's own chunks — for each candidate highlight phrase:
   ```bash
   yt-ai search "<phrase>" --vector -k 3
   ```
   Use the returned `MM:SS video_id text` lines whose `video_id` matches to anchor each highlight to a real timestamp. Never invent timestamps.

3. **Produce the analysis** (you, the model — no API call):
   - Executive summary (2–4 sentences) + key bullets → `summary_md`.
   - 3–8 highlights as JSON `[{"start_s": <seconds>, "label": "..."}]` (seconds from step 2).
   - 3–6 Q&A pairs as JSON `[{"q": "...", "a": "..."}]`.

4. **Persist:**
   ```bash
   yt-ai save-summary <video_id> "<summary_md>" --highlights '<highlights_json>' --qa '<qa_json>'
   ```

5. **Report** the summary + highlights (`MM:SS — label`) + Q&A in chat.

## Notes
- Everything must be grounded in the transcript; do not hallucinate.
- Highlight timestamps come from `yt-ai search` results, never invented.
