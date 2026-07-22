# SP2 Daily Digest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Batch-fetch a day's discovered videos (`fetch-pending`, continue-on-error), expose a `list` query, and add a `daily-digest` skill that turns them into per-video summaries + a dated digest — plus comprehensive project documentation (README + LLM instructions).

**Architecture:** Two thin CLI cores over the existing LanceDB store — `run_list` (query by status/date) and `run_fetch_pending` (select `discovered` videos and reuse `run_fetch` per video, catching per-video failures). Intelligence stays skills-primary: `daily-digest` reads `yt-ai list --json`, summarizes each video via the CLI (`show`/`search`/`save-summary`), and writes `digests/YYYY-MM-DD.md`. Documentation (README + a project `CLAUDE.md`) is treated as a first-class deliverable.

**Tech Stack:** Python 3.11+, LanceDB, Typer, pytest, uv.

## Global Constraints

- Python 3.11+, `X | None` unions. uv; console script `yt-ai`.
- Store handle is `db`; reuse `store` (`yt_summary.store.db`), `run_fetch`, `open_store`, `_safe`.
- Selection keys on `status` + `published_at` (ISO `YYYY-MM-DD` strings; string compare is date compare). `fetch-pending` `--since` defaults to `date.today().isoformat()`.
- `fetch-pending` is **continue-on-error**: each video runs under `try/except`, a failure is recorded as `"failed: <msg>"`, the batch never aborts. Reuse `run_fetch` (idempotent + status-based `is_seen`, so already-transcribed videos are skipped).
- `list_videos_by_status`/queries interpolate `status` through `_safe(...)`.
- Offline tests: `run_fetch_pending` tests monkeypatch `cli.run_fetch`; store tests use temp-dir LanceDB + fake embedder. No network in the unit suite.
- Documentation is a deliverable, not an afterthought: README covers every command; a project-level `CLAUDE.md` gives future LLM sessions the architecture, store schema, conventions, and skill catalog.
- Every task ends green (`uv run pytest -q`), `uv run --with ruff ruff check .` clean, `-W error::DeprecationWarning` clean, and is committed.

---

## File Structure

```
yt_summary/
  store/db.py    + list_videos_by_status(db, status, since=None, limit=None)
  cli.py         + run_list + list command; + run_fetch_pending + fetch-pending command
skills/
  daily-digest/SKILL.md   NEW (comprehensive)
CLAUDE.md        NEW — project LLM instructions
README.md        expanded (all commands + 3-step daily routine + architecture)
.gitignore       + digests/
tests/
  test_db.py     + list_videos_by_status tests
  test_cli.py    + run_list + run_fetch_pending tests
```

---

## Task 1: Store — list_videos_by_status

**Files:**
- Modify: `yt_summary/store/db.py` (append)
- Test: `tests/test_db.py` (append)

**Interfaces:**
- Produces: `list_videos_by_status(db, status, since=None, limit=None) -> list[Video]` — status filter (via `_safe`), optional `published_at >= since` lower bound, sorted `published_at` desc, optional `limit`.

- [ ] **Step 1: Write the failing test (append to `tests/test_db.py`)**

```python
def test_list_videos_by_status_filters_and_orders(tmp_path):
    conn = _db(tmp_path)
    store.upsert_video(conn, Video(video_id="a", url="u", status="discovered", published_at="2026-07-20"))
    store.upsert_video(conn, Video(video_id="b", url="u", status="discovered", published_at="2026-07-22"))
    store.upsert_video(conn, Video(video_id="c", url="u", status="transcribed", published_at="2026-07-22"))
    got = store.list_videos_by_status(conn, "discovered")
    assert [v.video_id for v in got] == ["b", "a"]  # desc by published_at, status-filtered


def test_list_videos_by_status_since_and_limit(tmp_path):
    conn = _db(tmp_path)
    store.upsert_video(conn, Video(video_id="a", url="u", status="discovered", published_at="2026-07-18"))
    store.upsert_video(conn, Video(video_id="b", url="u", status="discovered", published_at="2026-07-21"))
    store.upsert_video(conn, Video(video_id="c", url="u", status="discovered", published_at="2026-07-22"))
    since = store.list_videos_by_status(conn, "discovered", since="2026-07-20")
    assert [v.video_id for v in since] == ["c", "b"]        # a (07-18) excluded
    limited = store.list_videos_by_status(conn, "discovered", limit=1)
    assert [v.video_id for v in limited] == ["c"]           # newest only
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_db.py -q`
Expected: FAIL (`AttributeError: list_videos_by_status`)

