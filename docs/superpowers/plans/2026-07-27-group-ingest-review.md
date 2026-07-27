# Group ingest + group review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user process an arbitrary set of videos — a channel's recent uploads (optionally date-bounded), a comma list of ids/URLs, or a published-date range — and get per-video analysis plus a group synthesis. The engine gains a `channel-list` enumerator; the `yt` skill gains a "group" scenario that orchestrates ingest + per-video + synthesis.

**Architecture:** `channel-list` reuses `discovery.py`'s flat-extract machinery (`_default_extract_fn`, `_entry_to_video`, `_published_ts`) to enumerate a channel's uploads without ingesting. The `yt` skill drives ingestion (`yt-ai fetch`) and analysis (skills-primary). Comma-id parsing and id-set date-filtering are skill-side (no CLI).

**Tech Stack:** yt-dlp flat channel extraction, Typer, pytest with an injected `extract_fn` seam, the `yt` skill.

## Global Constraints

- Engine repo `yt-mem-ai` (package `yt_mem_ai`) only, plus the `yt` skill markdown.
- `channel-list` **enumerates only** — no ingest, no store writes.
- Reuse discovery helpers; do not duplicate flat-extraction or entry→Video mapping.
- Default channel cap **20** (`--limit`); date filters are `YYYY-MM-DD` string compares (matches the codebase).
- Tests offline via an injected `extract_fn` returning fake entries — no network.
- Streams are handled at fetch time (already marked/skipped); `channel-list` needs no stream logic.

---

## Task 1: `discovery.channel_videos` enumerator

**Files:**
- Modify: `yt_mem_ai/discovery.py`
- Test: `tests/test_discovery.py`

**Interfaces:**
- Produces:
  - `_channel_uploads_url(url: str) -> str` — normalize a channel URL/@handle to its `/videos` tab.
  - `channel_videos(cfg, url, limit=20, after=None, before=None, extract_fn=None) -> list[Video]` — newest-first, capped, date-filtered `[after, before]` on `published_at`.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_discovery.py` (follow its existing import/style; it already imports `Config`, `discovery`):
```python
def test_channel_uploads_url_normalizes():
    from yt_mem_ai import discovery as d
    assert d._channel_uploads_url("https://youtube.com/@chan") == "https://youtube.com/@chan/videos"
    assert d._channel_uploads_url("https://youtube.com/@chan/") == "https://youtube.com/@chan/videos"
    assert d._channel_uploads_url("https://youtube.com/@chan/videos") == "https://youtube.com/@chan/videos"
    assert d._channel_uploads_url("https://youtube.com/channel/UC123/streams") == "https://youtube.com/channel/UC123/streams"


def test_channel_videos_maps_caps_and_filters(_cfg_fixture=None):
    from yt_mem_ai import discovery as d
    from yt_mem_ai.config import Config
    from pathlib import Path
    cfg = Config(downloads_dir=Path("d"), proxy_username=None, proxy_password=None,
                 cookies_browser=None, whisper_model="s", whisper_device="cpu",
                 whisper_compute_type="int8", openrouter_api_key=None, openrouter_model="m",
                 store_path=Path("s"), embedding_backend="local", embedding_model=None,
                 chunk_target_s=45.0, openai_api_key=None)
    # newest-first fake channel: 3 entries with epoch timestamps
    entries = [
        {"id": "v3", "title": "Newest", "timestamp": 1753500000, "duration": 600},
        {"id": "v2", "title": "Middle",  "timestamp": 1753400000, "duration": 600},
        {"id": "v1", "title": "Oldest",  "timestamp": 1753300000, "duration": 600},
    ]

    def fake_extract(url, flat):
        assert url.endswith("/videos")   # normalized
        return {"entries": entries}

    got = d.channel_videos(cfg, "https://youtube.com/@chan", limit=2, extract_fn=fake_extract)
    assert [v.video_id for v in got] == ["v3", "v2"]            # newest-first, capped at 2
    assert got[0].title == "Newest" and got[0].url.endswith("v3")
    assert got[0].published_at is not None                       # date derived from timestamp

    # date filter (published_at strings)
    d3 = d.channel_videos(cfg, "https://youtube.com/@chan", limit=10,
                          after=got[0].published_at, before=got[0].published_at,
                          extract_fn=fake_extract)
    assert all(v.published_at == got[0].published_at for v in d3)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_discovery.py -q -k "channel"`
Expected: FAIL — `AttributeError: module 'yt_mem_ai.discovery' has no attribute '_channel_uploads_url'`.

- [ ] **Step 3: Implement in `discovery.py`**

Add (near the other helpers; reuses `_default_extract_fn`, `_published_ts`, `_entry_to_video`):
```python
_CHANNEL_TABS = ("/videos", "/streams", "/shorts", "/featured", "/playlists")


