# SP6 Video Supercut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `yt-ai supercut` — render SP5's budget-bounded highlight clips into one mp4: re-download each `[start,end]` section (720p), burn its label on, and concat, with a sidecar refs file.

**Architecture:** `supercut.py` of pure command-builders (`label_text`, `download_section_opts`, `normalize_label_cmd`, `concat_cmd`, `refs_markdown`) + `build_supercut` orchestrator taking injectable `download_fn`/`ffmpeg_fn` so the whole pipeline is verified offline. Reuses `compile_highlights` (selection) and `download.build_opts` (proxy/cookies). ffmpeg `drawtext=textfile=` avoids label-escaping entirely.

**Tech Stack:** Python 3.11+, yt-dlp (existing dep), ffmpeg (subprocess), Typer, pytest, uv.

## Global Constraints

- Python 3.11+, `X | None` unions. uv; console script `yt-ai`.
- Reuse: `compile.compile_highlights(db, since, max_minutes) -> list[Clip]` (SP5), `download.build_opts(cfg, download_audio=False)` (proxy+cookies), the existing store. No new dependencies.
- **Section download:** `from yt_dlp.utils import download_range_func`; opts include `download_ranges=download_range_func(None, [(clip.start_s, clip.end_s)])`, `force_keyframes_at_cuts=True`, `format="bestvideo[height<=720]+bestaudio/best[height<=720]"`, `outtmpl=<out>`; download URL = `https://www.youtube.com/watch?v=<video_id>`.
- **Normalize + label (one ffmpeg pass per clip):** scale to fit 1280×720 (`force_original_aspect_ratio=decrease`) + `pad` letterbox + `fps=30` + `drawtext=textfile='<label file>'` (label written to a file → NO text escaping), `-c:v libx264 -c:a aac`.
- **Concat:** ffmpeg concat demuxer over a list file (`file '<path>'` lines), `-c copy` (clips are uniform).
- **Injectable execution:** `build_supercut(..., download_fn=_default_download, ffmpeg_fn=_default_ffmpeg)`. `download_fn(clip, cfg, out_path)` does the yt-dlp download; `ffmpeg_fn(argv)` runs ffmpeg. Tests inject fakes that record calls + fake output files — no network, no yt-dlp/ffmpeg.
- **Continue-on-error per clip:** a clip whose download or normalize step raises is skipped and recorded in `failed`; if 0 clips render → raise a clear error (no partial mp4).
- `supercuts/` gitignored. Command-builders are pure (unit-tested); real render is manual/integration smoke.
- Every task ends green (`uv run pytest -q`, `uv run --with ruff ruff check .`, `-W error::DeprecationWarning` clean) and is committed.

---

## File Structure

```
yt_summary/
  supercut.py   NEW
  cli.py        + run_supercut + supercut command
.gitignore      + supercuts/
tests/
  test_supercut.py   pure builders + orchestrator (fake runners)
```

---

## Task 1: supercut.py — pure command builders

**Files:** Create `yt_summary/supercut.py` (pure parts). Test: `tests/test_supercut.py`.

**Interfaces:**
- `label_text(clip) -> str`
- `download_section_opts(clip, cfg, out_path) -> dict`
- `normalize_label_cmd(in_path, out_path, label_file, width=1280, height=720, fps=30) -> list[str]`
- `concat_cmd(list_file, out_path) -> list[str]`; `write_concat_list(list_file, clip_paths) -> None`
- `refs_markdown(rendered, failed) -> str`

- [ ] **Step 1: Write the failing test — `tests/test_supercut.py`**

