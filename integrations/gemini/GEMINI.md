# yt-mem-ai — Gemini playbook

For any YouTube task (summarize / highlights / Q&A / subscriptions digest or
review / analyzing a channel or set of videos), drive the `yt-mem-ai` MCP
server. All data goes through its tools; never invent highlight timestamps.

**Tools:** `fetch`, `show`, `search`, `list_videos`, `status`, `discover`,
`fetch_pending`, `channel_list`, `save_summary`, `like`, `dislike`, `recommend`,
`compile`, `supercut`, `frame`, `reembed`.

**Core (one video):**
1. `show(video_id)`; if `error: not found` and you have a URL →
   `fetch(url, captions_only=true)`, and on `status: no_captions` →
   `fetch(url, whisper=true)`.
2. Reuse a non-null `summary` from `show` unless a fresh artifact is asked for.
3. Anchor each highlight with `search(phrase, mode=vector, k=3)` (take `start_s`
   from a hit whose `video_id` matches).
4. Produce the exec summary + bullets, highlights `[{start_s, label}]`, Q&A
   `[{q, a}]`, then `save_summary(...)`.

**Scenarios:** digest (`discover` → `fetch_pending` → per-video →
`digests/<DATE>.md`); review (one cross-video essay to `reviews/<DATE>.md`);
group (resolve set → `fetch` each → `groups/<label>.md`).

Produce artifacts in the video's **original language** (`transcript_lang`);
translate only on request. Dates are `YYYY-MM-DD`. Report what ran + output paths.

**Reconfigure on request:** to change settings (Webshare proxy login, embedding
model/backend, cookies browser, caption languages) use `config_set(key, value)`
/ `config_list()` — persists to `~/.yt-mem-ai/config.env`, effective next call.
Only known `.env` keys are accepted; after changing the embedding model, run
`reembed`.
