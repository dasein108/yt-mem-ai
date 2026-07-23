# SP5 Highlight Compilation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `yt-ai compile` — build a budget-bounded, deep-linked highlights document from summarized videos (each highlight a `watch?v=ID&t=<start>s` link). No media rendering.

**Architecture:** A `compile.py` of mostly pure functions (`deep_link`, `chunk_span`, `video_clips`, `accumulate`, `render_markdown`) plus one store-reading orchestrator (`compile_highlights`). The CLI adds a `compile` command over a testable `run_compile` core. Everything is offline-testable — no ffmpeg, no network.

**Tech Stack:** Python 3.11+ (stdlib + the existing LanceDB store), Typer, pytest, uv.

## Global Constraints

- Python 3.11+, `X | None` unions. uv; console script `yt-ai`.
- Reuse existing store reads only: `list_videos_by_status(db, "summarized", since)` (returns newest-first), `get_summary(db, id)` (row dict with `highlights` as a JSON string), `list_chunks(db, id)` (rows with `start_s`/`end_s`). No new store functions.
- **Naming:** the module function is `compile_highlights` (NOT `compile` — that shadows a builtin); the CLI command is registered `@app.command("compile")` on a function named `compile_cmd`.
- Deep link: `f"https://www.youtube.com/watch?v={video_id}&t={int(start_s)}s"` (start floored to int seconds).
- Clip span = the highlight's containing chunk `[start_s, end_s]`; nearest chunk if none contains it; `[start_s, start_s + fallback_s]` (default 45s) if the video has no chunks.
- Budget (`accumulate`): take clips in order until the running sum of `duration_s` ≥ `max_seconds`; always include ≥1 clip; the clip that crosses the budget is the last included.
- Ordering: newest-video-first (from `list_videos_by_status`), then ascending `start_s` within a video.
- `compilations/` is gitignored. Offline tests only (temp-dir LanceDB + fake embedder for the orchestrator; pure functions need no store).
- Every task ends green (`uv run pytest -q`, `uv run --with ruff ruff check .`, `-W error::DeprecationWarning` clean) and is committed.

---

## File Structure

```
yt_summary/
  compile.py   NEW: deep_link, chunk_span, Clip, video_clips, accumulate, render_markdown, compile_highlights
  cli.py       + run_compile + compile command
.gitignore     + compilations/
tests/
  test_compile.py       pure functions + orchestrator
  test_cli.py           + compile command core (optional smoke)
```

---

## Task 1: compile.py — pure functions

**Files:** Create `yt_summary/compile.py` (pure parts). Test: `tests/test_compile.py`.

**Interfaces:**
- `deep_link(video_id, start_s) -> str`
- `chunk_span(chunks, start_s, fallback_s) -> tuple[float, float]`
- `Clip` dataclass: `video_id, title, label, start_s, end_s, duration_s, link`
- `video_clips(video, summary, chunks, fallback_s=45.0) -> list[Clip]`
- `accumulate(clips, max_seconds) -> list[Clip]`
- `render_markdown(clips, since, max_minutes) -> str`

- [ ] **Step 1: Write the failing test — `tests/test_compile.py`**

