# yt-mem-ai — Codex playbook

For any YouTube task (summarize / highlights / Q&A / a subscriptions digest or
review / analyzing a channel or set of videos), use the installed **`yt` and
`yt-manager` skills** — they contain the full workflow. Everything runs through
the **`uvx yt-mem-ai` CLI**; never touch the LanceDB store directly, and never
invent highlight timestamps (anchor them with `uvx yt-mem-ai search`).

## Running the CLI

Run every command as **`uvx yt-mem-ai <cmd>`** (zero-install, cached). **Nothing
is installed on PATH** — this plugin ships skills only, so don't look for a
`yt-ai` binary, a wrapper, or a venv, and don't fall back to raw `yt-dlp`:

```
uvx yt-mem-ai show <video_id> --json          # ingested? metadata + transcript
uvx yt-mem-ai fetch <url> --captions-only      # ingest (captions→whisper)
uvx yt-mem-ai search "<phrase>" --vector -k 3  # anchor a highlight timestamp
uvx yt-mem-ai save-summary <id> "<md>" --highlights '<json>' --qa '<json>'
uvx yt-mem-ai discover ; uvx yt-mem-ai fetch-pending   # subscriptions batch
uvx yt-mem-ai channel-list <url> --limit N --json      # enumerate a channel
```

See the `yt-manager` skill for the complete command surface (list, recommend,
compile, supercut, frame, reembed, …).

## Reconfigure on request

To change settings ("set my Webshare proxy login", "use the multilingual
embedding model", "pull cookies from Brave"), use the config CLI — don't ask the
user to edit files:

```
uvx yt-mem-ai config list                 # every setting, value, and source
uvx yt-mem-ai config set KEY VALUE        # e.g. WEBSHARE_PROXY_USERNAME, YT_EMBEDDING_MODEL
```

Only known `.env` keys are accepted; secrets are masked. After changing the
embedding model/backend, run `uvx yt-mem-ai reembed` to migrate the library.

Use `config set` rather than `KEY=value uvx …` — each `uvx` run is a fresh
process, so an env var only applies to that one command.

## When YouTube blocks a fetch

- `YouTube bot check: ... Sign in to confirm you're not a bot` (exit 4) → yt-dlp
  needs a browser session: `uvx yt-mem-ai config set YT_COOKIES_BROWSER chrome`
  (or `brave`/`firefox`/`edge`/`safari`), then re-run the same fetch.
- `captions blocked by YouTube (IP rate-limited)` (exit 3) → cookies don't help;
  retry later or set `YT_CAPTIONS_USE_WEBSHARE true` + the `WEBSHARE_PROXY_*` creds.
- `no captions available` (exit 1) → re-run with `--whisper`.

## Conventions

- Produce artifacts in each video's **original language** (from `transcript_lang`
  in `show --json`); translate only when asked.
- `fetch` is retry-safe (status-based `is_seen`) — follow-ups never re-download.
- Dates are `YYYY-MM-DD`. Always report what ran + output paths.
