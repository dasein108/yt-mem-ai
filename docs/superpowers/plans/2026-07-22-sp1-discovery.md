# SP1 Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `yt-ai discover` — list new subscription uploads after a cutoff date and store them as `status="discovered"` videos (metadata only), as a daily routine feeding `fetch`/SP2.

**Architecture:** A new `discovery.py` extracts the subscriptions feed via yt-dlp (proxy+cookies, reusing `build_opts`), through an injectable `extract_fn` seam so tests run offline with fake entry dicts. It iterates each source newest-first, resolves each entry's publish date (from the entry, else a cheap per-video fallback), stops per-source once older than the cutoff, drops sub-min-duration videos (keeps live/unknown-duration), and maps to `Video(status="discovered")`. The CLI resolves the cutoff (`--after` → stored `last_discover_at` → now−7d), writes channels + videos with an **insert-only** merge so already-fetched videos are never downgraded, and advances `last_discover_at` only on success.

**Tech Stack:** Python 3.11+, yt-dlp, LanceDB, Typer, pytest, uv.

## Global Constraints

- Python 3.11+, `X | None` unions. uv; console script `yt-ai`.
- Store handle is `db` (`lancedb.DBConnection`); reuse `store` (`yt_summary.store.db`), `memory`, existing `get_state`/`set_state`.
- **Dedup is insert-only:** `insert_discovered_video` uses `merge_insert("video_id").when_not_matched_insert_all().execute([...])` with NO `when_matched_update_all()` — an existing video row (any status) is left untouched.
- **Cutoff precedence:** `--after` (YYYY-MM-DD) → `get_state(db,"last_discover_at")` → `(today − 7 days).isoformat()`. Dates are `"YYYY-MM-DD"` strings; string comparison is the date comparison. `last_discover_at` is stored as a date-only isoformat and advanced ONLY after a successful discover.
- **Duration filter:** drop entries with `duration_s is not None and duration_s < min_duration`; keep `None`-duration (live/upcoming). Default `min_duration=120`.
- **Offline tests:** `discovery.discover` takes an injectable `extract_fn(url, flat) -> dict`; unit tests pass a fake. CLI `run_discover` tests monkeypatch `cli.discover_videos`. No network in the unit suite.
- `published_at` stored as `"YYYY-MM-DD"` (SP0 convention). `fetched_at` is `datetime.now(UTC).isoformat()`.
- Every task ends green (`uv run pytest -q`) and `uv run --with ruff ruff check .` clean, `-W error::DeprecationWarning` clean, and is committed.

---

## File Structure

```
yt_summary/
  discovery.py   NEW: FEED_URL/CHANNELS_URL, discover(), helpers
  store/db.py    + upsert_channel, insert_discovered_video
  cli.py         + discover_videos import, run_discover, discover command
tests/
  test_discovery.py   NEW
  test_db.py          + channel/discovered-video tests
  test_cli.py         + run_discover tests
README.md             + discover section
```

---

## Task 1: Store — upsert_channel + insert_discovered_video (insert-only)

**Files:**
- Modify: `yt_summary/store/db.py` (append)
- Test: `tests/test_db.py` (append)

**Interfaces:**
- Consumes: `Video`, `_video_to_row` (Task-4 SP0.5 helper), `merge_insert`.
- Produces:
  - `upsert_channel(db, channel_id, title=None, subscribed=1) -> None` (merge_insert update on channel_id).
  - `insert_discovered_video(db, v: Video) -> None` (insert-only merge on video_id).

- [ ] **Step 1: Write the failing test (append to `tests/test_db.py`)**