- [ ] **Step 3: Append to `yt_summary/store/db.py`**

```python
def list_videos_by_status(db, status: str, since: str | None = None,
                          limit: int | None = None) -> list[Video]:
    tbl = db.open_table("videos")
    rows = tbl.search().where(f"status = '{_safe(status)}'").limit(1_000_000).to_list()
    if since is not None:
        rows = [r for r in rows if (r.get("published_at") or "") >= since]
    rows.sort(key=lambda d: (d.get("published_at") or ""), reverse=True)
    if limit is not None:
        rows = rows[:limit]
    return [_row_to_video(d) for d in rows]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_db.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add yt_summary/store/db.py tests/test_db.py
git commit -m "feat: list_videos_by_status store query"
```

---

## Task 2: CLI — `list` command

**Files:**
- Modify: `yt_summary/cli.py`
- Test: `tests/test_cli.py` (append)

**Interfaces:**
- Produces:
  - `run_list(cfg, status=None, since=None, db=None) -> list[Video]`.
  - `list` Typer command: `--status`, `--since`, `--json`.

- [ ] **Step 1: Write the failing test (append to `tests/test_cli.py`)**

```python
def test_run_list_by_status(tmp_path):
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)
    store.upsert_video(conn, Video(video_id="a", url="u", status="discovered", published_at="2026-07-20"))
    store.upsert_video(conn, Video(video_id="b", url="u", status="transcribed", published_at="2026-07-22"))
    got = cli.run_list(cfg, status="discovered", db=conn)
    assert [v.video_id for v in got] == ["a"]


def test_run_list_all_with_since(tmp_path):
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)
    store.upsert_video(conn, Video(video_id="a", url="u", status="discovered", published_at="2026-07-18"))
    store.upsert_video(conn, Video(video_id="b", url="u", status="transcribed", published_at="2026-07-22"))
    got = cli.run_list(cfg, since="2026-07-20", db=conn)
    assert [v.video_id for v in got] == ["b"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -q`
Expected: FAIL (`AttributeError: run_list`)

- [ ] **Step 3: Add to `yt_summary/cli.py`**

```python
def run_list(cfg, status: str | None = None, since: str | None = None, db=None) -> list[Video]:
    if db is None:
        db = open_store(cfg)
    if status:
        return store.list_videos_by_status(db, status, since=since)
    videos = store.list_videos(db)
    if since is not None:
        videos = [v for v in videos if (v.published_at or "") >= since]
    return videos


@app.command("list")
def list_videos_cmd(
    status: str = typer.Option(None, "--status", help="Filter by status (discovered/transcribed/...)"),
    since: str = typer.Option(None, "--since", help="Only videos published on/after YYYY-MM-DD"),
    as_json: bool = typer.Option(False, "--json"),
):
    """List stored videos, optionally filtered by status/date."""
    cfg = load_config()
    videos = run_list(cfg, status=status, since=since)
    if as_json:
        typer.echo(json.dumps([
            {"video_id": v.video_id, "title": v.title, "url": v.url, "status": v.status,
             "published_at": v.published_at, "duration_s": v.duration_s} for v in videos]))
        return
    if not videos:
        typer.echo("no videos")
        return
    for v in videos:
        typer.echo(f"{v.published_at or '????-??-??'}  {v.status or '?':12}  {(v.title or '')[:50]:50}  {v.url}")
```

Note: the command function is named `list_videos_cmd` but registered as `list` via `@app.command("list")` to avoid shadowing the builtin.

- [ ] **Step 4: Run tests + smoke**

Run: `uv run pytest tests/test_cli.py -q` → PASS
Run: `uv run yt-ai list --help` → shows `--status/--since/--json`. Report output.

- [ ] **Step 5: Commit**

```bash
git add yt_summary/cli.py tests/test_cli.py
git commit -m "feat: yt-ai list command"
```

---

## Task 3: CLI — `fetch-pending` (batch, continue-on-error)

**Files:**
- Modify: `yt_summary/cli.py`
- Test: `tests/test_cli.py` (append)

**Interfaces:**
- Produces:
  - `run_fetch_pending(cfg, since=None, limit=None, db=None) -> list[tuple[str, str]]` returning `(video_id, outcome)` where outcome is `"ok"` or `"failed: <msg>"`.
  - `fetch-pending` Typer command: `--since`, `--limit`.

- [ ] **Step 1: Write the failing test (append to `tests/test_cli.py`)**

