---
name: yt
description: One skill for any YouTube request over the yt-mem-ai CLI — one-shot by URL or id ("summarize: <url>", "highlight: <url>", "qa: <url>", "presentation: <url>"), process the latest subscription uploads into a daily digest, or a cross-video subscriptions review. Ingests and caches transcripts (captions → whisper), anchors highlights via semantic search, and never re-downloads a cached video. Also processes an arbitrary group of videos (a channel's recent uploads, a comma list of ids/URLs, or a date range) into per-video analysis + a group synthesis.
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
- **D — group (arbitrary set)** ("process/review these videos <ids/urls>", "review
  channel <url>", "review <channel> from <date> to <date>"): ingest a user-specified
  set, then per-video analysis + a group synthesis.

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
Live streams are auto-detected and marked `status=stream` — `fetch-pending` skips
them (long + usually caption-less). List them with `yt-ai list --status stream`;
to transcribe one on demand, fetch it directly (`yt-ai fetch <url>`, optionally
`--whisper`).

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

## D — group of videos (arbitrary set)

Process a user-specified set (not tied to today's subscriptions), then per-video
analysis + a top-level synthesis.

1. **Resolve the set → ids/URLs:**
   - comma list (`id1,id2,https://youtu.be/id3`) → parse directly;
   - channel (URL/@handle) → `yt-ai channel-list <url> --limit N [--from D] [--to D] --json`;
   - date range over a channel → same with `--from/--to`.
   Report the resolved count first; if it's large (> ~15), say so and confirm/cap
   before mass-ingesting (whisper is slow).
2. **Ingest each:** `yt-ai fetch <url>` (captions→whisper; streams auto-marked
   `status=stream` and skipped; continue past failures — note any skipped).
3. **Per-video:** run the **core** analysis (summary + search-anchored highlights +
   Q&A, `presentation` → `slides/<id>.md` if asked), persisted via `save-summary`,
   in each video's original language (FTS-anchor non-English).
4. **Group synthesis** → `groups/<label>.md` (label = channel handle / date-range
   slug / timestamp): an executive synthesis (themes, standouts, what's worth
   watching) + one section per video (`## <title>` + link, summary, top highlights
   as `MM:SS — label`, 2–3 Q&A).
5. **Report** the `groups/<label>.md` path + the executive synthesis.

This is the daily-digest shape (B) over an arbitrary set. Use C instead for a
themes-only essay with no per-video sections.

## Conventions

- All data via the `yt-ai` CLI ([[yt-manager]] has the full surface). Never touch
  the store directly.
- Grounded strictly in transcripts; highlight timestamps only from `yt-ai search`.
- **Language / translation:** transcripts may be in ANY language — the source
  language is stored and returned by `show --json` as `transcript_lang`. **Default:
  produce each artifact in the video's OWN original language** (Russian video →
  Russian summary) — no translation. Only translate when the user asks for a
  specific target language. If the user hasn't stated a preference and the batch
  mixes languages, ask once which output language they want, then apply it to the
  whole run (and treat that as their saved default). Anchoring caveat: vector
  search is language-sensitive — search with a phrase in the transcript's original
  language, then write the label in the chosen output language. (For heavily
  multilingual libraries, a multilingual `YT_EMBEDDING_MODEL` improves search.)
- `is_seen` is status-based, so re-fetch is a no-op → follow-ups ("now highlight
  it", "make slides") and re-runs never re-download.
- Dates are `YYYY-MM-DD`. Always report what ran + the output paths (`slides/`,
  `digests/`, `reviews/`).
- Related: [[yt-manager]] (the full CLI surface — discover, recommend, compile,
  supercut, frame, status).
