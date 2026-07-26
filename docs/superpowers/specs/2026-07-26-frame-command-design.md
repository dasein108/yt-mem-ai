# `yt-ai frame` — grab a still frame at a timestamp

**Date:** 2026-07-26
**Repo:** engine `yt-mem-ai` (package `yt_mem_ai`)

## Purpose

Add a CLI command that extracts a single still image from an ingested video at a
given timestamp. Pairs with deep-linked highlights (`compile`) — every highlight
already carries a `video_id` + start second, so a user can turn any of those
moments into a shareable screenshot.

## Command

```
yt-ai frame <video_id> --at <ts> [--out <path>]
```

- `video_id` — positional; must already be in the LanceDB store (its URL is
  looked up). If absent → clear error, non-zero exit.
- `--at <ts>` — required; the position. Accepts plain seconds (`90`, `90.5`) or
  clock form (`1:30`, `1:02:03`).
- `--out <path>` — optional; defaults to `frames/<video_id>_<seconds>s.png`.
  Format is always PNG.

## Approach

Reuse the supercut download+ffmpeg pipeline. Download a **1-second 720p section**
starting at the timestamp (yt-dlp `download_ranges` + `force_keyframes_at_cuts`,
the same format string as `supercut.py`), then extract the **first frame** of
that section with ffmpeg (`-frames:v 1 -q:v 2`). The section starts on a keyframe
at the requested time, so its first frame is the target moment.

720p (not best-available) was chosen deliberately: reuses supercut's proven format
string and keeps the download small.

## Components

### New module `yt_mem_ai/frame.py`

Mirrors `supercut.py`'s shape — pure command-builders plus an orchestrator with
injectable seams, so the whole flow is unit-tested offline (no network, no ffmpeg).

- `parse_timestamp(text: str) -> float`
  - `"90"` / `"90.5"` → `90.0` / `90.5`; `"1:30"` → `90.0`; `"1:02:03"` → `3723.0`.
  - Rejects malformed input (empty, non-numeric parts, negative) → raises
    `ValueError` with a message naming the offending input.

- `frame_download_opts(url: str, at_s: float, cfg: Config, out_path: str) -> dict`
  - Returns yt-dlp opts: supercut's 720p `format` string, `build_opts(cfg,
    download_audio=False)` proxy/cookies base, `outtmpl = out_path`,
    `download_ranges = download_range_func(None, [(at_s, at_s + 1.0)])`,
    `force_keyframes_at_cuts = True`, `quiet = True`.

- `extract_frame_cmd(clip_path: str, out_path: str) -> list[str]`
  - `["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", clip_path,
     "-frames:v", "1", "-q:v", "2", out_path]`.

- `grab_frame(db, video_id: str, at_s: float, out_path: str, *, cfg: Config,
   workdir: str | None = None, download_fn=None, ffmpeg_fn=None) -> str`
  - Resolves `store.get_video(db, video_id)` → `video.url`; raises
    `FrameError` (new lightweight exception) if the video is missing or has no url.
  - Downloads the 1s section into `workdir` (a temp dir if not given) via
    `download_fn(url, at_s, cfg, section_path)` (default `_default_download`,
    which builds opts with `frame_download_opts` and runs yt-dlp).
  - Runs `ffmpeg_fn(extract_frame_cmd(section_path, out_path))` (default
    `_default_ffmpeg`, `subprocess.run(..., check=True)`).
  - Ensures the parent dir of `out_path` exists; returns `out_path`.
  - Raises `FrameError` (wrapping the cause) if download or extract fails.

### CLI wiring in `yt_mem_ai/cli.py`

- `run_frame(cfg, video_id: str, at: str, out: str | None = None, db=None) -> str`
  — the testable core:
  - `at_s = parse_timestamp(at)`.
  - `db = db or open_store(cfg)`.
  - `out = out or f"frames/{video_id}_{int(at_s)}s.png"`.
  - returns `grab_frame(db, video_id, at_s, out, cfg=cfg)`.
- `@app.command() def frame(video_id, at=typer.Option(..., "--at"),
   out=typer.Option(None, "--out"))` — thin wrapper: `load_config()`,
   `path = run_frame(cfg, video_id, at, out)`, `typer.echo(path)`. Catches
   `FrameError`/`ValueError` → `typer.echo(err, err=True)` + `raise typer.Exit(1)`.

### `.gitignore`

Add `frames/`.

## Data flow

```
frame <id> --at 1:30
  → parse_timestamp("1:30") = 90.0
  → open_store → get_video(id).url
  → yt-dlp: download [90.0, 91.0] @720p → <tmp>/section.mp4
  → ffmpeg -i section.mp4 -frames:v 1 → frames/<id>_90s.png
  → echo the path
```

## Error handling

| Case | Behavior |
|---|---|
| `video_id` not in store / no url | `FrameError` → stderr message, exit 1 |
| malformed `--at` | `ValueError` from `parse_timestamp` → stderr, exit 1 |
| yt-dlp download fails (private/removed/network) | `FrameError` wrapping cause → stderr, exit 1 |
| ffmpeg missing or fails | `FrameError` → stderr, exit 1 |

No partial output: `out_path` is only written by ffmpeg on success.

## Testing (offline, mirrors `test_supercut.py`)

`tests/test_frame.py`, using the registered fake embedder store + injected
`download_fn`/`ffmpeg_fn` (no network, no ffmpeg):

- `parse_timestamp`: `"90"→90.0`, `"90.5"→90.5`, `"1:30"→90.0`, `"1:02:03"→3723.0`;
  malformed (`""`, `"a:b"`, `"-5"`) raise `ValueError`.
- `frame_download_opts`: contains the 720p format string, `outtmpl == out_path`,
  and a `download_ranges` built for `[(at_s, at_s+1.0)]`; `force_keyframes_at_cuts`
  True.
- `extract_frame_cmd`: exact argv (`-frames:v 1`, `-q:v 2`, input/out paths).
- `grab_frame`: with a seeded video in a fake store + fake `download_fn`
  (writes a stub section file) + fake `ffmpeg_fn` (records argv, writes a stub
  png) → returns the out path, creates parent dir, calls both fns with expected
  args. Missing `video_id` → `FrameError`. `download_fn` raising → `FrameError`.
- `run_frame`: default out path `frames/<id>_<int seconds>s.png`; `--out`
  override respected; `parse_timestamp` applied (`--at 1:30` → path `..._90s.png`).

Real yt-dlp + ffmpeg is manual smoke only (not in the suite).

## Scope

Engine `yt-mem-ai` only. Touches: new `yt_mem_ai/frame.py`, `yt_mem_ai/cli.py`
(`run_frame` + `frame` command), `.gitignore` (`frames/`), `tests/test_frame.py`,
one README command line, and an AGENTS.md parity note. No API/desktop changes.

## Non-goals

Multiple timestamps per call, best-available resolution, URL (non-ingested)
input, and animated/gif output are out of scope for this iteration.