```python
from pathlib import Path
from types import SimpleNamespace
from yt_summary import supercut as S
from yt_summary.config import Config


def _cfg(**over):
    base = dict(downloads_dir=Path("dl"), proxy_username="u", proxy_password="p",
                cookies_browser="chrome", whisper_model="small", whisper_device="cpu",
                whisper_compute_type="int8", openrouter_api_key=None, openrouter_model="m",
                store_path=Path("s"), embedding_backend="local", embedding_model=None,
                chunk_target_s=45.0, openai_api_key=None)
    base.update(over)
    return Config(**base)


def _clip(video_id="v", start=10.0, end=40.0, label="A moment", title="Vid"):
    return SimpleNamespace(video_id=video_id, start_s=start, end_s=end, label=label,
                           title=title, duration_s=end - start,
                           link=f"https://www.youtube.com/watch?v={video_id}&t={int(start)}s")


def test_label_text_includes_label_ts_source():
    t = S.label_text(_clip(start=75.0, label="key point", title="My Video"))
    assert "key point" in t and "01:15" in t and "My Video" in t


def test_download_section_opts_range_format_proxy():
    opts = S.download_section_opts(_clip(start=10.0, end=40.0), _cfg(), "/w/v.mp4")
    assert opts["format"] == "bestvideo[height<=720]+bestaudio/best[height<=720]"
    assert opts["force_keyframes_at_cuts"] is True
    assert opts["proxy"] == "http://u:p@p.webshare.io:80"        # from build_opts
    assert opts["outtmpl"] == "/w/v.mp4"
    assert callable(opts["download_ranges"])                     # download_range_func instance


def test_normalize_label_cmd_has_scale_pad_fps_drawtext():
    argv = S.normalize_label_cmd("/in.mp4", "/out.mp4", "/labels/0.txt")
    joined = " ".join(argv)
    assert argv[0] == "ffmpeg"
    assert "scale=1280:720:force_original_aspect_ratio=decrease" in joined
    assert "pad=1280:720" in joined and "fps=30" in joined
    assert "drawtext=textfile=/labels/0.txt" in joined or "textfile='/labels/0.txt'" in joined
    assert "libx264" in joined and "aac" in joined
    assert argv[-1] == "/out.mp4"


def test_concat_cmd_and_list(tmp_path):
    lst = tmp_path / "list.txt"
    S.write_concat_list(str(lst), ["/a.mp4", "/b.mp4"])
    assert lst.read_text().splitlines() == ["file '/a.mp4'", "file '/b.mp4'"]
    argv = S.concat_cmd(str(lst), "/out.mp4")
    j = " ".join(argv)
    assert "-f concat" in j and "-safe 0" in j and "-c copy" in j and argv[-1] == "/out.mp4"


def test_refs_markdown_lists_rendered_and_failed():
    md = S.refs_markdown([_clip(start=10.0, label="hi", title="V1")],
                         [_clip(video_id="bad", label="nope", title="V2")])
    assert "hi" in md and "watch?v=v&t=10s" in md
    assert "Skipped" in md and "bad" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_supercut.py -q`
Expected: FAIL (`ModuleNotFoundError: yt_summary.supercut`)

- [ ] **Step 3: Implement the pure parts of `yt_summary/supercut.py`**

```python
# yt_summary/supercut.py
from __future__ import annotations
from .download import build_opts

_FORMAT = "bestvideo[height<=720]+bestaudio/best[height<=720]"


def _fmt_ts(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60:02d}:{s % 60:02d}"


def label_text(clip) -> str:
    return f"{clip.label}  ·  {_fmt_ts(clip.start_s)}  ·  {clip.title or clip.video_id}"


def download_section_opts(clip, cfg, out_path: str) -> dict:
    from yt_dlp.utils import download_range_func
    opts = build_opts(cfg, download_audio=False)
    opts["format"] = _FORMAT
    opts["download_ranges"] = download_range_func(None, [(clip.start_s, clip.end_s)])
    opts["force_keyframes_at_cuts"] = True
    opts["outtmpl"] = out_path
    return opts


def normalize_label_cmd(in_path: str, out_path: str, label_file: str,
                        width: int = 1280, height: int = 720, fps: int = 30) -> list[str]:
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        f"fps={fps},"
        f"drawtext=textfile={label_file}:x=(w-text_w)/2:y=h-th-20:"
        f"fontsize=24:fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=8"
    )
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", in_path,
            "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac",
            "-r", str(fps), "-y", out_path]


def write_concat_list(list_file: str, clip_paths: list[str]) -> None:
    with open(list_file, "w") as f:
        for p in clip_paths:
            f.write(f"file '{p}'\n")


def concat_cmd(list_file: str, out_path: str) -> list[str]:
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "concat",
            "-safe", "0", "-i", list_file, "-c", "copy", "-y", out_path]


def refs_markdown(rendered, failed) -> str:
    lines = ["# Supercut refs", ""]
    for c in rendered:
        lines.append(f"- [{_fmt_ts(c.start_s)}] {c.label} — "
                     f"https://www.youtube.com/watch?v={c.video_id}&t={int(c.start_s)}s "
                     f"({c.title or c.video_id})")
    if failed:
        lines += ["", "## Skipped (download/render failed)"]
        for c in failed:
            lines.append(f"- {c.video_id}: {c.label}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_supercut.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add yt_summary/supercut.py tests/test_supercut.py
git commit -m "feat: supercut command builders (download-sections/normalize/concat/refs)"
```

