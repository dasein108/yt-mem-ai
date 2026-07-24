# Backlog

Deferred features — not yet designed/implemented. Each entry captures intent +
enough context to brainstorm properly when picked up.

## Channel subscribe / unsubscribe

**Primary intent:** let the user **unsubscribe (mute) channels they no longer
want to see** in discovery. Subscribe/follow is secondary.

**Design fork to resolve at pickup:**
- **Local follow/mute layer (recommended default):** a channel list in the DB
  steers discovery. `mute` → `discover` skips that channel's uploads; `follow`
  → include a channel's uploads (even beyond the YT sub feed, via the `--deep`
  path). No YouTube account changes, no OAuth — fits the local-first design.
- **Real YouTube unsubscribe:** actually change the account via YouTube Data
  API v3 + OAuth write scope (`youtube.force-ssl`) — Google Cloud project,
  consent flow, quota. yt-dlp/cookies path is read-only and can't do this.

**Existing hooks to build on:**
- `store/db.py` `upsert_channel` + `channels` table (already tracks channel_id,
  title, a count).
- `discovery.py` — `_sources` already enumerates channels under `--deep`; the
  feed loop is where a mute filter would apply (drop entries whose `channel_id`
  is muted).
- Videos carry `channel_id` (and, once fetched, `channel` name).

**Sketch (local layer):**
- CLI: `yt-ai channel mute <id|url|name>`, `yt-ai channel unmute …`,
  `yt-ai channel follow …`, `yt-ai channel list` (show followed/muted/neutral).
- Store: add `mute`/`follow` state to the `channels` row (idempotent column
  migration via `_ensure_columns`, same pattern as SP8 video meta).
- `discover`: filter out muted `channel_id`s in the feed loop before date/dur
  filtering; count muted-skipped for the report.
- Skill: extend `yt-manager` (or a small `yt-channels` skill) with the channel
  ops so Claude Code can mute "channels I don't want anymore" by name → resolve
  to `channel_id` via the store, then `channel mute`.

**Open questions:** resolve channel by name vs id vs url; what `follow` adds
beyond the existing feed; whether muted channels' already-stored videos are
hidden from `list`/`recommend` or just excluded from future discovery.