def _channel_uploads_url(url: str) -> str:
    """Point a channel URL / @handle at its uploads (/videos) tab."""
    stripped = url.rstrip("/")
    if any(stripped.endswith(tab) for tab in _CHANNEL_TABS):
        return stripped
    return f"{stripped}/videos"


def channel_videos(cfg: Config, url: str, limit: int = 20, after: str | None = None,
                   before: str | None = None, extract_fn=None) -> list[Video]:
    """Enumerate a channel's uploads (newest-first, capped, date-filtered). Does
    NOT ingest. `after`/`before` are inclusive YYYY-MM-DD bounds on published_at."""
    if extract_fn is None:
        extract_fn = _default_extract_fn(cfg)
    tab = _channel_uploads_url(url)
    info = extract_fn(tab, True) or {}
    entries = (info.get("entries") or [])[:limit]
    out: list[Video] = []
    for entry in entries:
        if not entry.get("id"):
            continue
        v = _entry_to_video(entry, _published_ts(entry, extract_fn))
        pub = v.published_at or ""
        if after and pub < after:
            continue
        if before and pub > before:
            continue
        out.append(v)
    return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_discovery.py -q -k "channel"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add yt_mem_ai/discovery.py tests/test_discovery.py
git commit -m "feat(discovery): channel_videos enumerator (reuses flat-extract; capped + date-filtered)"
```

---

## Task 2: CLI `channel-list`

**Files:**
- Modify: `yt_mem_ai/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `discovery.channel_videos` (Task 1).
- Produces: `run_channel_list(cfg, url, limit=20, after=None, before=None, extract_fn=None) -> list[Video]`; a Typer `channel-list` command (`--limit/-n`, `--from`, `--to`, `--json`).

- [ ] **Step 1: Write a failing test**

Append to `tests/test_cli.py`:
```python
def test_run_channel_list_delegates(tmp_path, monkeypatch):
    from yt_mem_ai import cli
    from yt_mem_ai.store.models import Video
    captured = {}

    def fake_channel_videos(cfg, url, limit=20, after=None, before=None, extract_fn=None):
        captured.update(url=url, limit=limit, after=after, before=before)
        return [Video(video_id="v3", url="https://youtu.be/v3", title="Newest",
                      published_at="2026-07-26")]

    monkeypatch.setattr(cli, "channel_videos", fake_channel_videos)
    out = cli.run_channel_list(_cfg(tmp_path), "https://youtube.com/@chan",
                               limit=5, after="2026-07-01", before="2026-07-26")
    assert [v.video_id for v in out] == ["v3"]
    assert captured == {"url": "https://youtube.com/@chan", "limit": 5,
                        "after": "2026-07-01", "before": "2026-07-26"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_cli.py -q -k run_channel_list`
Expected: FAIL — `AttributeError: module 'yt_mem_ai.cli' has no attribute 'run_channel_list'` (or `channel_videos`).

- [ ] **Step 3: Wire the CLI**

In `yt_mem_ai/cli.py`, add to the discovery import line:
```python
from .discovery import discover as discover_videos, channel_videos
```
(the existing line is `from .discovery import discover as discover_videos`.)

Add the core + command:
```python
def run_channel_list(cfg, url: str, limit: int = 20, after: str | None = None,
                     before: str | None = None, extract_fn=None) -> list[Video]:
    return channel_videos(cfg, url, limit=limit, after=after, before=before,
                          extract_fn=extract_fn)


@app.command("channel-list")
def channel_list_cmd(
    url: str = typer.Argument(..., help="Channel URL or @handle"),
    limit: int = typer.Option(20, "--limit", "-n", help="Newest N uploads"),
    from_: str = typer.Option(None, "--from", help="Only uploads on/after YYYY-MM-DD"),
    to: str = typer.Option(None, "--to", help="Only uploads on/before YYYY-MM-DD"),
    as_json: bool = typer.Option(False, "--json"),
):
    """List a channel's recent uploads (enumerate only — does not ingest)."""
    cfg = load_config()
    vids = run_channel_list(cfg, url, limit=limit, after=from_, before=to)
    if as_json:
        typer.echo(json.dumps([
            {"video_id": v.video_id, "url": v.url, "title": v.title,
             "published_at": v.published_at, "duration_s": v.duration_s} for v in vids]))
        return
    if not vids:
        typer.echo("no videos")
        return
    for v in vids:
        d = v.duration_s
        d = f"{d // 60}m" if isinstance(d, int) else "?"
        typer.echo(f"{v.published_at or '????-??-??'}  {v.video_id}  {d:>4}  {v.title or ''}")
```
Note: `run_channel_list` calls `channel_videos` as a cli module global so the test's `monkeypatch.setattr(cli, "channel_videos", ...)` intercepts it — keep the direct import.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_cli.py -q -k run_channel_list`
Expected: PASS.