---

## Task 2: build_supercut orchestrator + CLI

**Files:** Modify `yt_summary/supercut.py` (orchestrator + default runners), `yt_summary/cli.py`. Test: `tests/test_supercut.py` (append).

**Interfaces:**
- `Result` dataclass: `out_path, rendered, failed`.
- `build_supercut(db, since, max_minutes, out_path, workdir=None, download_fn=None, ffmpeg_fn=None) -> Result`.
- `run_supercut(cfg, since=None, max_minutes=20, out=None, db=None) -> Result`.
- `supercut` command: `--since`, `--max-minutes 20`, `--out`, `--keep-clips`.

- [ ] **Step 1: Write the failing test (append to `tests/test_supercut.py`)**

```python
import lancedb
import json
from tests.support import fake_embedder
from yt_summary.store import db as store
from yt_summary.store.models import Video


def _db(tmp_path):
    conn = lancedb.connect(str(tmp_path / "lance"))
    store.init_db(conn, fake_embedder())
    return conn


def _seed(conn, vid, highlights, spans):
    store.upsert_video(conn, Video(video_id=vid, url=f"https://y/{vid}", title=vid.upper(),
                                   status="summarized", published_at="2026-07-22"))
    store.replace_chunks(conn, vid, [
        {"id": f"{vid}:{i}", "video_id": vid, "start_s": s, "end_s": e, "text": f"c{i}"}
        for i, (s, e) in enumerate(spans)])
    store.upsert_summary(conn, vid, "s", json.dumps(highlights), "[]", "m", "t0")


def test_build_supercut_downloads_normalizes_concats(tmp_path):
    conn = _db(tmp_path)
    _seed(conn, "a", [{"start_s": 0, "label": "hi-a"}], [(0, 30)])
    _seed(conn, "b", [{"start_s": 0, "label": "hi-b"}], [(0, 30)])
    calls = {"download": [], "ffmpeg": []}

    def fake_download(clip, cfg, out_path):
        calls["download"].append(clip.video_id)
        Path(out_path).write_text("raw")            # fake downloaded section

    def fake_ffmpeg(argv):
        calls["ffmpeg"].append(argv)
        Path(argv[-1]).write_text("out")            # fake ffmpeg output

    res = S.build_supercut(conn, since="2026-07-01", max_minutes=20,
                           out_path=str(tmp_path / "reel.mp4"), workdir=str(tmp_path / "work"),
                           download_fn=fake_download, ffmpeg_fn=fake_ffmpeg)
    assert set(calls["download"]) == {"a", "b"}     # both downloaded
    # one normalize per clip + one concat
    assert len(calls["ffmpeg"]) == 3
    assert res.out_path.endswith("reel.mp4")
    assert len(res.rendered) == 2 and res.failed == []
    assert Path(str(tmp_path / "reel.mp4") + ".refs.md").exists()


def test_build_supercut_skips_failed_download(tmp_path):
    conn = _db(tmp_path)
    _seed(conn, "ok", [{"start_s": 0, "label": "ok"}], [(0, 30)])
    _seed(conn, "bad", [{"start_s": 0, "label": "bad"}], [(0, 30)])

    def fake_download(clip, cfg, out_path):
        if clip.video_id == "bad":
            raise RuntimeError("blocked")
        Path(out_path).write_text("raw")

    def fake_ffmpeg(argv):
        Path(argv[-1]).write_text("out")

    res = S.build_supercut(conn, since="2026-07-01", max_minutes=20,
                           out_path=str(tmp_path / "r.mp4"), workdir=str(tmp_path / "w"),
                           download_fn=fake_download, ffmpeg_fn=fake_ffmpeg)
    assert [c.video_id for c in res.rendered] == ["ok"]
    assert [c.video_id for c in res.failed] == ["bad"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_supercut.py -q`