```python
from types import SimpleNamespace
import json
from yt_summary import compile as C


def _chunks(spans):
    return [{"video_id": "v", "start_s": s, "end_s": e, "text": "t"} for s, e in spans]


def test_deep_link_floors_int():
    assert C.deep_link("abc", 11.7) == "https://www.youtube.com/watch?v=abc&t=11s"


def test_chunk_span_containing():
    assert C.chunk_span(_chunks([(0, 10), (10, 20)]), 12.0, 45.0) == (10.0, 20.0)


def test_chunk_span_nearest_when_none_contains():
    # 8.0 is not inside [0,5] or [10,15]; nearest by start_s is (10,15)? |10-8|=2 < |0-8|=8
    assert C.chunk_span(_chunks([(0, 5), (10, 15)]), 8.0, 45.0) == (10.0, 15.0)


def test_chunk_span_empty_fallback():
    assert C.chunk_span([], 30.0, 45.0) == (30.0, 75.0)


def test_video_clips_builds_from_highlights():
    v = SimpleNamespace(video_id="v", title="Title")
    summary = {"highlights": json.dumps([{"start_s": 10, "label": "A"}, {"start_s": 0, "label": "B"}])}
    clips = C.video_clips(v, summary, _chunks([(0, 8), (10, 20)]))
    assert [c.label for c in clips] == ["B", "A"]           # sorted by start_s
    assert clips[1].link == "https://www.youtube.com/watch?v=v&t=10s"
    assert clips[1].duration_s == 10.0


def test_video_clips_bad_json_empty():
    v = SimpleNamespace(video_id="v", title="T")
    assert C.video_clips(v, {"highlights": "not json"}, []) == []
    assert C.video_clips(v, {"highlights": None}, []) == []
    assert C.video_clips(v, None, []) == []


def test_accumulate_budget():
    mk = lambda d: C.Clip("v", "T", "l", 0, d, d, "u")
    clips = [mk(10), mk(10), mk(10)]
    got = C.accumulate(clips, 15)          # 10 -> 20 crosses 15 → include the crosser, stop
    assert [c.duration_s for c in got] == [10, 10]
    assert C.accumulate(clips, 0) == [clips[0]]   # always >= 1


def test_render_markdown_groups_and_links():
    clips = [C.Clip("v1", "First", "hi", 10, 20, 10, "https://www.youtube.com/watch?v=v1&t=10s")]
    md = C.render_markdown(clips, "2026-07-23", 20)
    assert "# Highlights" in md
    assert "## First" in md
    assert "[00:10] hi" in md
    assert "watch?v=v1&t=10s" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_compile.py -q`
Expected: FAIL (`ModuleNotFoundError: yt_summary.compile`)

- [ ] **Step 3: Implement the pure parts of `yt_summary/compile.py`**

```python
# yt_summary/compile.py
from __future__ import annotations
import json
from dataclasses import dataclass

DEFAULT_FALLBACK_S = 45.0


def deep_link(video_id: str, start_s: float) -> str:
    return f"https://www.youtube.com/watch?v={video_id}&t={int(start_s)}s"


def chunk_span(chunks: list[dict], start_s: float, fallback_s: float) -> tuple[float, float]:
    for c in chunks:
        cs, ce = c.get("start_s"), c.get("end_s")
        if cs is not None and ce is not None and float(cs) <= start_s <= float(ce):
            return float(cs), float(ce)
    with_start = [c for c in chunks if c.get("start_s") is not None]
    if with_start:
        nearest = min(with_start, key=lambda c: abs(float(c["start_s"]) - start_s))
        ns = float(nearest["start_s"])
        ne = float(nearest["end_s"]) if nearest.get("end_s") is not None else ns + fallback_s
        return ns, ne
    return start_s, start_s + fallback_s


@dataclass
class Clip:
    video_id: str
    title: str | None
    label: str
    start_s: float
    end_s: float
    duration_s: float
    link: str


def _parse_highlights(raw) -> list[dict]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        return []
    return value if isinstance(value, list) else []


def video_clips(video, summary, chunks: list[dict], fallback_s: float = DEFAULT_FALLBACK_S) -> list[Clip]:
    highlights = _parse_highlights(summary.get("highlights") if summary else None)
    clips: list[Clip] = []
    for h in highlights:
        start = h.get("start_s")
        if start is None:
            continue
        start = float(start)
        s, e = chunk_span(chunks, start, fallback_s)
        clips.append(Clip(
            video_id=video.video_id, title=video.title, label=str(h.get("label", "")),
            start_s=s, end_s=e, duration_s=max(0.0, e - s), link=deep_link(video.video_id, s)))
    clips.sort(key=lambda c: c.start_s)
    return clips


def accumulate(clips: list[Clip], max_seconds: float) -> list[Clip]:
    out: list[Clip] = []
    total = 0.0
    for clip in clips:
        out.append(clip)
        total += clip.duration_s
        if total >= max_seconds:
            break
    return out


def _fmt_ts(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60:02d}:{s % 60:02d}"


def render_markdown(clips: list[Clip], since: str | None, max_minutes: float) -> str:
    lines = ["# Highlights", "",
             f"_since {since or 'today'} · budget {int(max_minutes)} min · {len(clips)} clips_", ""]
    by_video: dict[str, list[Clip]] = {}
    for c in clips:
        by_video.setdefault(c.video_id, []).append(c)
    for vid, cs in by_video.items():
        lines.append(f"## {cs[0].title or vid}")
        lines.append(f"<https://www.youtube.com/watch?v={vid}>")
        for c in cs:
            lines.append(f"- [{_fmt_ts(c.start_s)}] {c.label} — {c.link}")
        lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_compile.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add yt_summary/compile.py tests/test_compile.py
git commit -m "feat: highlight compilation pure functions (deep-link/chunk-span/budget/render)"
```

