# `yt-ai frame` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `yt-ai frame <video_id> --at <ts>` CLI command that extracts one still image from an ingested video at a timestamp.

**Architecture:** New `yt_mem_ai/frame.py` mirrors `supercut.py` — pure command-builders + an orchestrator with injectable `download_fn`/`ffmpeg_fn` seams so the flow is unit-tested offline. yt-dlp downloads a 1s 720p section at the timestamp; ffmpeg extracts the first frame → PNG. CLI adds a thin `frame` command over a testable `run_frame` core.

**Tech Stack:** Python 3.11+, Typer, yt-dlp (`download_range_func`), ffmpeg, LanceDB store, pytest with the registered fake embedder.

## Global Constraints

- Engine repo `yt-mem-ai` (package dir `yt_mem_ai/`) only. No API/desktop changes.
- Reuse, don't duplicate: import `_FORMAT` from `yt_mem_ai/supercut.py` and `build_opts` from `yt_mem_ai/download.py`.
- Section window is exactly **1.0s** (`[at_s, at_s + 1.0]`); take the **first frame**.
- Output format is always **PNG**; default path `frames/<video_id>_<int seconds>s.png`.
- Tests are offline — inject `download_fn`/`ffmpeg_fn`, use the `fake_embedder` store; never hit the network or run real ffmpeg.
- Timestamp parsing accepts plain seconds (`90`, `90.5`) and colon clock form (`1:30`, `1:02:03`).

---

## Task 1: `frame.py` — timestamp parser + command builders + defaults

**Files:**
- Create: `yt_mem_ai/frame.py`
- Test: `tests/test_frame.py`

**Interfaces:**
- Produces:
  - `parse_timestamp(text: str) -> float`
  - `frame_download_opts(url: str, at_s: float, cfg, out_path: str) -> dict`
  - `extract_frame_cmd(clip_path: str, out_path: str) -> list[str]`
  - `class FrameError(Exception)`
  - `_default_download(url, at_s, cfg, out_path) -> None`, `_default_ffmpeg(argv) -> None`

- [ ] **Step 1: Write failing tests for the pure functions**

Create `tests/test_frame.py`:
```python
import pytest

from yt_mem_ai import frame as F


@pytest.mark.parametrize("text,expected", [
    ("90", 90.0),
    ("90.5", 90.5),
    ("1:30", 90.0),
    ("0:05", 5.0),
    ("1:02:03", 3723.0),
])
def test_parse_timestamp_ok(text, expected):
    assert F.parse_timestamp(text) == expected


@pytest.mark.parametrize("bad", ["", "   ", "a:b", "1:2:3:4", "-5", "1:-2"])
def test_parse_timestamp_rejects(bad):
    with pytest.raises(ValueError):
        F.parse_timestamp(bad)


def test_frame_download_opts_range_format_outtmpl():
    opts = F.frame_download_opts("https://youtu.be/abc", 30.0, _cfg(), "/w/s.mp4")
    assert opts["format"] == (
        "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/"
        "best[height<=720][ext=mp4]/best[height<=720]/best"
    )
    assert opts["outtmpl"] == "/w/s.mp4"
    assert opts["force_keyframes_at_cuts"] is True
    assert "download_ranges" in opts  # callable built for [(30.0, 31.0)]


def test_extract_frame_cmd_argv():
    cmd = F.extract_frame_cmd("/w/s.mp4", "/w/out.png")
    assert cmd == [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", "/w/s.mp4", "-frames:v", "1", "-q:v", "2", "/w/out.png",
    ]


def _cfg(**over):
    from pathlib import Path
    from yt_mem_ai.config import Config
    base = dict(downloads_dir=Path("dl"), proxy_username="u", proxy_password="p",
                cookies_browser="chrome", whisper_model="small", whisper_device="cpu",
                whisper_compute_type="int8", openrouter_api_key=None, openrouter_model="m",
                store_path=Path("s"), embedding_backend="local", embedding_model=None,
                chunk_target_s=45.0, openai_api_key=None, use_webshare=True)
    base.update(over)
    return Config(**base)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_frame.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'yt_mem_ai.frame'`.

- [ ] **Step 3: Implement `frame.py`**

