# yt_summary/cli.py
from __future__ import annotations
import json
from datetime import date, datetime, timedelta, UTC
import typer
from .config import load_config
from .store import db as store
from .store.models import TranscriptRow
from .store.embeddings import build_embedder, chunk_segments
from .download import download
from .transcript import get_transcript
from .discovery import discover as discover_videos
from . import memory

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


def run_fetch(url: str, cfg, force: bool = False, db=None, video_id: str | None = None) -> str:
    if db is None:
        db = open_store(cfg)
    vid = video_id or _extract_video_id(url)
    if vid and not force and memory.is_seen(db, vid):
        return vid

    video, audio = download(url, cfg)
    if not force and memory.is_seen(db, video.video_id):
        return video.video_id
    store.upsert_video(db, video)
    result = get_transcript(video, audio, cfg)
    store.insert_transcript(db, TranscriptRow(
        video_id=video.video_id, source=result.source, lang=result.lang,
        full_text=result.full_text, created_at=datetime.now(UTC).isoformat()))
    chunks = chunk_segments(video.video_id, result.segments, cfg.chunk_target_s)
    store.replace_chunks(db, video.video_id, chunks)
    memory.mark_status(db, video.video_id, "transcribed")
    return video.video_id


@app.command()
def fetch(url: str, force: bool = typer.Option(False, "--force")):
    """Download + transcribe + embed + store a video."""
    cfg = load_config()
    vid = run_fetch(url, cfg, force=force)
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
            "status": v.status, "published_at": v.published_at,
            "duration_s": v.duration_s, "transcript": text,
        }))
        return
    typer.echo(f"{v.title or '(no title)'}  [{v.status}]  {v.url}")
    if text:
        typer.echo(text[:500])


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


@app.command("save-summary")
def save_summary(video_id: str, summary_md: str, highlights: str = "[]", qa: str = "[]"):
    """Persist a summary/highlights/qa (used by the summarize-video skill)."""
    cfg = load_config()
    run_save_summary(cfg, video_id, summary_md, highlights, qa)
    typer.echo(f"saved summary for {video_id}")


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


if __name__ == "__main__":
    app()