---

## Task 2: compile_highlights orchestrator + CLI

**Files:** Modify `yt_summary/compile.py` (add `compile_highlights`), `yt_summary/cli.py` (add `run_compile` + `compile` command). Test: `tests/test_compile.py` (append orchestrator), `tests/test_cli.py` (optional).

**Interfaces:**
- `compile_highlights(db, since, max_minutes=20, fallback_s=45.0) -> list[Clip]`
- `run_compile(cfg, since=None, max_minutes=20, db=None) -> list[Clip]`
- `compile` command: `--since`, `--max-minutes 20`, `--json`, `--out`.

- [ ] **Step 1: Write the failing test (append to `tests/test_compile.py`)**

```python
import lancedb
from tests.support import fake_embedder
from yt_summary.store import db as store
from yt_summary.store.models import Video


def _db(tmp_path):
    conn = lancedb.connect(str(tmp_path / "lance"))
    store.init_db(conn, fake_embedder())
    return conn


def _seed(conn, vid, published, highlights, spans):
    store.upsert_video(conn, Video(video_id=vid, url=f"https://y/{vid}", title=vid.upper(),
                                   status="summarized", published_at=published))
    store.replace_chunks(conn, vid, [
        {"id": f"{vid}:{i}", "video_id": vid, "start_s": s, "end_s": e, "text": f"c{i}"}
        for i, (s, e) in enumerate(spans)])
    store.upsert_summary(conn, vid, "sum", json.dumps(highlights), "[]", "m", "t0")


def test_compile_highlights_orders_and_links(tmp_path):
    conn = _db(tmp_path)
    _seed(conn, "old", "2026-07-20", [{"start_s": 0, "label": "old-hi"}], [(0, 30)])
    _seed(conn, "new", "2026-07-22", [{"start_s": 10, "label": "new-hi"}], [(10, 40)])
    clips = C.compile_highlights(conn, since="2026-07-01", max_minutes=20)
    assert [c.video_id for c in clips] == ["new", "old"]           # newest-video-first
    assert clips[0].link == "https://www.youtube.com/watch?v=new&t=10s"
    assert clips[0].duration_s == 30.0


def test_compile_highlights_budget_trims(tmp_path):
    conn = _db(tmp_path)
    _seed(conn, "v", "2026-07-22",
          [{"start_s": 0, "label": "a"}, {"start_s": 60, "label": "b"}],
          [(0, 60), (60, 120)])                                     # two 60s clips
    clips = C.compile_highlights(conn, since="2026-07-01", max_minutes=1)  # 60s budget
    assert len(clips) == 1                                          # first fills the budget
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_compile.py -q`
Expected: FAIL (`AttributeError: module ... has no attribute 'compile_highlights'`)

- [ ] **Step 3: Add `compile_highlights` to `yt_summary/compile.py`**

```python
from .store import db as store


def compile_highlights(db, since: str, max_minutes: float = 20,
                       fallback_s: float = DEFAULT_FALLBACK_S) -> list[Clip]:
    videos = store.list_videos_by_status(db, "summarized", since=since)  # newest-first
    all_clips: list[Clip] = []
    for v in videos:
        summary = store.get_summary(db, v.video_id)
        if not summary:
            continue
        chunks = store.list_chunks(db, v.video_id)
        all_clips.extend(video_clips(v, summary, chunks, fallback_s))
    return accumulate(all_clips, max_minutes * 60)
```

- [ ] **Step 4: Add `run_compile` + `compile` command to `yt_summary/cli.py`**

Add near the other imports:
```python
from dataclasses import asdict
from .compile import compile_highlights, render_markdown
```
Add the core + command:
```python
def run_compile(cfg, since: str | None = None, max_minutes: float = 20, db=None) -> list:
    if db is None:
        db = open_store(cfg)
    since = since or date.today().isoformat()
    return compile_highlights(db, since, max_minutes)


@app.command("compile")
def compile_cmd(
    since: str = typer.Option(None, "--since"),
    max_minutes: float = typer.Option(20, "--max-minutes"),
    as_json: bool = typer.Option(False, "--json"),
    out: str = typer.Option(None, "--out"),
):
    """Compile deep-linked highlights from summarized videos (budget-bounded)."""
    cfg = load_config()
    since_v = since or date.today().isoformat()
    clips = run_compile(cfg, since=since_v, max_minutes=max_minutes)
    if not clips:
        typer.echo("no highlights — summarize some videos first")
        return
    if as_json:
        typer.echo(json.dumps([asdict(c) for c in clips]))
        return
    md = render_markdown(clips, since_v, max_minutes)
    if out:
        from pathlib import Path
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(md)
        typer.echo(f"wrote {out} ({len(clips)} clips)")
    else:
        typer.echo(md)
```

