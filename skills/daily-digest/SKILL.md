---
name: daily-digest
description: Use when the user wants a daily digest of their freshly-fetched YouTube subscription videos — a combined summary plus per-video summaries/highlights/Q&A. Reads transcribed videos via the yt-ai CLI and writes digests/<DATE>.md. Run after `yt-ai fetch-pending`.
---

# Daily Digest

Turn the videos fetched for a given day into per-video summaries and one combined
digest file. All data access is through the `yt-ai` CLI — never touch the store directly.

## Inputs
- `date` (optional, default = today, `YYYY-MM-DD`) — the `--since` cutoff.

## Steps

1. **Select the day's videos:**
   ```bash
   yt-ai list --status transcribed --since <DATE> --json
   ```
   Parse the JSON array. If empty, tell the user to run `yt-ai fetch-pending` first and stop.

2. **Per video** (each entry's `video_id`):
   a. Load content: `yt-ai show <video_id> --json` → `title`, `url`, `transcript`.
   b. Anchor highlights: for each candidate highlight phrase, run
      `yt-ai search "<phrase>" --vector -k 3` and use the `MM:SS` from a line whose
      `video_id` matches. **Never invent timestamps.**
   c. Produce (grounded strictly in the transcript):
      - `summary_md`: 2–4 sentence executive summary + key bullets.
      - `highlights`: JSON `[{"start_s": <seconds>, "label": "..."}]` (3–8, from step b).
      - `qa`: JSON `[{"q": "...", "a": "..."}]` (3–6).
   d. Persist: `yt-ai save-summary <video_id> "<summary_md>" '<highlights_json>' '<qa_json>'`.

3. **Compose the digest** at `digests/<DATE>.md`:
   - A top **executive digest**: what happened across the day, cross-video themes, what's
     worth the user's time.
   - One **section per video**: `## <title>` + link, the 2–4 sentence summary, top
     highlights as `MM:SS — label`, and 2–3 Q&A.
   Create the `digests/` directory if needed.

4. **Report** the digest file path + the executive digest in chat.

## Notes
- Everything is grounded in the transcripts; do not hallucinate content.
- Highlight timestamps come only from `yt-ai search` results.
- Idempotent: re-running overwrites each video's `summaries` row and rewrites the dated file.
- Related: [[summarize-video]] does a single video; this batches a day + adds the cross-video digest.
