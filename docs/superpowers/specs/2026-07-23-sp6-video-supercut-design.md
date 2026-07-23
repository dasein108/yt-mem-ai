# SP6 — Video Supercut Design

**Date:** 2026-07-23
**Status:** Approved (brainstorming complete)
**Builds on:** SP5 (`compile_highlights` clip selection) + `download.build_opts` (proxy/cookies).

## Vision

Render the same budget-bounded highlight selection SP5 produces as a single
**video reel** — re-download each highlight section from YouTube, burn its label
onto the clip, and concatenate into one mp4 with a sidecar refs file. The
"watch 20 minutes of the day's best moments" version of the deep-linked doc.

## Locked Decisions

| Concern | Choice |
|---|---|
| Command | separate `yt-ai supercut` (keeps `compile` the lightweight doc) |
| Selection | reuse `compile_highlights(db, since, max_minutes)` — SP5's tested budget selection |
| Section download | `yt-dlp --download-sections` for `[start_s, end_s]`, `bestvideo[height<=720]+bestaudio`, proxy+cookies via `build_opts` |
| Labels | burned-in per clip (ffmpeg `drawtext`: label + source title + `MM:SS`) + a sidecar refs markdown |
| Normalize | scale+pad to **1280×720**, **30 fps**, **h264 + aac** (uniform → clean concat) |
| Concat | ffmpeg concat demuxer over the normalized clips |
| Robustness | continue-on-error per clip (skip failed downloads, note in refs); 0 usable → error |
| Testability | pure command-builders unit-tested; orchestrator uses an injectable `run_fn` (offline); real render is manual/integration smoke |

## Architecture

```
yt_summary/
  supercut.py   NEW: escape_drawtext, download_section_opts, normalize_label_cmd,
                     concat_cmd, refs_markdown, build_supercut(run_fn injectable)
  cli.py        + run_supercut + supercut command
```

Reuses `compile.compile_highlights` (clips), `download.build_opts` (proxy/cookies),
and the existing store. No new dependencies (yt-dlp is a dep; ffmpeg via subprocess).

### supercut.py

- `escape_drawtext(text) -> str` — escape for ffmpeg `drawtext` (`\`, `:`, `'`, `%`, newlines);
  a small pure function with its own tests (this is the fiddly bit).
- `download_section_opts(clip, cfg, out_path) -> dict` — yt-dlp opts: `build_opts(cfg, download_audio=False)`
  base (proxy/cookies) + `format="bestvideo[height<=720]+bestaudio/best[height<=720]"`,
  a `download_ranges` for `(clip.start_s, clip.end_s)`, `force_keyframes_at_cuts=True`,
  `outtmpl=out_path`. (The exact `download_ranges`/`download_range_func` API is grounded at plan time.)
- `normalize_label_cmd(in_path, out_path, clip, width=1280, height=720, fps=30) -> list[str]` —
  an `ffmpeg` argv: `-i in -vf "scale=...:force_original_aspect_ratio=decrease,pad=...,fps=30,
  drawtext=text='<escaped label · MM:SS · source>':..." -c:v libx264 -c:a aac -y out`.
- `concat_cmd(clip_paths, out_path, list_file) -> list[str]` — writes the concat list file, returns
  `ffmpeg -f concat -safe 0 -i list.txt -c copy -y out` (clips already uniform → stream copy).
- `refs_markdown(clips, failed) -> str` — the sidecar: each rendered clip's `MM:SS`, label, source
  title + deep link; a note listing any skipped/failed clips.
- `build_supercut(db, since, max_minutes, out_path, run_fn=subprocess-runner, workdir=None) -> Result` —
  orchestrates:
  1. `clips = compile_highlights(db, since, max_minutes)`; if empty → raise/return empty.
  2. per clip: `run_fn(<yt-dlp download>)` → raw section; on failure record it and `continue`.
  3. per downloaded clip: `run_fn(normalize_label_cmd(...))` → normalized+labeled clip.
  4. `run_fn(concat_cmd(...))` → the final mp4 at `out_path`.
  5. write `<out_path>.refs.md` from `refs_markdown(rendered, failed)`.
  6. return `Result(out_path, rendered_count, failed)`.
  - `run_fn(spec) -> None` is injectable: default executes (yt-dlp for the download step, `subprocess`
    for ffmpeg); tests pass a fake that records specs + touches fake output files. So the full
    orchestration is verified offline with no network/ffmpeg.

### cli.py

- `run_supercut(cfg, since=None, max_minutes=20, out=None, db=None) -> Result` — opens store if needed;
  `since` defaults today; `out` defaults `supercuts/<since>.mp4`; calls `build_supercut`.
- `supercut` command: `--since`, `--max-minutes 20`, `--out`, `--keep-clips` (keep the work dir).
  Empty selection → "no highlights — summarize some videos first". On finish, echo the output path +
  `N rendered / M skipped`.

### Data Flow

```
supercut --since D --max-minutes 20
  → compile_highlights (SP5 selection)  → Clip[]
  → per clip: yt-dlp --download-sections [start,end] @720p (proxy/cookies)  [skip on fail]
  → per clip: ffmpeg scale/pad/fps + drawtext(label · MM:SS · source)
  → ffmpeg concat → out.mp4
  → out.mp4.refs.md (sources + timestamps + skipped)
```

### Error Handling

- Per-clip download failure (private/blocked/geo) → skip, add to `failed`, continue.
- 0 clips usable (all failed or empty selection) → clear error, no partial mp4.
- ffmpeg/normalize failure on a clip → skip that clip (continue), note it.
- `ffmpeg`/`yt-dlp` missing → the default `run_fn` surfaces a clear error naming the missing tool.
- Work dir cleaned up unless `--keep-clips`; `supercuts/` gitignored.

### Testing (offline)

- `escape_drawtext`: `:`/`'`/`\`/`%` escaped; a label like `a: "b" \ 50%` round-trips safely.
- `download_section_opts`: correct format cap, the `[start,end]` range, proxy/cookies merged from `build_opts`.
- `normalize_label_cmd`: scale/pad/fps present, drawtext uses the escaped label, libx264/aac, out path.
- `concat_cmd`: writes the list file, `-f concat -c copy` argv.
- `refs_markdown`: rendered clips listed with `MM:SS` + deep link; failed clips noted.
- `build_supercut` with a fake `run_fn` (records specs, creates fake outputs) on a temp-dir LanceDB +
  fake embedder seeded with summarized videos: asserts a download + normalize per clip, one concat,
  a refs file written, and that a clip whose download `run_fn` raises is skipped (in `failed`, not in
  the reel) while the rest still render. No network, no ffmpeg, no yt-dlp execution.
- Integration/manual (documented, NOT automated): a real short supercut from one fetched video with a
  summary — exercises actual yt-dlp section download + ffmpeg; needs network + ffmpeg.

## Documentation Updates

- README: add `yt-ai supercut` + a note it re-downloads video sections (network, slower than `compile`).
- `CLAUDE.md`: add `supercut.py` (video reel from compile's clips; pure command-builders + injectable runner).
- Roadmap memory: record SP6 (the previously-deferred video supercut) done.

## Out of Scope

- Transitions/crossfades, background music, intro/outro or per-clip title cards.
- Vertical/short-form export, chapter markers, thumbnail generation.
- Reusing stored audio (this always re-downloads video sections).
- Parallel downloads (sequential + continue-on-error for the MVP).