```python
def test_upsert_channel_roundtrip(tmp_path):
    conn = _db(tmp_path)
    store.upsert_channel(conn, "chan1", "Cool Channel", 1)
    rows = conn.open_table("channels").search().where("channel_id = 'chan1'").limit(1).to_list()
    assert rows and rows[0]["title"] == "Cool Channel" and rows[0]["subscribed"] == 1


def test_insert_discovered_video_inserts_new(tmp_path):
    conn = _db(tmp_path)
    store.insert_discovered_video(conn, Video(video_id="v1", url="u", title="T",
                                              status="discovered", published_at="2026-07-20"))
    got = store.get_video(conn, "v1")
    assert got is not None and got.status == "discovered" and got.title == "T"


def test_insert_discovered_video_does_not_downgrade(tmp_path):
    conn = _db(tmp_path)
    # already fetched/transcribed
    store.upsert_video(conn, Video(video_id="v1", url="u", title="T", status="transcribed"))
    # re-discovered
    store.insert_discovered_video(conn, Video(video_id="v1", url="u", title="T",
                                              status="discovered"))
    assert store.get_video(conn, "v1").status == "transcribed"  # unchanged
    assert len(store.list_videos(conn)) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_db.py -q`
Expected: FAIL (`AttributeError: upsert_channel`)

- [ ] **Step 3: Append to `yt_summary/store/db.py`**

```python
def upsert_channel(db, channel_id: str, title: str | None = None, subscribed: int = 1) -> None:
    tbl = db.open_table("channels")
    tbl.merge_insert("channel_id") \
        .when_matched_update_all() \
        .when_not_matched_insert_all() \
        .execute([{"channel_id": channel_id, "title": title, "subscribed": subscribed}])


def insert_discovered_video(db, v: Video) -> None:
    tbl = db.open_table("videos")
    tbl.merge_insert("video_id") \
        .when_not_matched_insert_all() \
        .execute([_video_to_row(v)])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_db.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add yt_summary/store/db.py tests/test_db.py
git commit -m "feat: upsert_channel + insert-only discovered video"
```

---

## Task 2: discovery.py — feed extraction, date resolution, filtering

**Files:**
- Create: `yt_summary/discovery.py`
- Test: `tests/test_discovery.py`

**Interfaces:**
- Consumes: `Config`, `build_opts` (from `download.py`), `Video`.
- Produces:
  - `discover(cfg, after, deep=False, min_duration=120, extract_fn=None) -> list[Video]`.
  - Module constants `FEED_URL`, `CHANNELS_URL`.
  - `extract_fn(url: str, flat: bool) -> dict` seam (default built from cfg via yt-dlp).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_discovery.py
from pathlib import Path
from yt_summary.config import Config
from yt_summary import discovery


def _cfg():
    return Config(downloads_dir=Path("dl"), proxy_username=None, proxy_password=None,
                  cookies_browser=None, whisper_model="small", whisper_device="cpu",
                  whisper_compute_type="int8", openrouter_api_key=None,
                  store_path=Path("lance"), embedding_backend="local", embedding_model=None,
                  chunk_target_s=45.0, openai_api_key=None)


def _feed(entries):
    """Return a fake extract_fn serving a subscriptions feed of `entries`."""
    def extract_fn(url, flat):
        if url == discovery.FEED_URL:
            return {"entries": entries}
        # per-video fallback keyed by id in the url
        for e in entries:
            if e["id"] in url:
                return e
        return {}
    return extract_fn


def test_discover_filters_by_date_and_stops():
    entries = [
        {"id": "new1", "title": "New", "duration": 600, "channel_id": "c", "upload_date": "20260721"},
        {"id": "new2", "title": "New2", "duration": 600, "channel_id": "c", "upload_date": "20260720"},
        {"id": "old1", "title": "Old", "duration": 600, "channel_id": "c", "upload_date": "20260701"},
        {"id": "old2", "title": "Older", "duration": 600, "channel_id": "c", "upload_date": "20260601"},
    ]
    out = discovery.discover(_cfg(), after="2026-07-15", extract_fn=_feed(entries))
    ids = [v.video_id for v in out]
    assert ids == ["new1", "new2"]  # stops at first older-than-cutoff
    assert out[0].status == "discovered"
    assert out[0].published_at == "2026-07-21"
    assert out[0].channel_id == "c"


def test_discover_drops_short_keeps_live():
    entries = [
        {"id": "short", "title": "S", "duration": 30, "channel_id": "c", "upload_date": "20260721"},
        {"id": "live", "title": "L", "duration": None, "channel_id": "c", "upload_date": "20260721"},
        {"id": "long", "title": "Lo", "duration": 300, "channel_id": "c", "upload_date": "20260721"},
    ]
    out = discovery.discover(_cfg(), after="2026-07-01", min_duration=120, extract_fn=_feed(entries))
    ids = [v.video_id for v in out]
    assert "short" not in ids
    assert "live" in ids and "long" in ids


