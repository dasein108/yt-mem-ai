# yt_mem_ai/cli.py
from __future__ import annotations
import json
from dataclasses import asdict
from datetime import date, datetime, timedelta, UTC
from pathlib import Path
import typer
from .config import load_config
from .store import db as store
from .store.models import TranscriptRow, Video
from .store.embeddings import build_embedder, chunk_segments
from .download import download, download_metadata
from .transcript import get_transcript, TranscriptUnavailable
from .discovery import discover as discover_videos
from .recommend import recommend as recommend_videos
from .compile import compile_highlights, render_markdown
from .supercut import build_supercut
from .frame import parse_timestamp, grab_frame, FrameError
from . import memory
from .obs import blog

app = typer.Typer(help="YouTube AI CLI — download, transcribe, embed, search.")


def _extract_video_id(url: str) -> str | None:
    for marker in ("v=", "youtu.be/", "/shorts/"):
        if marker in url:
            tail = url.split(marker, 1)[1]
            return tail.split("&")[0].split("?")[0].split("/")[0]
    return None


def open_store(cfg):
    db = store.connect(cfg.store_path)
    store.init_db(db, build_embedder(cfg))
    return db


def run_fetch(url: str, cfg, force: bool = False, db=None, video_id: str | None = None,
              captions_only: bool = False, force_whisper: bool = False) -> str:
    if db is None:
        db = open_store(cfg)
    vid = video_id or _extract_video_id(url)
    if vid and not force and memory.is_seen(db, vid):
        blog("fetch.skip", video_id=vid)
        return vid

    # captions_only: metadata only (no audio download) → captions with no whisper
    # fallback. get_transcript raises TranscriptUnavailable if the video has none.
    if captions_only:
        video, audio = download_metadata(url, cfg), None
    else:
        video, audio = download(url, cfg)
    if not force and memory.is_seen(db, video.video_id):
        blog("fetch.skip", video_id=video.video_id)
        return video.video_id
    store.upsert_video(db, video)
    blog("fetch.download", video_id=video.video_id, audio_path=audio)
    result = get_transcript(video, audio, cfg, force_whisper=force_whisper)
    blog("fetch.transcribe", video_id=video.video_id, source_kind=result.source)
    store.insert_transcript(db, TranscriptRow(
        video_id=video.video_id, source=result.source, lang=result.lang,
        full_text=result.full_text, created_at=datetime.now(UTC).isoformat()))
    chunks = chunk_segments(video.video_id, result.segments, cfg.chunk_target_s)
    store.replace_chunks(db, video.video_id, chunks)
    memory.mark_status(db, video.video_id, "transcribed")
    blog("fetch.done", video_id=video.video_id, status="transcribed")
    return video.video_id


@app.command()
def fetch(url: str, force: bool = typer.Option(False, "--force"),
          captions_only: bool = typer.Option(
              False, "--captions-only",
              help="Fetch captions directly (no audio download, no whisper). "
                   "Fails if the video has no captions."),
          whisper: bool = typer.Option(
              False, "--whisper",
              help="Skip captions, download audio and transcribe with whisper.")):
    """Download + transcribe + embed + store a video."""
    if captions_only and whisper:
        typer.echo("--captions-only and --whisper are mutually exclusive")
        raise typer.Exit(2)
    cfg = load_config()
    try:
        vid = run_fetch(url, cfg, force=force, captions_only=captions_only,
                        force_whisper=whisper)
    except TranscriptUnavailable as exc:
        typer.echo(f"no captions available: {exc}")
        raise typer.Exit(1)
    typer.echo(f"stored {vid}")


@app.command()
def transcript(url: str):
    """Transcribe + store (same pipeline as fetch)."""
    cfg = load_config()
    vid = run_fetch(url, cfg)
    typer.echo(f"transcribed {vid}")


@app.command()
def show(video_id: str, as_json: bool = typer.Option(False, "--json")):
    """Print stored metadata + transcript (human or --json)."""
    cfg = load_config()
    db = open_store(cfg)
    v = store.get_video(db, video_id)
    if not v:
        typer.echo("not found")
        raise typer.Exit(1)
    text = store.get_transcript_text(db, video_id) or ""
    if as_json:
        typer.echo(json.dumps({
            "video_id": v.video_id, "title": v.title, "url": v.url,
            "status": v.status, "channel_id": v.channel_id, "channel": v.channel,
            "published_at": v.published_at, "duration_s": v.duration_s,
            "tags": v.tags, "description": v.description, "transcript": text,
            "transcript_lang": store.get_transcript_lang(db, video_id),
            "summary": store.get_summary(db, video_id),
        }))
        return
    ch = f"  {v.channel}" if v.channel else ""
    typer.echo(f"{v.title or '(no title)'}  [{v.status}]{ch}  {v.url}")
    if v.tags:
        typer.echo(f"tags: {v.tags}")
    if v.description:
        typer.echo(f"\n{v.description[:500]}")
    if text:
        typer.echo(f"\n--- transcript ---\n{text[:500]}")


