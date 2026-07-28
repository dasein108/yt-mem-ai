# yt-mem-ai — Gemini playbook

For any YouTube task (summarize / highlights / Q&A / subscriptions digest or
review / analyzing a channel or set of videos), use the installed **`yt` and
`yt-manager` skills** — they hold the full workflow. Everything runs through the
**`yt-ai` CLI**; never touch the store directly and never invent highlight
timestamps (anchor them with `yt-ai search`).

**Running the CLI** — if `yt-ai` isn't on PATH, run every command as
`uvx yt-mem-ai <cmd>` (zero-install):

```
uvx yt-mem-ai show <video_id> --json          # ingested? metadata + transcript
uvx yt-mem-ai fetch <url> --captions-only      # ingest (captions→whisper)
uvx yt-mem-ai search "<phrase>" --vector -k 3  # anchor a highlight timestamp
uvx yt-mem-ai save-summary <id> "<md>" --highlights '<json>' --qa '<json>'
uvx yt-mem-ai discover ; uvx yt-mem-ai fetch-pending
```

The `yt-manager` skill documents the full surface (list, channel-list, recommend,
compile, supercut, frame, reembed, config).

**Reconfigure on request** — change settings via the CLI, not by editing files:
`uvx yt-mem-ai config set KEY VALUE` / `uvx yt-mem-ai config list` (Webshare
creds, embedding model/backend, cookies browser, caption languages). After
changing the embedding model, run `uvx yt-mem-ai reembed`.

Produce artifacts in the video's **original language** (`transcript_lang`);
translate only on request. Dates are `YYYY-MM-DD`. Report what ran + output paths.