def test_discover_uses_timestamp_then_fallback():
    # entry with neither date field triggers a per-video fallback lookup
    entries = [{"id": "vid", "title": "T", "duration": 600, "channel_id": "c"}]
    def extract_fn(url, flat):
        if url == discovery.FEED_URL:
            return {"entries": entries}
        return {"id": "vid", "upload_date": "20260721"}  # fallback provides the date
    out = discovery.discover(_cfg(), after="2026-07-01", extract_fn=extract_fn)
    assert out and out[0].published_at == "2026-07-21"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_discovery.py -q`
Expected: FAIL (`ModuleNotFoundError: yt_summary.discovery`)

- [ ] **Step 3: Implement `yt_summary/discovery.py`**

```python
# yt_summary/discovery.py
from __future__ import annotations
from datetime import datetime, UTC
from .config import Config
from .download import build_opts
from .store.models import Video

FEED_URL = "https://www.youtube.com/feed/subscriptions"
CHANNELS_URL = "https://www.youtube.com/feed/channels"


def _default_extract_fn(cfg: Config):
    from yt_dlp import YoutubeDL
    base = build_opts(cfg, download_audio=False)

    def extract_fn(url: str, flat: bool) -> dict:
        opts = dict(base)
        opts["skip_download"] = True
        opts["extract_flat"] = "in_playlist" if flat else False
        with YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False) or {}

    return extract_fn