- [ ] **Step 5: Full suite + lint + help**

Run: `uv run pytest -q && uv run ruff check yt_mem_ai/ && uv run yt-ai channel-list --help`
Expected: suite passes; ruff clean; `channel-list --help` shows `--limit/--from/--to/--json`.

- [ ] **Step 6: Commit**

```bash
git add yt_mem_ai/cli.py tests/test_cli.py
git commit -m "feat(cli): channel-list command + run_channel_list core"
```

---

## Task 3: `yt` skill "group" scenario + docs

**Files:**
- Modify: `skills/yt/SKILL.md`
- Modify: `.gitignore`
- Modify: `CLAUDE.md`, `README.md`

- [ ] **Step 1: Add the "group" scenario to the `yt` skill**

In `skills/yt/SKILL.md`, add to the "Pick the scenario" list a **D** entry, and a new scenario section after C. Insert into the scenario list:
```markdown
- **D — group (arbitrary set)** ("process/review these videos <ids/urls>", "review
  channel <url>", "review <channel> from <date> to <date>"): ingest a user-specified
  set, then per-video analysis + a group synthesis.
```

Add this section after the "## C — subscriptions review" section:
```markdown
## D — group of videos (arbitrary set)

Process a user-specified set (not tied to today's subscriptions), then per-video
analysis + a top-level synthesis.

1. **Resolve the set → ids/URLs:**
   - comma list (`id1,id2,https://youtu.be/id3`) → parse directly;
   - channel (URL/@handle) → `yt-ai channel-list <url> --limit N [--from D] [--to D] --json`;
   - date range over a channel → same with `--from/--to`.
   Report the resolved count first; if it's large (> ~15), say so and confirm/cap
   before mass-ingesting (whisper is slow).
2. **Ingest each:** `yt-ai fetch <url>` (captions→whisper; streams auto-marked
   `status=stream` and skipped; continue past failures — note any skipped).
3. **Per-video:** run the **core** analysis (summary + search-anchored highlights +
   Q&A, `presentation` → `slides/<id>.md` if asked), persisted via `save-summary`,
   in each video's original language (FTS-anchor non-English).
4. **Group synthesis** → `groups/<label>.md` (label = channel handle / date-range
   slug / timestamp): an executive synthesis (themes, standouts, what's worth
   watching) + one section per video (`## <title>` + link, summary, top highlights
   as `MM:SS — label`, 2–3 Q&A).
5. **Report** the `groups/<label>.md` path + the executive synthesis.

This is the daily-digest shape (B) over an arbitrary set. Use C instead for a
themes-only essay with no per-video sections.
```

Also update the skill's `description` frontmatter to mention groups (append to the existing description): ` Also processes an arbitrary group of videos (a channel's recent uploads, a comma list of ids/URLs, or a date range) into per-video analysis + a group synthesis.`

- [ ] **Step 2: gitignore `groups/`**

Append to `.gitignore`:
```
groups/
```

- [ ] **Step 3: Docs — CLAUDE.md + README**

In `CLAUDE.md`, add to the `discovery.py` module-map bullet (or after it):
```markdown
- `channel-list` (CLI) — `channel_videos` enumerates a channel's recent uploads
  (reuses discovery's flat-extract), capped + date-filtered; the `yt` skill's
  "group" scenario uses it to ingest + review an arbitrary set → `groups/<label>.md`.
```

In `README.md` Commands block, add after `yt-ai reembed`:
```
yt-ai channel-list <url>     # list a channel's recent uploads (--limit/--from/--to/--json); enumerate only
```

- [ ] **Step 4: Commit**

```bash
git add skills/yt/SKILL.md .gitignore CLAUDE.md README.md
git commit -m "feat(skill+docs): yt group scenario + channel-list docs; gitignore groups/"
```

---

## Self-Review notes

- **Coverage:** `channel_videos` map/cap/filter + URL normalize (T1), CLI core delegation + command (T2), skill scenario + gitignore + docs (T3). The channel enumeration's real network path is manual smoke (offline tests use the injected `extract_fn`).
- **Interfaces consistent:** `channel_videos(cfg, url, limit, after, before, extract_fn)` identical in T1 impl and T2 caller; `run_channel_list` mirrors the same signature and calls `channel_videos` as a cli module global (monkeypatchable).
- **Reuse:** `_default_extract_fn`/`_entry_to_video`/`_published_ts` reused, not duplicated (Global Constraints). Known limit: `_default_extract_fn` caps pagination at `discover_feed_limit` (60); `--limit` above that needs `YT_DISCOVER_FEED_LIMIT` raised — note in docs if it matters.
- **Skill not unit-tested** (it's markdown), but the `channel-list` seam it depends on is.
