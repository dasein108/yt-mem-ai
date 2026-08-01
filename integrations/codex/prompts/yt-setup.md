Run the yt-mem-ai first-run setup as a short interactive wizard.

Use the `yt-mem-ai` MCP `config_*` tools. Ask one thing at a time; skip a step if
the user says it's already fine. Persist every choice with `config_set(key,
value)` (global config `~/.yt-mem-ai/config.env`).

1. **Show current state** — call `config_list()` and summarize what's set vs default.
2. **Cookies browser** — the fix for YouTube's "Sign in to confirm you're not a
   bot" check. Ask which browser they're logged into YouTube on and set
   `YT_COOKIES_BROWSER` (`chrome`/`brave`/`firefox`/`edge`, or blank).
3. **Webshare proxy (optional)** — only if they hit IP rate-limits. If yes, set
   `WEBSHARE_PROXY_USERNAME` + `WEBSHARE_PROXY_PASSWORD`, then either
   `YT_USE_WEBSHARE=true` (everything) or `YT_CAPTIONS_USE_WEBSHARE=true` (only
   the transcript API — recommended).
4. **Embedding model (optional)** — default is English `all-MiniLM-L6-v2`. For
   non-English videos set `YT_EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2`
   (re-embed an existing library afterwards).
5. **Caption languages (optional)** — set `YT_CAPTION_LANGS` (e.g. `en,es`).
6. **Verify** — call `config_list()` to show the final state, then offer a smoke
   test with the summarize prompt on a short YouTube URL.

Keep it conversational and skippable; don't set anything the user didn't confirm.