```python
def test_run_fetch_pending_continue_on_error(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)
    store.upsert_video(conn, Video(video_id="ok1", url="u1", status="discovered", published_at="2026-07-22"))
    store.upsert_video(conn, Video(video_id="bad", url="u2", status="discovered", published_at="2026-07-22"))
    store.upsert_video(conn, Video(video_id="ok2", url="u3", status="discovered", published_at="2026-07-22"))

    def fake_run_fetch(url, cfg, force=False, db=None, video_id=None):
        if video_id == "bad":
            raise RuntimeError("blocked")
        return video_id
    monkeypatch.setattr(cli, "run_fetch", fake_run_fetch)

    results = cli.run_fetch_pending(cfg, since="2026-07-01", db=conn)
    outcomes = dict(results)
    assert outcomes["ok1"] == "ok" and outcomes["ok2"] == "ok"
    assert outcomes["bad"].startswith("failed:")            # captured, batch continued
    assert len(results) == 3


def test_run_fetch_pending_since_and_limit(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)
    store.upsert_video(conn, Video(video_id="old", url="u", status="discovered", published_at="2026-07-01"))
    store.upsert_video(conn, Video(video_id="new1", url="u", status="discovered", published_at="2026-07-22"))
    store.upsert_video(conn, Video(video_id="new2", url="u", status="discovered", published_at="2026-07-21"))
    monkeypatch.setattr(cli, "run_fetch", lambda url, cfg, force=False, db=None, video_id=None: video_id)

    results = cli.run_fetch_pending(cfg, since="2026-07-10", limit=1, db=conn)
    assert [vid for vid, _ in results] == ["new1"]          # since excludes old, limit=1 keeps newest
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -q`
Expected: FAIL (`AttributeError: run_fetch_pending`)

- [ ] **Step 3: Add to `yt_summary/cli.py`**

```python
def run_fetch_pending(cfg, since: str | None = None, limit: int | None = None,
                      db=None) -> list[tuple[str, str]]:
    if db is None:
        db = open_store(cfg)
    since = since or date.today().isoformat()
    pending = store.list_videos_by_status(db, "discovered", since=since, limit=limit)
    results: list[tuple[str, str]] = []
    for v in pending:
        try:
            run_fetch(v.url, cfg, db=db, video_id=v.video_id)
            results.append((v.video_id, "ok"))
        except Exception as exc:  # noqa: BLE001 - continue-on-error is the point
            results.append((v.video_id, f"failed: {exc}"))
    return results


@app.command("fetch-pending")
def fetch_pending(
    since: str = typer.Option(None, "--since", help="Only discovered videos published on/after YYYY-MM-DD (default today)"),
    limit: int = typer.Option(None, "--limit", help="Process at most N videos"),
):
    """Batch download + transcribe + embed all pending 'discovered' videos."""
    cfg = load_config()
    results = run_fetch_pending(cfg, since=since, limit=limit)
    if not results:
        typer.echo("nothing pending")
        return
    ok = 0
    for vid, outcome in results:
        typer.echo(f"{vid}: {outcome}")
        if outcome == "ok":
            ok += 1
    typer.echo(f"\n{ok} ok / {len(results) - ok} failed")
```

- [ ] **Step 4: Run tests + smoke**

Run: `uv run pytest tests/test_cli.py -q` → PASS
Run: `uv run pytest -q` → full suite PASS; `-W error::DeprecationWarning` clean.
Run: `uv run yt-ai fetch-pending --help` → shows `--since/--limit`. Report output.

- [ ] **Step 5: Commit**

```bash
git add yt_summary/cli.py tests/test_cli.py
git commit -m "feat: yt-ai fetch-pending (batch, continue-on-error)"
```

---

## Task 4: `daily-digest` skill

**Files:**
- Create: `skills/daily-digest/SKILL.md`
- Modify: `.gitignore` (+ `digests/`)

**Interfaces:** Consumes the CLI (`yt-ai list`/`show`/`search`/`save-summary`); writes `digests/<DATE>.md` + `summaries` rows. No Python.

- [ ] **Step 1: Add `digests/` to `.gitignore`**

Append `digests/` to `.gitignore`.

- [ ] **Step 2: Create `skills/daily-digest/SKILL.md`**

````markdown
---
name: daily-digest
description: Use when the user wants a daily digest of their freshly-fetched YouTube subscription videos — a combined summary plus per-video summaries/highlights/Q&A. Reads transcribed videos via the yt-ai CLI and writes digests/<DATE>.md. Run after `yt-ai fetch-pending`.
---

