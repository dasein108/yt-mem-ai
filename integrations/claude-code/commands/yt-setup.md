---
description: First-run setup wizard — walk through Webshare proxy, cookies browser, and embedding model, then verify.
argument-hint: (no args)
---

Run the yt-mem-ai first-run setup as a short interactive wizard, using the **yt**
skill's "Configure & maintain" flow. Ask one thing at a time; skip a step if the
user says it's already fine. Persist every choice with `uvx yt-mem-ai config set
KEY VALUE` (global config `~/.yt-mem-ai/config.env`).

1. **Prereqs** — confirm `uv`/`uvx` is on PATH (`uvx --version`). If missing,
   point to https://docs.astral.sh/uv/ and stop.
2. **Show current state** — run `uvx yt-mem-ai config list` and summarize what's
   already set vs default.
3. **Cookies browser** — the fix for YouTube's "Sign in to confirm you're not a
   bot" check. Ask which browser they're logged into YouTube on and set
   `YT_COOKIES_BROWSER` (`chrome`/`brave`/`firefox`/`edge`, or blank for none).
4. **Webshare proxy (optional)** — only if they hit IP rate-limits. If yes, set
   `WEBSHARE_PROXY_USERNAME` + `WEBSHARE_PROXY_PASSWORD`, then either
   `YT_USE_WEBSHARE true` (proxy everything) or `YT_CAPTIONS_USE_WEBSHARE true`
   (proxy only the transcript API — recommended, yt-dlp stays direct).
5. **Embedding model (optional)** — default is English `all-MiniLM-L6-v2`. If
   they watch non-English videos, set
   `YT_EMBEDDING_MODEL paraphrase-multilingual-MiniLM-L12-v2`. Note: if they
   already have a library, run `uvx yt-mem-ai reembed` afterwards to migrate it.
6. **Caption languages (optional)** — set `YT_CAPTION_LANGS` (e.g. `en,es`) if
   they want a non-default priority order.
7. **Verify** — run `uvx yt-mem-ai config list` to show the final state, then
   offer a smoke test: `/yt-summarize <a short YouTube URL>`.

Keep it conversational and skippable; don't set anything the user didn't confirm.
