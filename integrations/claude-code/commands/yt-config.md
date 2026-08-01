---
description: View or change yt-mem-ai settings (Webshare proxy, cookies browser, embedding model, caption langs, …).
argument-hint: [list | set KEY VALUE | get KEY | unset KEY | path]
---

Use the **yt** skill's "Configure & maintain" flow to run the requested config
operation for: $ARGUMENTS

Map the request to the CLI (values persist to the global config
`~/.yt-mem-ai/config.env`, secrets masked):

- `list` (or empty $ARGUMENTS) → `uvx yt-mem-ai config list` — every setting, value, source.
- `set KEY VALUE` → `uvx yt-mem-ai config set KEY VALUE`
- `get KEY` → `uvx yt-mem-ai config get KEY` (add `--reveal` for secrets)
- `unset KEY` → `uvx yt-mem-ai config unset KEY`
- `path` → `uvx yt-mem-ai config path`

Common keys (run `config list` for the full set):

- `WEBSHARE_PROXY_USERNAME` / `WEBSHARE_PROXY_PASSWORD` + `YT_USE_WEBSHARE true`
  — route yt-dlp + transcripts through the Webshare proxy.
- `YT_CAPTIONS_USE_WEBSHARE true` — proxy ONLY the transcript API (fixes
  IP-rate-limited captions; yt-dlp stays direct).
- `YT_COOKIES_BROWSER chrome` (or `brave`/`firefox`/`edge`) — fixes the YouTube
  "Sign in to confirm you're not a bot" bot check.
- `YT_EMBEDDING_MODEL paraphrase-multilingual-MiniLM-L12-v2` — multilingual
  embeddings (run `uvx yt-mem-ai reembed` afterwards to migrate the library).
- `YT_CAPTION_LANGS en,es,…` — preferred caption languages (priority order).

Only known keys are accepted and choice-constrained values are validated; if the
key is unknown, show `config list` so the user can pick a valid one.