Create `yt_mem_ai/frame.py`:
```python
# yt_mem_ai/frame.py
from __future__ import annotations

import os

from .download import build_opts
from .supercut import _FORMAT


class FrameError(Exception):
    """Raised when a frame grab cannot be completed."""


def parse_timestamp(text: str) -> float:
    """Parse '90', '90.5', '1:30', or '1:02:03' into seconds."""
    text = (text or "").strip()
    if not text:
        raise ValueError(f"invalid timestamp: {text!r}")
    parts = text.split(":")
    if len(parts) > 3:
        raise ValueError(f"invalid timestamp: {text!r}")
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        raise ValueError(f"invalid timestamp: {text!r}")
    if any(n < 0 for n in nums):
        raise ValueError(f"invalid timestamp: {text!r}")
    seconds = 0.0
    for n in nums:
        seconds = seconds * 60 + n
    return seconds


def frame_download_opts(url: str, at_s: float, cfg, out_path: str) -> dict:
    """yt-dlp opts: a 1s 720p section at at_s, written to out_path."""
    from yt_dlp.utils import download_range_func
    opts = build_opts(cfg, download_audio=False)
    opts["format"] = _FORMAT
    opts["merge_output_format"] = "mp4"
    opts["download_ranges"] = download_range_func(None, [(at_s, at_s + 1.0)])
    opts["force_keyframes_at_cuts"] = True
    opts["outtmpl"] = out_path
    opts["quiet"] = True
    return opts


def extract_frame_cmd(clip_path: str, out_path: str) -> list[str]:
    """ffmpeg argv: grab the first frame of clip_path as an image."""
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", clip_path, "-frames:v", "1", "-q:v", "2", out_path]


def _default_download(url: str, at_s: float, cfg, out_path: str) -> None:
    from yt_dlp import YoutubeDL
    opts = frame_download_opts(url, at_s, cfg, out_path)
    with YoutubeDL(opts) as ydl:
        ydl.download([url])


def _default_ffmpeg(argv: list[str]) -> None:
    import subprocess
    subprocess.run(argv, check=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_frame.py -q`
Expected: PASS (all Task-1 tests green).

- [ ] **Step 5: Commit**

```bash
git add yt_mem_ai/frame.py tests/test_frame.py
git commit -m "feat(frame): parse_timestamp + yt-dlp/ffmpeg command builders"
```

---

## Task 2: `grab_frame` orchestrator

**Files:**
- Modify: `yt_mem_ai/frame.py`
- Test: `tests/test_frame.py`

**Interfaces:**
- Consumes: `frame_download_opts`, `extract_frame_cmd`, `FrameError`, `_default_download`, `_default_ffmpeg` (Task 1); `store.get_video(db, video_id) -> Video | None` with `.url`.
- Produces: `grab_frame(db, video_id: str, at_s: float, out_path: str, *, cfg, workdir=None, download_fn=None, ffmpeg_fn=None) -> str`

- [ ] **Step 1: Write failing tests for `grab_frame`**

Append to `tests/test_frame.py`:
```python
import lancedb
from tests.support import fake_embedder
from yt_mem_ai.store import db as store
from yt_mem_ai.store.models import Video


def _seeded_store(tmp_path, video_id="vid", url="https://youtu.be/vid"):
    db = lancedb.connect(str(tmp_path / "s"))
    store.ensure_tables(db, fake_embedder())
    store.upsert_video(db, Video(video_id=video_id, url=url, title="T", status="transcribed"))
    return db


def test_grab_frame_happy_path(tmp_path):
    db = _seeded_store(tmp_path)
    calls = {}

    def fake_dl(url, at_s, cfg, out_path):
        calls["dl"] = (url, at_s, out_path)
        open(out_path, "wb").write(b"section")

    def fake_ff(argv):
        calls["ff"] = argv
        open(argv[-1], "wb").write(b"png")

    out = str(tmp_path / "frames" / "vid_30s.png")
    result = F.grab_frame(db, "vid", 30.0, out, cfg=_cfg(),
                          workdir=str(tmp_path / "w"),
                          download_fn=fake_dl, ffmpeg_fn=fake_ff)
    assert result == out
    assert os.path.exists(out)                       # parent dir created + written
    assert calls["dl"][0] == "https://youtu.be/vid"  # url resolved from store
    assert calls["dl"][1] == 30.0
    assert calls["ff"][-1] == out                    # ffmpeg writes to out


def test_grab_frame_unknown_video(tmp_path):
    db = _seeded_store(tmp_path)
    with pytest.raises(F.FrameError):
        F.grab_frame(db, "missing", 5.0, str(tmp_path / "x.png"), cfg=_cfg(),
                     download_fn=lambda *a: None, ffmpeg_fn=lambda *a: None)


def test_grab_frame_download_failure_wraps(tmp_path):
    db = _seeded_store(tmp_path)

    def boom(*a):
        raise RuntimeError("yt-dlp exploded")

    with pytest.raises(F.FrameError):
        F.grab_frame(db, "vid", 5.0, str(tmp_path / "x.png"), cfg=_cfg(),
                     workdir=str(tmp_path / "w"), download_fn=boom,
                     ffmpeg_fn=lambda *a: None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_frame.py -q -k grab_frame`