@app.command()
def status():
    """Show counts by status."""
    cfg = load_config()
    db = open_store(cfg)
    counts = store.count_by_status(db)
    if not counts:
        typer.echo("empty")
        return
    for k, c in sorted(counts.items()):
        typer.echo(f"{k}: {c}")


def run_search(cfg, query: str, mode: str = "hybrid", k: int = 10, db=None) -> list[dict]:
    if db is None:
        db = open_store(cfg)
    return store.search_chunks(db, query, k=k, mode=mode)


def _fmt_ts(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


@app.command()
def search(
    query: str,
    hybrid: bool = typer.Option(False, "--hybrid"),
    fts: bool = typer.Option(False, "--fts"),
    vector: bool = typer.Option(False, "--vector"),
    k: int = typer.Option(10, "-k"),
):
    """Semantic search across transcript chunks."""
    cfg = load_config()
    mode = "hybrid"
    if fts:
        mode = "fts"
    elif vector:
        mode = "vector"
    elif hybrid:
        mode = "hybrid"
    hits = run_search(cfg, query, mode=mode, k=k)
    if not hits:
        typer.echo("no results")
        return
    for h in hits:
        typer.echo(f"{_fmt_ts(h.get('start_s', 0.0))}  {h['video_id']}  {h['text'][:80]}")


def run_save_summary(cfg, video_id, summary_md, highlights_json, qa_json, db=None):
    if db is None:
        db = open_store(cfg)
    store.upsert_summary(db, video_id, summary_md, highlights_json, qa_json,
                         "claude-code-skill", datetime.now(UTC).isoformat())
    memory.mark_status(db, video_id, "summarized")


@app.command("save-summary")
def save_summary(video_id: str, summary_md: str, highlights: str = "[]", qa: str = "[]"):
    """Persist a summary/highlights/qa (used by the summarize-video skill)."""
    cfg = load_config()
    run_save_summary(cfg, video_id, summary_md, highlights, qa)
    typer.echo(f"saved summary for {video_id}")


def run_discover(cfg, after: str | None = None, deep: bool = False,
                 min_duration: int = 120, db=None) -> tuple[list[Video], int]:
    if db is None:
        db = open_store(cfg)
    # Cutoff precedence: explicit --after (date) > stored epoch high-water
    # (incremental, hour-precise) > legacy last_discover_at date > 7-day default.
    # The epoch path applies a 1h overlap so hour-rounded approximate dates near
    # a boundary aren't missed; is_seen dedupe below drops the re-seen ones.
    last_ts = store.get_state(db, "last_discover_ts")
    cutoff_date: str | None
    after_ts: float | None
    if after:
        cutoff_date, after_ts = after, None
    elif last_ts:
        cutoff_date, after_ts = None, float(last_ts)
    else:
        cutoff_date = store.get_state(db, "last_discover_at") \
            or (date.today() - timedelta(days=7)).isoformat()
        after_ts = None
    blog("discover.start", after=cutoff_date, after_ts=after_ts, deep=deep)
    discovered = discover_videos(cfg, cutoff_date, deep=deep, min_duration=min_duration,
                                 after_ts=after_ts, overlap_s=cfg.discover_overlap_s)
    # Drop already-processed videos (transcribed/summarized); discovered-but-pending
    # ones are kept so fetch-pending still picks them up.
    fresh = [v for v in discovered if not memory.is_seen(db, v.video_id)]
    new_count = 0
    for v in fresh:
        if store.get_video(db, v.video_id) is None:
            new_count += 1
        if v.channel_id:
            store.upsert_channel(db, v.channel_id, None, 1)
        store.insert_discovered_video(db, v)
    # Advance the high-water mark (never regress, even on an empty/older run).
    seen_ts = [v.published_ts for v in discovered if v.published_ts]
    if seen_ts:
        prev = float(last_ts) if last_ts else 0.0
        store.set_state(db, "last_discover_ts", repr(max(max(seen_ts), prev)))
    store.set_state(db, "last_discover_at", date.today().isoformat())
    blog("discover.done", new=new_count, found=len(discovered), fresh=len(fresh))
    return fresh, new_count


@app.command()
def discover(
    after: str | None = typer.Option(None, "--after", help="Only videos published on/after YYYY-MM-DD"),
    deep: bool = typer.Option(False, "--deep", help="Enumerate subscribed channels for backfill"),
    min_duration: int = typer.Option(120, "--min-duration", help="Skip videos shorter than N seconds"),
    as_json: bool = typer.Option(False, "--json"),
):
    """List new subscription uploads after a cutoff and store them as 'discovered'."""
    from .discovery import DiscoverTimeout
    cfg = load_config()
    try:
        discovered, new_count = run_discover(cfg, after=after, deep=deep, min_duration=min_duration)
    except DiscoverTimeout as exc:
        typer.echo(str(exc))
        raise typer.Exit(1)
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


def run_list(cfg, status: str | None = None, since: str | None = None,
             channel: str | None = None, limit: int | None = None, db=None) -> list[Video]:
    if db is None:
        db = open_store(cfg)
    if status:
        videos = store.list_videos_by_status(db, status, since=since)
    else:
        videos = store.list_videos(db)
        if since is not None:
            videos = [v for v in videos if (v.published_at or "") >= since]
    if channel:
        videos = [v for v in videos if v.channel_id == channel or v.channel == channel]
    if limit is not None:
        videos = videos[:limit]
    return videos


@app.command("list")
def list_videos_cmd(
    status: str = typer.Option(None, "--status", help="Filter by status (discovered/transcribed/...)"),
    since: str = typer.Option(None, "--since", help="Only videos published on/after YYYY-MM-DD"),
    channel: str = typer.Option(None, "--channel", help="Filter by channel_id or channel name"),
    limit: int = typer.Option(None, "--limit", "-n", help="Return at most N (newest-first)"),
    as_json: bool = typer.Option(False, "--json"),
):
    """List stored videos, optionally filtered by status/date/channel, capped by --limit."""
    cfg = load_config()
    videos = run_list(cfg, status=status, since=since, channel=channel, limit=limit)
    if as_json:
        typer.echo(json.dumps([
            {"video_id": v.video_id, "title": v.title, "url": v.url, "status": v.status,
             "channel_id": v.channel_id, "channel": v.channel,
             "published_at": v.published_at, "duration_s": v.duration_s,
             "tags": v.tags, "description": v.description} for v in videos]))
        return
    if not videos:
        typer.echo("no videos")
        return
    for v in videos:
        ch = (v.channel or v.channel_id or "")[:18]
        typer.echo(f"{v.published_at or '????-??-??'}  {v.status or '?':11}  {ch:18}  {(v.title or '')[:44]:44}  {v.url}")


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


def run_feedback(cfg, video_id: str, signal: int, db=None) -> None:
    if db is None:
        db = open_store(cfg)
    store.insert_feedback(db, video_id, signal, datetime.now(UTC).isoformat())


def run_recommend(cfg, limit: int = 20, db=None) -> list[tuple[str, float]]:
    if db is None:
        db = open_store(cfg)
    return recommend_videos(db, limit=limit)


@app.command()
def like(video_id: str):
    """Mark a video as liked (feeds recommendations)."""
    cfg = load_config()
    run_feedback(cfg, video_id, 1)
    typer.echo(f"liked {video_id}")


@app.command()
def dislike(video_id: str):
    """Mark a video as disliked (feeds recommendations)."""
    cfg = load_config()
    run_feedback(cfg, video_id, -1)
    typer.echo(f"disliked {video_id}")


@app.command()
def recommend(limit: int = typer.Option(20, "--limit"),
              as_json: bool = typer.Option(False, "--json")):
    """Rank your unrated fetched videos by learned taste."""
    cfg = load_config()
    db = open_store(cfg)
    ranked = run_recommend(cfg, limit=limit, db=db)
    if not ranked:
        typer.echo("no candidates — fetch and rate some videos first")
        return
    rows = [(store.get_video(db, vid), score) for vid, score in ranked]
    if as_json:
        typer.echo(json.dumps([
            {"video_id": v.video_id, "title": v.title, "url": v.url,
             "published_at": v.published_at, "score": round(score, 4)}
            for v, score in rows if v is not None]))
        return
    for v, score in rows:
        if v is None:
            continue
        typer.echo(f"{score:+.3f}  {v.published_at or '????-??-??'}  {(v.title or '')[:50]:50}  {v.url}")


def run_compile(cfg, since: str | None = None, max_minutes: float = 20, db=None) -> list:
    if db is None:
        db = open_store(cfg)
    since = since or date.today().isoformat()
    return compile_highlights(db, since, max_minutes)


@app.command("compile")
def compile_cmd(
    since: str = typer.Option(
        None, "--since",
        help="Only summarized videos published on/after YYYY-MM-DD (default: today)"),
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
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(md)
        typer.echo(f"wrote {out} ({len(clips)} clips)")
    else:
        typer.echo(md)


def run_supercut(cfg, since: str | None = None, max_minutes: float = 20,
                 out: str | None = None, db=None):
    if db is None:
        db = open_store(cfg)
    since = since or date.today().isoformat()
    out = out or f"supercuts/{since}.mp4"
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
        shutil.rmtree(res.workdir, ignore_errors=True)
    line = f"wrote {res.out_path} ({len(res.rendered)} rendered / {len(res.failed)} skipped)"
    if not res.labeled:
        line += " (labels skipped: ffmpeg has no drawtext)"
    typer.echo(line)


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


if __name__ == "__main__":
    app()
