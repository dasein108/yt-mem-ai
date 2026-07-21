# YouTube Summary — Foundation (SP0) Design

**Date:** 2026-07-21
**Status:** Approved (brainstorming complete)

## Vision

Developer-first tool that ingests YouTube videos from subscriptions, produces
transcripts, and lets Claude Code skills generate summaries / highlights / Q&A.
Stage 1 = Python CLI + Claude Code skills. Later stages add discovery automation,
recommendations, a Tauri+React frontend, and highlight compilation.

## Locked Decisions

| Concern | Choice | Rationale |
|---|---|---|
| Backend | Python | Native whisper/yt-dlp/ffmpeg; best ML ecosystem |
| Discovery + download | yt-dlp, cookies-only | No Google Cloud/OAuth setup, no quota |
| Scrape reliability | Webshare rotating residential proxy | Dodges YouTube IP blocks on scrape/caption calls |
| Transcript | youtube-transcript-api first → faster-whisper fallback | Fast/free when captions exist; portable whisper engine |
| Audio | ffmpeg | bestaudio → mp3 |
| Storage | SQLite | Metadata + transcript text + skill outputs |
| Intelligence | Claude Code **skills** (primary), OpenRouter (optional) | No API cost, higher quality, interactive |
| CLI framework | Typer | Type-hint based, autocompletion, low boilerplate |
| Frontend | Tauri + React | Deferred to SP4 |

## Secrets Handling

Webshare proxy creds + any API keys live in `.env` (gitignored). Never hardcoded,
never committed. `config.py` loads them. Note: proxy creds shared in chat are
considered exposed — rotate if this repo/log ever goes anywhere shared.

## Roadmap (Decomposition)

Each sub-project gets its own spec → plan → build cycle.

- **SP0 FOUNDATION (this spec):** single-video pipeline url → meta+audio →
  transcript → SQLite. Proxy + cookies infra. Dedup memory. `summarize-video` skill.
- **SP1 DISCOVERY:** list subscription uploads after `[date]`; daily routine; feeds SP0.
- **SP2 DAILY DIGEST:** batch SP0 over today's discovered videos; digest + per-video Q&A skill.
- **SP3 RECOMMENDATIONS:** like/dislike CLI → embeddings (openai|local) → ranked suggestions.
- **SP4 FRONTEND:** Tauri + React over SQLite/CLI.
- **SP5 HIGHLIGHT COMPILATION (future):** timestamped highlights → ffmpeg supercut, 5h → ~20min + refs.

## SP0 Architecture

Isolated modules, each with one job:

```
yt_summary/
  config.py      env load (.env): proxy creds, cookie path, keys
  proxy.py       Webshare rotating proxy → yt-dlp + transcript-api
  cookies.py     Chrome cookie export/locate for yt-dlp
  discovery.py   stub in SP0, real in SP1
  download.py    yt-dlp: fetch metadata + bestaudio → mp3 via ffmpeg
  transcript/
    captions.py  youtube-transcript-api (proxied)
    whisper.py   faster-whisper fallback
    __init__.py  orchestrator: try captions → fallback
  store/
    db.py        SQLite schema + connection
    models.py    Video, Transcript, Segment, Feedback dataclasses
  memory.py      dedup: "already downloaded?" by video_id
  cli.py         Typer commands
skills/
  summarize-video/   Claude Code skill: reads transcript from SQLite,
                     emits summary + highlights + Q&A, writes back
```

### CLI Surface (SP0)

```
yt-ai fetch <url>        # meta + audio + transcript → SQLite, skip if seen
yt-ai transcript <url>   # transcript only
yt-ai show <video_id>    # dump stored data
yt-ai status             # what's in DB
```

### Data Flow

```
url
 └─ download.py      → metadata + bestaudio→mp3
     └─ transcript/  → captions.py (proxied) OR whisper.py fallback → text + segments
         └─ store/   → videos, transcripts, segments rows
             └─ memory marks video_id seen (status=transcribed)

then in Claude Code:
  summarize-video skill  → reads transcript for video_id → summary/highlights/Q&A → summaries row
```

### Error Handling

- Network/scrape failures: retry via rotating proxy; surface clear error, mark
  `status` unchanged so re-run resumes.
- No captions: automatic whisper fallback (logged as `source=whisper`).
- Restricted/age-gated video: use Chrome cookies; if still blocked, report and skip.
- Idempotency: `fetch` on a seen `video_id` is a no-op unless `--force`.

### Testing

- Unit: transcript orchestrator (captions success, captions-empty→whisper), memory
  dedup, config env parsing. Mock network/yt-dlp/proxy.
- Integration: one real short public video end-to-end (opt-in, network-gated).
- Schema: migrations create clean DB; inserts round-trip via models.

## SQLite Schema

```sql
channels(
  channel_id    TEXT PRIMARY KEY,
  title         TEXT,
  subscribed    INTEGER DEFAULT 0        -- 1 = from my subs (SP1)
)

videos(
  video_id      TEXT PRIMARY KEY,        -- yt id, natural dedup key
  channel_id    TEXT REFERENCES channels,
  title         TEXT,
  url           TEXT,
  duration_s    INTEGER,
  published_at  TEXT,                    -- ISO8601, for "after [date]"
  fetched_at    TEXT,
  audio_path    TEXT,                    -- null if audio deleted/never dl
  status        TEXT                     -- discovered|downloaded|transcribed|summarized
)

transcripts(
  video_id      TEXT PRIMARY KEY REFERENCES videos,
  source        TEXT,                    -- captions|whisper
  lang          TEXT,
  full_text     TEXT,
  created_at    TEXT
)

segments(
  id            INTEGER PRIMARY KEY,
  video_id      TEXT REFERENCES videos,
  start_s       REAL,
  end_s         REAL,
  text          TEXT
)

summaries(
  video_id      TEXT PRIMARY KEY REFERENCES videos,
  summary_md    TEXT,                    -- executive + bullets
  highlights    TEXT,                    -- json: [{start_s, label}]
  qa            TEXT,                    -- json: [{q, a}]
  model         TEXT,                    -- 'claude-code-skill' | openrouter model
  created_at    TEXT
)

feedback(
  video_id      TEXT REFERENCES videos,
  signal        INTEGER,                 -- +1 like / -1 dislike
  created_at    TEXT,
  PRIMARY KEY(video_id, created_at)
)
-- embeddings deferred to SP3 (separate table or vector store)
```

### Schema Rationale

- `video_id` = natural dedup key; feature "remember downloaded" = row existence check.
- `status` drives pipeline state and resumability.
- `segments` timestamped from the start so highlights (SP0/SP2) and compilation (SP5)
  get data for free.
- JSON blobs for skill outputs keep schema stable as summary format evolves.