Expected: FAIL — `AttributeError: module 'yt_mem_ai.frame' has no attribute 'grab_frame'`.

Note: if `store.ensure_tables`/`store.upsert_video`/`Video(...)` field names differ from the above, adjust the test's seeding to match the real `yt_mem_ai/store/db.py` and `models.py` (check `tests/test_supercut.py` / `tests/test_db.py` for the exact helpers) — the assertion behavior stays the same.

- [ ] **Step 3: Implement `grab_frame`**

Append to `yt_mem_ai/frame.py`:
```python
def grab_frame(db, video_id: str, at_s: float, out_path: str, *, cfg,
               workdir: str | None = None, download_fn=None, ffmpeg_fn=None) -> str:
    """Download a 1s section at at_s and write its first frame to out_path."""
    from .store import db as store
    download_fn = download_fn or _default_download
    ffmpeg_fn = ffmpeg_fn or _default_ffmpeg

    video = store.get_video(db, video_id)
    if video is None or not getattr(video, "url", None):
        raise FrameError(f"video not found or has no url: {video_id}")

    if workdir is None:
        import tempfile
        workdir = tempfile.mkdtemp(prefix="ytframe-")
    os.makedirs(workdir, exist_ok=True)
    section = os.path.join(workdir, "section.mp4")

    try:
        download_fn(video.url, at_s, cfg, section)
    except Exception as exc:
        raise FrameError(f"download failed for {video_id} @ {at_s}s: {exc}") from exc

    parent = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(parent, exist_ok=True)
    try:
        ffmpeg_fn(extract_frame_cmd(section, out_path))
    except Exception as exc:
        raise FrameError(f"frame extraction failed: {exc}") from exc

    return out_path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_frame.py -q`
Expected: PASS (all frame tests green).

- [ ] **Step 5: Commit**

```bash
git add yt_mem_ai/frame.py tests/test_frame.py
git commit -m "feat(frame): grab_frame orchestrator (store url lookup + injectable seams)"
```

---

## Task 3: CLI `run_frame` + `frame` command + gitignore

**Files:**
- Modify: `yt_mem_ai/cli.py`
- Modify: `.gitignore`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `parse_timestamp`, `grab_frame`, `FrameError` (frame.py); `open_store`, `load_config` (cli.py).
- Produces: `run_frame(cfg, video_id: str, at: str, out: str | None = None, db=None) -> str`; a Typer `frame` command.

- [ ] **Step 1: Write a failing test for `run_frame`**