- [ ] **Step 5: (optional) CLI core test (append to `tests/test_cli.py`)**

```python
def test_run_compile_returns_clips(tmp_path):
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)
    store.upsert_video(conn, Video(video_id="v", url="u", title="V", status="summarized", published_at="2026-07-22"))
    store.replace_chunks(conn, "v", [{"id": "v:0", "video_id": "v", "start_s": 0.0, "end_s": 30.0, "text": "c"}])
    store.upsert_summary(conn, "v", "s", '[{"start_s": 0, "label": "hi"}]', "[]", "m", "t0")
    clips = cli.run_compile(cfg, since="2026-07-01", db=conn)
    assert clips and clips[0].link.endswith("watch?v=v&t=0s")
```

- [ ] **Step 6: Run gates + smoke**

Run: `uv run pytest -q` → all PASS; `-W error::DeprecationWarning` clean; `uv run --with ruff ruff check .` → clean.
Run: `uv run yt-ai --help` → confirm `compile` listed; `uv run yt-ai compile --help` → shows `--since/--max-minutes/--json/--out`. Report.

- [ ] **Step 7: Commit**

```bash
git add yt_summary/compile.py yt_summary/cli.py tests/
git commit -m "feat: yt-ai compile command + orchestrator"
```

---

## Task 3: Docs + final sweep

**Files:** `.gitignore`, `README.md`, `CLAUDE.md`.

- [ ] **Step 1: gitignore `compilations/`**

Append `compilations/` to `.gitignore`.

- [ ] **Step 2: Docs**

- README: add `yt-ai compile` to the Commands list (`--since/--max-minutes/--json/--out`) + a line in the daily routine (after `/daily-digest`): compile the day's highlights into a deep-linked markdown you can click into. Note the video-supercut is a future improvement.
- `CLAUDE.md`: add `compile.py` to the module map (deep-linked highlights doc from `summaries` highlights + `chunks` spans, budget-bounded; no media rendering — video supercut deferred).

- [ ] **Step 3: Final sweep**

Run: `uv run pytest -q` → all PASS (report count). `-W error::DeprecationWarning` clean. `uv run --with ruff ruff check .` → clean.
Confirm `git status` shows no `compilations/` staged.

- [ ] **Step 4: Commit**

```bash
git add .gitignore README.md CLAUDE.md
git commit -m "docs: document yt-ai compile"
```

- [ ] **Step 5: Report roadmap-memory update to the controller**

Report that the roadmap memory should mark SP5 done → **the roadmap is complete**: `yt-ai compile` builds a budget-bounded deep-linked highlights document (`watch?v=ID&t=<start>s`) from summarized videos' highlights + chunk spans; video-fragment supercut (yt-dlp --download-sections + ffmpeg) is the parked future improvement.

---

## Self-Review Notes

- **Spec coverage:** deep-linked document + link form (T1 `deep_link`/`render_markdown`), chunk-span clip window with fallback (T1 `chunk_span`/`video_clips`), `--since`/`--max-minutes` budget newest-first (T1 `accumulate` + T2 `compile_highlights`), `--json`/`--out`/markdown output (T2 command), summarized-only source (T2 orchestrator), docs + gitignore (T3). Video supercut deferred per the spec's Out of Scope.
- **Placeholder scan:** none — every code step is complete.
- **Type/name consistency:** `compile_highlights`/`run_compile`/`compile_cmd` avoid the `compile` builtin clash (command registered as `@app.command("compile")`); `Clip` fields match `render_markdown`/`asdict` usage and the tests; store reads (`list_videos_by_status`/`get_summary`/`list_chunks`) match their existing signatures; `video_clips` sorts by `start_s`, `compile_highlights` preserves newest-video-first from `list_videos_by_status`.
- **Offline discipline:** pure functions need no store; the orchestrator/CLI tests use a temp-dir LanceDB + fake embedder; no ffmpeg, no network anywhere.