Expected: FAIL (`AttributeError: build_supercut`)

- [ ] **Step 3: Add the orchestrator + default runners to `yt_summary/supercut.py`**

```python
import os
from dataclasses import dataclass, field
from .compile import compile_highlights


@dataclass
class Result:
    out_path: str
    rendered: list = field(default_factory=list)
    failed: list = field(default_factory=list)


def _default_download(clip, cfg, out_path: str) -> None:
    from yt_dlp import YoutubeDL
    opts = download_section_opts(clip, cfg, out_path)
    with YoutubeDL(opts) as ydl:
        ydl.download([f"https://www.youtube.com/watch?v={clip.video_id}"])


def _default_ffmpeg(argv: list[str]) -> None:
    import subprocess
    subprocess.run(argv, check=True)


def build_supercut(db, since: str, max_minutes: float, out_path: str, cfg=None,
                   workdir: str | None = None, download_fn=None, ffmpeg_fn=None) -> Result:
    download_fn = download_fn or _default_download
    ffmpeg_fn = ffmpeg_fn or _default_ffmpeg
    workdir = workdir or (out_path + ".work")
    os.makedirs(workdir, exist_ok=True)

    clips = compile_highlights(db, since, max_minutes)
    rendered, failed, normalized_paths = [], [], []
    for i, clip in enumerate(clips):
        raw = os.path.join(workdir, f"{i:03d}_raw.mp4")
        norm = os.path.join(workdir, f"{i:03d}.mp4")
        label_file = os.path.join(workdir, f"{i:03d}.txt")
        try:
            download_fn(clip, cfg, raw)
            with open(label_file, "w") as f:
                f.write(label_text(clip))
            ffmpeg_fn(normalize_label_cmd(raw, norm, label_file))
            normalized_paths.append(norm)
            rendered.append(clip)
        except Exception:  # noqa: BLE001 - continue-on-error per clip
            failed.append(clip)

    if not rendered:
        raise RuntimeError("no clips rendered (all downloads/renders failed or no highlights)")

    list_file = os.path.join(workdir, "concat.txt")
    write_concat_list(list_file, normalized_paths)
    ffmpeg_fn(concat_cmd(list_file, out_path))

    with open(out_path + ".refs.md", "w") as f:
        f.write(refs_markdown(rendered, failed))
    return Result(out_path=out_path, rendered=rendered, failed=failed)
```
Note: `build_supercut` needs `cfg` to build download opts — pass it through (the CLI supplies it; the fake `download_fn` in tests ignores it).

- [ ] **Step 4: Add `run_supercut` + `supercut` command to `yt_summary/cli.py`**

Add near the imports:
```python
from .supercut import build_supercut
```
Add the core + command:
```python
def run_supercut(cfg, since: str | None = None, max_minutes: float = 20,
                 out: str | None = None, db=None):
    if db is None:
        db = open_store(cfg)
    since = since or date.today().isoformat()
    out = out or f"supercuts/{since}.mp4"
    from pathlib import Path
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    return build_supercut(db, since, max_minutes, out, cfg=cfg)


@app.command()
def supercut(
    since: str = typer.Option(None, "--since", help="Summarized videos published on/after YYYY-MM-DD (default today)"),
    max_minutes: float = typer.Option(20, "--max-minutes"),
    out: str = typer.Option(None, "--out"),
    keep_clips: bool = typer.Option(False, "--keep-clips", help="Keep the per-clip work dir"),
):
    """Render a video supercut of highlights (re-downloads sections; needs ffmpeg)."""
    cfg = load_config()
    since_v = since or date.today().isoformat()
    try:
        res = run_supercut(cfg, since=since_v, max_minutes=max_minutes, out=out)
    except RuntimeError as exc:
        typer.echo(str(exc))
        raise typer.Exit(1)
    if not keep_clips:
        import shutil
        shutil.rmtree(res.out_path + ".work", ignore_errors=True)
    typer.echo(f"wrote {res.out_path} ({len(res.rendered)} rendered / {len(res.failed)} skipped)")
```

- [ ] **Step 5: Run gates + smoke**