Append to `tests/test_cli.py` (follow the file's existing import style):
```python
def test_run_frame_default_path_and_parse(tmp_path, monkeypatch):
    from yt_mem_ai import cli
    captured = {}

    def fake_grab(db, video_id, at_s, out_path, *, cfg):
        captured["at_s"] = at_s
        captured["out"] = out_path
        return out_path

    monkeypatch.setattr(cli, "grab_frame", fake_grab)
    cfg = object()
    # sentinel db so run_frame doesn't open a real store
    out = cli.run_frame(cfg, "vid", "1:30", out=None, db="DB")
    assert captured["at_s"] == 90.0
    assert out == "frames/vid_90s.png"
    assert captured["out"] == "frames/vid_90s.png"


def test_run_frame_out_override(monkeypatch):
    from yt_mem_ai import cli
    monkeypatch.setattr(cli, "grab_frame", lambda db, v, at_s, out, *, cfg: out)
    assert cli.run_frame(object(), "vid", "5", out="/tmp/x.png", db="DB") == "/tmp/x.png"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -q -k run_frame`
Expected: FAIL — `AttributeError: module 'yt_mem_ai.cli' has no attribute 'run_frame'` (or `grab_frame`).

- [ ] **Step 3: Wire the CLI**

In `yt_mem_ai/cli.py`, add to the imports block (after the `from .supercut import build_supercut` line):
```python
from .frame import parse_timestamp, grab_frame, FrameError
```

Add the core + command (place near `run_supercut`/`supercut`):
```python
def run_frame(cfg, video_id: str, at: str, out: str | None = None, db=None) -> str:
    at_s = parse_timestamp(at)
    if db is None:
        db = open_store(cfg)
    out = out or f"frames/{video_id}_{int(at_s)}s.png"
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    return grab_frame(db, video_id, at_s, out, cfg=cfg)


@app.command()
def frame(
    video_id: str = typer.Argument(..., help="Ingested video id"),
    at: str = typer.Option(..., "--at", help="Timestamp: seconds or HH:MM:SS"),
    out: str = typer.Option(None, "--out", help="Output path (default frames/<id>_<s>s.png)"),
):
    """Grab a still frame from an ingested video at a timestamp (needs yt-dlp + ffmpeg)."""
    cfg = load_config()
    try:
        path = run_frame(cfg, video_id, at, out)
    except (FrameError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)
    typer.echo(path)
```

Note: `run_frame` calls `grab_frame` as a module-global name (`grab_frame(...)`), so the test's `monkeypatch.setattr(cli, "grab_frame", ...)` intercepts it — keep the imported name, do not call it as `frame.grab_frame`.

- [ ] **Step 4: Add `frames/` to `.gitignore`**

Append to `.gitignore` (near `compilations/` / `supercuts/`):
```
frames/
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -q -k run_frame`
Expected: PASS.

- [ ] **Step 6: Full suite + lint sanity**

Run: `uv run pytest -q && uv run ruff check yt_mem_ai/frame.py yt_mem_ai/cli.py`
Expected: whole suite passes; ruff clean on the touched files.

- [ ] **Step 7: Commit**

```bash
git add yt_mem_ai/cli.py .gitignore tests/test_cli.py
git commit -m "feat(cli): add 'frame' command + run_frame core; gitignore frames/"
```

---

## Task 4: Docs — README, CLAUDE.md, AGENTS.md

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Add the command to the README Commands block**

In `README.md`, inside the ```` ```bash ```` Commands block, add after the `yt-ai supercut ...` line:
```
yt-ai frame <video_id> --at <ts>  # still frame at a timestamp (seconds or H:M:S) → frames/<id>_<s>s.png
```

- [ ] **Step 2: Add a module-map entry to CLAUDE.md**

In `CLAUDE.md`, add a bullet after the `supercut.py` entry:
```markdown
- `frame.py` — single still-frame grab: `grab_frame(db, video_id, at_s, out_path,
  cfg=, workdir=, download_fn=, ffmpeg_fn=)` downloads a 1s 720p section at the
  timestamp (reusing `supercut`'s `_FORMAT` + `download_range_func`) and extracts
  the first frame via ffmpeg. `parse_timestamp` accepts seconds or `H:M:S`.
  Injectable seams keep it offline-testable; real yt-dlp/ffmpeg is manual smoke.
```

- [ ] **Step 3: Note the new surface in AGENTS.md**

In `AGENTS.md`, under the surface-parity list (the CLI bullet), no code change is required, but append this note after the parity list so future changes keep frame in mind:
```markdown
The `frame` command shares `supercut.py`'s download/ffmpeg approach — when you
change the section-download format or the ffmpeg invocation in one, check the other.
```

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md AGENTS.md
git commit -m "docs: document the 'frame' command (README/CLAUDE/AGENTS)"
```

---

## Manual smoke (not automated)

After merge, verify against a real ingested video (needs network + ffmpeg):
```bash
uv run yt-ai frame <a-real-video_id> --at 1:30
# → prints frames/<id>_90s.png ; open it and confirm it's the ~1:30 moment
```

## Self-Review notes

- **Coverage:** parser (T1), builders (T1), orchestrator incl. error wrapping + store lookup (T2), CLI core default-path + parse + command (T3), gitignore (T3), docs (T4). Manual smoke covers the real yt-dlp/ffmpeg path the offline suite deliberately fakes.
- **Interfaces consistent:** `grab_frame` signature identical in spec, T2 impl, and T3 caller; `run_frame` calls `grab_frame(db, video_id, at_s, out, cfg=cfg)`.
- **Reuse:** `_FORMAT` + `build_opts` imported, not duplicated (Global Constraints).
- **Seam correctness:** `run_frame` references `grab_frame`/`parse_timestamp` as cli module globals so tests can monkeypatch them.
- **Store-helper caveat:** T2 Step 2 flags that the test's store-seeding helpers (`ensure_tables`/`upsert_video`/`Video` fields) must match the real store API — the implementer verifies against `tests/test_supercut.py`.
