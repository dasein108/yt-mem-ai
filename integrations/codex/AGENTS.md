# yt-mem-ai — Codex playbook

When a task is about YouTube (summarize / highlights / Q&A / a subscriptions
digest or review / analyzing a channel or set of videos), drive the `yt-mem-ai`
MCP server. All data goes through its tools — never touch the LanceDB store
directly, and never invent highlight timestamps.

## Tools

`fetch`, `show`, `search`, `list_videos`, `status`, `discover`, `fetch_pending`,
`channel_list`, `save_summary`, `like`, `dislike`, `recommend`, `compile`,
`supercut`, `frame`, `reembed`, and the config tools `config_list`, `config_get`,
`config_set`, `config_unset` (see **Reconfigure on request**).

## Core (one video)

1. **Ingest (idempotent):** `show(video_id)`. If `error: not found` and you have
   a URL → `fetch(url, captions_only=true)`; on `status: no_captions` →
   `fetch(url, whisper=true)`.
2. **Reuse:** if `show` returns a non-null `summary`, reuse it unless asked for a
   fresh artifact.
3. **Anchor:** for each candidate highlight phrase, `search(phrase, mode=vector,
   k=3)` and take the `start_s`/`ts` from a hit whose `video_id` matches.
4. **Produce** (you, the model — no external LLM): an exec summary + bullets,
   highlights JSON `[{start_s, label}]`, Q&A JSON `[{q, a}]`.
5. **Persist:** `save_summary(video_id, summary_md, highlights, qa)`.

## Scenarios

- **Digest** (latest subs): `discover` → `fetch_pending` → analyze each of the
  day's transcribed videos → `digests/<DATE>.md`.
- **Review** (themes essay): `list_videos(status=summarized, since=…)` → one
  cross-video essay to `reviews/<DATE>.md`.
- **Group** (arbitrary set): resolve via a comma list / `channel_list` / date
  range → `fetch` each → per-video analysis → `groups/<label>.md`.

## Reconfigure on request

If the user asks to change settings ("set my Webshare proxy login", "use the
multilingual embedding model", "pull cookies from Brave"), use the config tools —
don't ask them to edit files:

- `config_list()` — every setting, its value, and source.
- `config_set(key, value)` — persists to `~/.yt-mem-ai/config.env`; takes effect
  next call. Only known `.env` keys (e.g. `WEBSHARE_PROXY_USERNAME`,
  `WEBSHARE_PROXY_PASSWORD`, `YT_EMBEDDING_MODEL`, `YT_EMBEDDING_BACKEND`,
  `YT_COOKIES_BROWSER`, `YT_CAPTION_LANGS`). After switching the embedding
  model/backend, run `reembed` to migrate the library.

## Conventions

- Produce artifacts in each video's **original language** (from `transcript_lang`
  in `show`); translate only when a target language is requested. Vector search
  is language-sensitive — search in the transcript's language, label in the
  output language.
- `fetch` is retry-safe (status-based `is_seen`) — follow-ups never re-download.
- Dates are `YYYY-MM-DD`. Always report what ran + output paths.