def _to_date(value) -> str | None:
    """Convert a yt-dlp timestamp (epoch) or upload_date (YYYYMMDD) to YYYY-MM-DD."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, UTC).strftime("%Y-%m-%d")
    text = str(value)
    if len(text) == 8 and text.isdigit():
        return datetime.strptime(text, "%Y%m%d").strftime("%Y-%m-%d")
    return None


def _published_date(entry: dict, extract_fn) -> str | None:
    pub = _to_date(entry.get("timestamp")) or _to_date(entry.get("upload_date"))
    if pub:
        return pub
    url = entry.get("url") or entry.get("webpage_url")
    if not url:
        return None
    info = extract_fn(url, False) or {}
    return _to_date(info.get("timestamp")) or _to_date(info.get("upload_date"))


def _entry_to_video(entry: dict, published_at: str | None) -> Video:
    vid = entry["id"]
    url = entry.get("url") or entry.get("webpage_url") or f"https://www.youtube.com/watch?v={vid}"
    return Video(
        video_id=vid,
        url=url,
        channel_id=entry.get("channel_id"),
        title=entry.get("title"),
        duration_s=entry.get("duration"),
        published_at=published_at,
        fetched_at=datetime.now(UTC).isoformat(),
        status="discovered",
    )


def _sources(extract_fn, deep: bool) -> list[list[dict]]:
    feed = extract_fn(FEED_URL, True) or {}
    sources = [feed.get("entries") or []]
    if deep:
        chans = extract_fn(CHANNELS_URL, True) or {}
        for c in (chans.get("entries") or []):
            url = c.get("url")
            if not url and c.get("id"):
                url = f"https://www.youtube.com/channel/{c['id']}/videos"
            if not url:
                continue
            try:
                cvids = extract_fn(url, True) or {}
                sources.append(cvids.get("entries") or [])
            except Exception:
                continue  # best-effort per channel
    return sources


def discover(cfg: Config, after: str, deep: bool = False,
             min_duration: int = 120, extract_fn=None) -> list[Video]:
    if extract_fn is None:
        extract_fn = _default_extract_fn(cfg)
    out: list[Video] = []
    for entries in _sources(extract_fn, deep):
        for entry in entries:
            pub = _published_date(entry, extract_fn)
            if pub is not None and pub < after:
                break  # source is newest-first: the rest are older
            dur = entry.get("duration")
            if dur is not None and dur < min_duration:
                continue
            out.append(_entry_to_video(entry, pub))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_discovery.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add yt_summary/discovery.py tests/test_discovery.py
git commit -m "feat: subscription discovery (feed extract, date/duration filter)"
```

---

## Task 3: CLI — run_discover + discover command

**Files:**
- Modify: `yt_summary/cli.py`
- Test: `tests/test_cli.py` (append)

**Interfaces:**
- Consumes: `discovery.discover` (imported as `discover_videos`), `store` (`get_state`/`set_state`/`get_video`/`upsert_channel`/`insert_discovered_video`), `open_store`.
- Produces:
  - `run_discover(cfg, after=None, deep=False, min_duration=120, db=None) -> tuple[list[Video], int]` returning `(discovered, new_count)`.
  - `discover` Typer command: `--after`, `--deep`, `--min-duration 120`, `--json`.

- [ ] **Step 1: Write the failing test (append to `tests/test_cli.py`)**

```python
def test_run_discover_writes_and_advances_state(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)
    monkeypatch.setattr(cli, "discover_videos",
        lambda cfg, after, deep=False, min_duration=120: [
            Video(video_id="v1", url="u1", channel_id="c1", title="A", status="discovered", published_at="2026-07-21"),
            Video(video_id="v2", url="u2", channel_id="c1", title="B", status="discovered", published_at="2026-07-20"),
        ])
    discovered, new = cli.run_discover(cfg, after="2026-07-01", db=conn)
    assert new == 2
    assert store.get_video(conn, "v1").status == "discovered"
    assert store.get_state(conn, "last_discover_at") is not None


def test_run_discover_reports_known_and_no_downgrade(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)
    store.upsert_video(conn, Video(video_id="v1", url="u1", status="transcribed"))
    monkeypatch.setattr(cli, "discover_videos",
        lambda cfg, after, deep=False, min_duration=120: [
            Video(video_id="v1", url="u1", channel_id="c1", status="discovered"),
            Video(video_id="v2", url="u2", channel_id="c1", status="discovered", published_at="2026-07-20"),
        ])
    discovered, new = cli.run_discover(cfg, after="2026-07-01", db=conn)
    assert new == 1                                   # only v2 is new
    assert store.get_video(conn, "v1").status == "transcribed"  # not downgraded


def test_run_discover_cutoff_precedence(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)
    store.set_state(conn, "last_discover_at", "2026-07-10")
    captured = {}
    def fake(cfg, after, deep=False, min_duration=120):
        captured["after"] = after
        return []
    monkeypatch.setattr(cli, "discover_videos", fake)
    cli.run_discover(cfg, after=None, db=conn)       # no --after → use stored state
    assert captured["after"] == "2026-07-10"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -q`
Expected: FAIL (`AttributeError: run_discover` / `discover_videos`)

- [ ] **Step 3: Add to `yt_summary/cli.py`**

Add the import near the other imports:
```python
from datetime import date, timedelta
from .discovery import discover as discover_videos
```

Add the core + command:
```python
def run_discover(cfg, after: str | None = None, deep: bool = False,
                 min_duration: int = 120, db=None) -> tuple[list, int]:
    if db is None:
        db = open_store(cfg)
    cutoff = after or store.get_state(db, "last_discover_at") \
        or (date.today() - timedelta(days=7)).isoformat()
    discovered = discover_videos(cfg, cutoff, deep=deep, min_duration=min_duration)
    new_count = 0
    for v in discovered:
        if store.get_video(db, v.video_id) is None:
            new_count += 1
        if v.channel_id:
            store.upsert_channel(db, v.channel_id, None, 1)
        store.insert_discovered_video(db, v)
    store.set_state(db, "last_discover_at", date.today().isoformat())
    return discovered, new_count


@app.command()
def discover(
    after: str = typer.Option(None, "--after", help="Only videos published on/after YYYY-MM-DD"),
    deep: bool = typer.Option(False, "--deep", help="Enumerate subscribed channels for backfill"),
    min_duration: int = typer.Option(120, "--min-duration", help="Skip videos shorter than N seconds"),
    as_json: bool = typer.Option(False, "--json"),
):
    """List new subscription uploads after a cutoff and store them as 'discovered'."""
    cfg = load_config()
    discovered, new_count = run_discover(cfg, after=after, deep=deep, min_duration=min_duration)
    if as_json:
        typer.echo(json.dumps([
            {"video_id": v.video_id, "title": v.title, "url": v.url,
             "channel_id": v.channel_id, "duration_s": v.duration_s,
             "published_at": v.published_at} for v in discovered]))
        return
    if not discovered:
        typer.echo("no new videos")
        return
    for v in discovered:
        dur = f"{(v.duration_s or 0) // 60}m" if v.duration_s else "live"
        typer.echo(f"{v.published_at or '????-??-??'}  {(v.title or '')[:60]:60}  {dur:>5}  {v.url}")
    typer.echo(f"\n{new_count} new / {len(discovered) - new_count} already known")
```

- [ ] **Step 4: Run tests + smoke**

Run: `uv run pytest tests/test_cli.py -q` → PASS
Run: `uv run pytest -q` → full suite PASS; also `-W error::DeprecationWarning` clean.
Run: `uv run yt-ai --help` → confirm `discover` listed. Report output.

- [ ] **Step 5: Commit**

```bash
git add yt_summary/cli.py tests/test_cli.py
git commit -m "feat: yt-ai discover command"
```

---

## Task 4: Docs + final sweep

**Files:**
- Modify: `README.md`
- Report: roadmap memory update (controller applies — memory is outside the repo)

**Interfaces:** none (docs + verification).

- [ ] **Step 1: Add `discover` to `README.md`**

In the Commands section, add:
```markdown
yt-ai discover               # list new subscription uploads (daily routine)
                             #   --after YYYY-MM-DD | --deep | --min-duration N | --json
```
And a short note:
```markdown
## Daily routine

`yt-ai discover` lists subscription uploads published since your last run
(first run defaults to the last 7 days), storing them as `discovered`. It never
downloads or re-touches videos you've already fetched. Pipe `--json` into your
own loop to batch-`fetch` the ones you want.
```

- [ ] **Step 2: Full suite + lint + smoke**

Run: `uv run pytest -q` → all PASS (+1 skipped integration).
Run: `uv run --with ruff ruff check .` → clean.
Run: `uv run yt-ai discover --help` → shows `--after/--deep/--min-duration/--json`; report output.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document yt-ai discover"
```

- [ ] **Step 4: Report roadmap-memory update to the controller**

Report that the roadmap memory (`sp-roadmap-and-stack`, outside the repo) should mark SP1 done: `discover` lists subscription uploads after a cutoff (since-last-run/`--after`/7d default), insert-only dedup, `--json` feeds SP2. Note SP2 can now consume `yt-ai discover --json`.

---

## Self-Review Notes

- **Spec coverage:** discover+list-only command (T3), feed source + `--deep` (T2 `_sources`), cutoff precedence after>state>7d (T3 `run_discover`), min-duration filter keeping live (T2), `--json` output (T3), insert-only no-downgrade dedup (T1 + tested), `last_discover_at` advances only on success (T3 — after the write loop), README + memory (T4). Integration with real cookies is manual-only per spec (out of automated scope).
- **Placeholder scan:** none — every code step is complete.
- **Type/name consistency:** `discover(cfg, after, deep, min_duration, extract_fn)` in `discovery.py` matches `run_discover`'s `discover_videos(cfg, cutoff, deep=, min_duration=)` call (imported alias). `insert_discovered_video`/`upsert_channel` signatures match their `run_discover` calls. `_video_to_row` reused from the SP0.5 store. `Video(status="discovered")` shape consistent with `VideoSchema`.
- **Robustness choice:** the spec mentioned yt-dlp `break_on_reject`; the plan instead resolves dates per-entry and breaks per-source in Python (flat entries lack reliable dates and `break_on_reject` semantics are fragile). Same observable behavior (stop past the cutoff), more robust and fully offline-testable.
- **`extract_fn` seam:** `discover` is offline-tested via injected `extract_fn`; `run_discover` is offline-tested by monkeypatching `cli.discover_videos`. No network in the unit suite.
