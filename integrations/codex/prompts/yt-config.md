View or change yt-mem-ai settings: $ARGUMENTS

Use the `yt-mem-ai` MCP `config_*` tools (values persist to the global config
`~/.yt-mem-ai/config.env`, secrets masked):

- `list` (or empty) → `config_list()` — every setting, value, source.
- `set KEY VALUE` → `config_set(key, value)`
- `get KEY` → `config_get(key)` (`reveal=true` for secrets)
- `unset KEY` → `config_unset(key)`

Common keys (call `config_list()` for the full set):

- `WEBSHARE_PROXY_USERNAME` / `WEBSHARE_PROXY_PASSWORD` + `YT_USE_WEBSHARE=true`
  — route yt-dlp + transcripts through the Webshare proxy.
- `YT_CAPTIONS_USE_WEBSHARE=true` — proxy ONLY the transcript API (fixes
  IP-rate-limited captions).
- `YT_COOKIES_BROWSER=chrome` (or `brave`/`firefox`/`edge`) — fixes the YouTube
  "Sign in to confirm you're not a bot" bot check.
- `YT_EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2` — multilingual
  embeddings (re-embed the library afterwards).
- `YT_CAPTION_LANGS=en,es,…` — preferred caption languages (priority order).

Only known keys are accepted and choice-constrained values validated; if the key
is unknown, call `config_list()` and let the user pick a valid one.
