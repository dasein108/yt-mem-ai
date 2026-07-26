---
name: yt
description: One skill for any YouTube request over the yt-mem-ai CLI — one-shot by URL or id ("summarize: <url>", "highlight: <url>", "qa: <url>", "presentation: <url>"), process the latest subscription uploads into a daily digest, or a cross-video subscriptions review. Ingests and caches transcripts (captions → whisper), anchors highlights via semantic search, and never re-downloads a cached video.
---

# yt — summarize / highlights / Q&A / presentation / digest / review

One entry point for turning YouTube into artifacts. All data access goes through
the `yt-ai` CLI (see [[yt-manager]] for the full command surface) — never touch
the LanceDB store directly. Everything is grounded in the transcript; highlight
timestamps come from `yt-ai search`, never invented. The analysis is done by
**this agent** — no API key, no OpenRouter.

## Pick the scenario

- **A — one video** (a URL, a bare 11-char `video_id`, or "this video" as a
  follow-up): produce a `summarize` / `highlights` / `qa` / `presentation` artifact.
- **B — process latest subscriptions** ("catch up", "daily", "new uploads"):
  discover + fetch + analyze each + write a dated digest.
- **C — subscriptions review** ("review my subs", "themes lately", "what's been
  happening"): one cross-video synthesis over a date range.

## Core: analyze one video (used by A and B)

Given a `video_id` (and a URL if it may not be ingested yet):

1. **Ensure ingested** (idempotent): `yt-ai show <video_id> --json`.
   - `not found` and you have a URL → `yt-ai fetch <url> --captions-only`. If that
     prints `no captions available: ...`, fall back to `yt-ai fetch <url> --whisper`
     (downloads audio + transcribes — slower, always yields a transcript).
   - Already ingested → instant, no download (`is_seen` skips it).
2. **Reuse if present:** if the `show --json` output has a non-null `summary`,
   reuse it — skip generation unless the user asked for a fresh artifact.
3. **Anchor highlights:** for each candidate highlight phrase, run
   `yt-ai search "<phrase>" --vector -k 3` and use the `MM:SS` from a returned
   line whose `video_id` matches. Never invent timestamps.
4. **Produce** (you, the model — no API): `summary_md` (2–4 sentence exec summary
   + key bullets), `highlights` JSON `[{"start_s": <seconds>, "label": "..."}]`
   (3–8, seconds from step 3), `qa` JSON `[{"q": "...", "a": "..."}]` (3–6).
5. **Persist:** `yt-ai save-summary <video_id> "<summary_md>" --highlights '<json>' --qa '<json>'`.

## A — single-video artifacts

Run the core, then deliver the artifact the phrasing asked for:

- **summarize** (default) → executive summary + key bullets in chat (mention
  highlights / qa / presentation are available on request).
- **highlights** → each as `MM:SS — label`, a deep link
  `https://www.youtube.com/watch?v=<id>&t=<start>s`.
- **qa** → the Q&A pairs.
- **presentation** → write a slide deck to `slides/<video_id>.md`:
  - `---`-separated slides (renderable by reveal.js / Marp; no images).
  - Slide 1: title + channel + a one-line thesis.
  - One slide per theme/section: a heading, 3–5 key-point bullets, and any
    notable quote with its `MM:SS` timestamp.
  - Final slide: takeaways + the watch link.
  Report the file path + the title slide in chat.

## B — process latest subscriptions (daily digest)

```bash
yt-ai discover           # new uploads → 'discovered'
yt-ai fetch-pending      # download + transcribe + embed today's batch (skips failures)
```
Then for each of the day's transcribed videos
(`yt-ai list --status transcribed --since <DATE> --json`), run the **core**
analysis. Compose `digests/<DATE>.md`:
- Top **executive digest**: cross-video themes and what's worth the user's time.
- One **section per video**: `## <title>` + link, the 2–4 sentence summary, top
  highlights (`MM:SS — label`), 2–3 Q&A.

Create `digests/` if needed. Report the digest path + the executive digest.
Idempotent — re-running overwrites each `summaries` row and rewrites the file.

## C — subscriptions review (cross-video themes)

Select the period's videos: `yt-ai list --status summarized --since <DATE> --json`
(analyze any still `transcribed` via the core first). Then write **one essay** to
`reviews/<DATE>.md` — no per-video sections:
- Common threads across the videos, contradictions / disagreements, emerging trends.
- Ground every claim in the videos; when citing a specific moment, name the video
  title + a `MM:SS` deep link.

Report the review path + a short lede in chat.

## Conventions

- All data via the `yt-ai` CLI ([[yt-manager]] has the full surface). Never touch
  the store directly.
- Grounded strictly in transcripts; highlight timestamps only from `yt-ai search`.
- **Language / translation:** transcripts may be in ANY language — the source
  language is stored and returned by `show --json` as `transcript_lang`. Produce
  every artifact (summary, highlight labels, Q&A, presentation, digest, review) in
  the user's **target language** (default English, or whatever they ask), translating
  from the source as needed. Caveat: vector search is language-sensitive, so to
  anchor a highlight in a non-English video, run `yt-ai search "<phrase>"` with the
  phrase in the transcript's **original** language, then write the label in the
  target language. (For heavily multilingual libraries, set a multilingual
  `YT_EMBEDDING_MODEL` for better cross-language search.)
- `is_seen` is status-based, so re-fetch is a no-op → follow-ups ("now highlight
  it", "make slides") and re-runs never re-download.
- Dates are `YYYY-MM-DD`. Always report what ran + the output paths (`slides/`,
  `digests/`, `reviews/`).
- Related: [[yt-manager]] (the full CLI surface — discover, recommend, compile,
  supercut, frame, status).