Run: `uv run pytest -q` → all PASS; `-W error::DeprecationWarning` clean; `uv run --with ruff ruff check .` → clean.
Run: `uv run yt-ai --help` → confirm `supercut`; `uv run yt-ai supercut --help` → shows `--since/--max-minutes/--out/--keep-clips`. Report.

- [ ] **Step 6: Commit**

```bash
git add yt_summary/supercut.py yt_summary/cli.py tests/test_supercut.py
git commit -m "feat: yt-ai supercut orchestrator + command (injectable runners)"
```

---

## Task 3: Docs + final sweep

**Files:** `.gitignore`, `README.md`, `CLAUDE.md`.

- [ ] **Step 1: gitignore `supercuts/`**

Append `supercuts/` to `.gitignore`.

- [ ] **Step 2: Docs**

- README: add `yt-ai supercut` to the Commands + a note: renders a video reel of highlights by
  **re-downloading** the sections (network + ffmpeg, slower than `compile`); output `supercuts/<date>.mp4`
  + a `.refs.md`. Contrast with `compile` (the fast deep-linked doc).
- `CLAUDE.md`: add `supercut.py` — video reel from `compile_highlights` clips; pure command-builders
  (`download_section_opts`/`normalize_label_cmd`/`concat_cmd`/`label_text`/`refs_markdown`) + `build_supercut`
  with injectable `download_fn`/`ffmpeg_fn` (offline-tested); `drawtext=textfile=` avoids label escaping;
  continue-on-error per clip; real render is manual smoke.

- [ ] **Step 3: Final sweep**

Run: `uv run pytest -q` → all PASS (report count). `-W error::DeprecationWarning` clean. `uv run --with ruff ruff check .` → clean.
Confirm `git status` shows no `supercuts/` staged.
Document a MANUAL SMOKE (in the report, not automated): with a fetched+summarized short video, `uv run yt-ai supercut --since <its date> --max-minutes 2` produces a playable `.mp4` + `.refs.md` (needs network + ffmpeg).

- [ ] **Step 4: Commit**

```bash
git add .gitignore README.md CLAUDE.md
git commit -m "docs: document yt-ai supercut"
```

- [ ] **Step 5: Report roadmap-memory update to the controller**

Report that the roadmap memory should record SP6 done: the previously-deferred video-fragment supercut is built — `yt-ai supercut` re-downloads highlight sections (720p, `download_range_func`), burns labels (`drawtext=textfile`), concats to mp4 + refs, reusing SP5's clip selection; command-builders unit-tested, real render manual smoke.

---

## Self-Review Notes

- **Spec coverage:** separate `supercut` command reusing `compile_highlights` (T2), 720p section download via `download_range_func` + `build_opts` proxy/cookies (T1 `download_section_opts`), burned labels via `drawtext=textfile` + normalize to 1280×720/30fps/h264+aac (T1 `normalize_label_cmd`), concat demuxer (T1 `concat_cmd`), sidecar refs + skipped list (T1 `refs_markdown`), continue-on-error + injectable runners offline (T2 `build_supercut`), docs + gitignore + manual smoke (T3). Transitions/music/title-cards/audio-reuse deferred per spec.
- **Refinement over spec:** the spec named `escape_drawtext`; the plan uses `drawtext=textfile=<file>` (label written to a file) which sidesteps text escaping entirely — more robust against arbitrary label punctuation. The tested pure bit is `label_text` (the file's content).
- **Placeholder scan:** none — every code step is complete.
- **Type/name consistency:** `build_supercut(db, since, max_minutes, out_path, cfg=, workdir=, download_fn=, ffmpeg_fn=)` matches the T2 tests and `run_supercut`'s call; `download_fn(clip, cfg, out_path)` / `ffmpeg_fn(argv)` signatures match the fakes; `Clip` attrs (`video_id/start_s/end_s/label/title`) come from SP5's `compile.Clip`; `compile_highlights`/`build_opts` reused with their existing signatures.
- **Offline discipline:** pure builders need no execution; the orchestrator/CLI tests inject fake `download_fn`/`ffmpeg_fn` + temp-dir LanceDB; no network, no yt-dlp, no ffmpeg in the suite. Real render is documented manual smoke.