# Daily Digest

Turn the videos fetched for a given day into per-video summaries and one combined
digest file. All data access is through the `yt-ai` CLI — never touch the store directly.

## Inputs
- `date` (optional, default = today, `YYYY-MM-DD`) — the `--since` cutoff.

## Steps

1. **Select the day's videos:**
   ```bash
   yt-ai list --status transcribed --since <DATE> --json
   ```
   Parse the JSON array. If empty, tell the user to run `yt-ai fetch-pending` first and stop.

2. **Per video** (each entry's `video_id`):
   a. Load content: `yt-ai show <video_id> --json` → `title`, `url`, `transcript`.
   b. Anchor highlights: for each candidate highlight phrase, run
      `yt-ai search "<phrase>" --vector -k 3` and use the `MM:SS` from a line whose
      `video_id` matches. **Never invent timestamps.**
   c. Produce (grounded strictly in the transcript):
      - `summary_md`: 2–4 sentence executive summary + key bullets.
      - `highlights`: JSON `[{"start_s": <seconds>, "label": "..."}]` (3–8, from step b).
      - `qa`: JSON `[{"q": "...", "a": "..."}]` (3–6).
   d. Persist: `yt-ai save-summary <video_id> "<summary_md>" '<highlights_json>' '<qa_json>'`.

3. **Compose the digest** at `digests/<DATE>.md`:
   - A top **executive digest**: what happened across the day, cross-video themes, what's
     worth the user's time.
   - One **section per video**: `## <title>` + link, the 2–4 sentence summary, top
     highlights as `MM:SS — label`, and 2–3 Q&A.
   Create the `digests/` directory if needed.

4. **Report** the digest file path + the executive digest in chat.

## Notes
- Everything is grounded in the transcripts; do not hallucinate content.
- Highlight timestamps come only from `yt-ai search` results.
- Idempotent: re-running overwrites each video's `summaries` row and rewrites the dated file.
- Related: [[summarize-video]] does a single video; this batches a day + adds the cross-video digest.
````

- [ ] **Step 3: Commit**

```bash
git add skills/daily-digest/SKILL.md .gitignore
git commit -m "feat: daily-digest skill"
```

---

## Task 5: Comprehensive documentation — README + project CLAUDE.md

**Files:**
- Modify: `README.md`
- Create: `CLAUDE.md`

**Interfaces:** none (documentation).

- [ ] **Step 1: Expand `README.md`**

Ensure the Commands section lists the full surface and the daily routine is the 3-step flow. Replace/extend the relevant sections so they read:

```markdown
## Commands

```bash
yt-ai fetch <url>            # download + transcribe + embed + store one video
yt-ai transcript <url>       # same pipeline
yt-ai discover               # list new subscription uploads (--after/--deep/--min-duration/--json)
yt-ai fetch-pending          # batch-fetch all pending 'discovered' videos (--since/--limit)
yt-ai list                   # list stored videos (--status/--since/--json)
yt-ai show <video_id>        # metadata + transcript (--json)
yt-ai status                 # counts by status
yt-ai search "<query>"       # semantic search (--hybrid/--fts/--vector, -k N)
yt-ai save-summary <id> ...  # persist a summary (used by skills)
```

## Daily routine

```bash
yt-ai discover               # find new subscription uploads → 'discovered'
yt-ai fetch-pending          # download+transcribe+embed today's batch (robust, skips failures)
# then in Claude Code:
/daily-digest                # per-video summaries + digests/YYYY-MM-DD.md
```

Single video on demand: `yt-ai fetch <url>` then the `/summarize-video` skill.
```

- [ ] **Step 2: Create `CLAUDE.md` (project LLM instructions)**

```markdown
# CLAUDE.md — yt_summary

Guidance for Claude Code (and any LLM) working in this repo.

## What this is

A local-first YouTube AI CLI (`yt-ai`): download audio, transcribe (captions →
faster-whisper fallback), store everything in an embedded LanceDB with per-chunk
embeddings, discover subscription uploads, and produce summaries/highlights/Q&A.
Heavy IO lives in the CLI; summarization is **skills-primary** (Claude Code skills,
not an API) to keep it free and high-quality.

## Architecture (module map)

- `config.py` — `.env` loading (`Config`). Secrets only from `.env` (gitignored).
- `proxy.py` / `cookies.py` — Webshare rotating proxy + Chrome cookies for yt-dlp.
- `download.py` — yt-dlp download + metadata; `build_opts(cfg, download_audio)`.
- `transcript/` — `captions.py` (youtube-transcript-api) → `whisper.py` (faster-whisper)
  fallback, orchestrated by `get_transcript`.
- `discovery.py` — subscription feed extraction (`discover`), injectable `extract_fn` seam.
- `store/` — `models.py` (dataclasses + LanceModel schemas + `chunk_schema`),
  `embeddings.py` (`build_embedder`, `chunk_segments`), `db.py` (LanceDB CRUD + search).
- `memory.py` — status-based `is_seen` / `mark_status`.
- `cli.py` — Typer app; thin `run_*` cores are the testable seam.

## Store (LanceDB)

Tables: `videos`, `channels`, `transcripts`, `chunks` (embedded + FTS), `summaries`,
`feedback`, `app_state`. Video lifecycle `status`: `discovered → downloaded →
transcribed → summarized`.

## Conventions (follow these)

- **skills-primary summarization** — the CLI stores data; skills read it via
  `yt-ai show --json` / `search` / `save-summary` and never touch the store engine.
- **`_safe(...)`** guards every LanceDB `where/delete/update` clause that interpolates
  an id/key/status. Always use it for new filters.
- **`is_seen` is status-based** (`transcribed`/`summarized`) → ingest is retry-safe.
- **insert-only discovery** (`insert_discovered_video`) never downgrades a fetched video.
- **Injectable seams for offline tests**: `ydl_factory`, `extract_fn`, `model_factory`,
  and monkeypatched `cli.run_fetch`/`cli.discover_videos`. Unit tests must not hit the
  network or download models — the registered `FakeEmbedder` (tests/support.py) covers
  embeddings.
- Dates are `YYYY-MM-DD` strings; string comparison is date comparison.

## Skills

- `summarize-video` — one ingested video → summary/highlights/Q&A (`summaries` table).
- `daily-digest` — a day's transcribed videos → per-video summaries + `digests/<DATE>.md`.

## Commands & daily routine

See README.md. Pipeline: `discover → fetch-pending → /daily-digest`; single video:
`fetch → /summarize-video`.

## Dev

```bash
uv sync --extra dev
uv run pytest -q                        # offline unit suite (fake embedder)
YT_RUN_INTEGRATION=1 uv run pytest -q   # + real sentence-transformers integration
uv run --with ruff ruff check .         # lint
```

TDD: tests live in `tests/`, one per module; keep them offline via the injectable seams.
Design docs in `docs/superpowers/specs/`, plans in `docs/superpowers/plans/`.
```

- [ ] **Step 3: Final sweep**

Run: `uv run pytest -q` → all PASS (+1 skipped integration).
Run: `uv run --with ruff ruff check .` → clean.
Run: `uv run yt-ai --help` → confirm `list` + `fetch-pending` listed. Report output.

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: comprehensive README + project CLAUDE.md (LLM instructions)"
```

- [ ] **Step 5: Report roadmap-memory update to the controller**

Report that the roadmap memory (`sp-roadmap-and-stack`) should mark SP2 done: `list` +
`fetch-pending` commands + `daily-digest` skill; digest = per-video `summaries` +
`digests/<DATE>.md`; project now has a `CLAUDE.md`.

---

## Self-Review Notes

- **Spec coverage:** batch-fetch continue-on-error with `--since`/`--limit` (T3), `list` query for the skill's input (T1–T2), `daily-digest` skill → `summaries` + `digests/<DATE>.md` (T4), README + `CLAUDE.md` LLM instructions + `.gitignore digests/` (T4–T5), roadmap memory (T5). Cross-day dedup + cron + OpenRouter explicitly out of scope per spec.
- **Placeholder scan:** none — every code step is complete.
- **Type/name consistency:** `list_videos_by_status(db, status, since, limit)` matches `run_list`/`run_fetch_pending` calls; `run_fetch_pending` calls `run_fetch(url, cfg, db=, video_id=)` matching the SP0.5 signature; the monkeypatch in T3 mirrors that exact signature (`url, cfg, force=False, db=None, video_id=None`). `list` command registered as `@app.command("list")` (function `list_videos_cmd`) to avoid the builtin clash. `_safe` reused from the store.
- **Doc emphasis:** per the request, documentation is its own task (T5) with a comprehensive README and a project `CLAUDE.md`; the `daily-digest` skill (T4) is written to be self-contained and cross-links `summarize-video`.
