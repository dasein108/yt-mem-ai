# yt_summary/cli.py
from __future__ import annotations
from datetime import datetime, UTC
import typer
from .config import load_config
from .store import db
from .store.models import TranscriptRow
from .download import download
from .transcript import get_transcript
from . import memory

app = typer.Typer(help="YouTube AI CLI — download, transcribe, store.")


def _extract_video_id(url: str) -> str | None:
    # best-effort; real id resolved from yt-dlp info during download
    for marker in ("v=", "youtu.be/", "/shorts/"):
        if marker in url:
            tail = url.split(marker, 1)[1]
            return tail.split("&")[0].split("?")[0].split("/")[0]
    return None


def run_fetch(url: str, cfg, force: bool = False, conn=None, video_id: str | None = None) -> str:
    own_conn = conn is None
    if conn is None:
        conn = db.connect(cfg.db_path)
        db.init_db(conn)
    try:
        vid = video_id or _extract_video_id(url)
        if vid and not force and memory.is_seen(conn, vid):
            return vid

        video, audio = download(url, cfg)
        if not force and memory.is_seen(conn, video.video_id):
            return video.video_id
        db.upsert_video(conn, video)
        result = get_transcript(video, audio, cfg)
        db.insert_transcript(conn, TranscriptRow(
            video_id=video.video_id, source=result.source, lang=result.lang,
            full_text=result.full_text, created_at=datetime.now(UTC).isoformat()))
        if result.segments:
            db.insert_segments(conn, result.segments)
        memory.mark_status(conn, video.video_id, "transcribed")
        return video.video_id
    finally:
        if own_conn:
            conn.close()


@app.command()
def fetch(url: str, force: bool = typer.Option(False, "--force")):
    """Download + transcribe + store a video."""
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
def show(video_id: str):
    """Print stored metadata + transcript snippet."""
    cfg = load_config()
    conn = db.connect(cfg.db_path)
    try:
        db.init_db(conn)
        v = db.get_video(conn, video_id)
        if not v:
            typer.echo("not found")
            raise typer.Exit(1)
        row = conn.execute(
            "SELECT full_text FROM transcripts WHERE video_id=?", (video_id,)
        ).fetchone()
        typer.echo(f"{v.title or '(no title)'}  [{v.status}]  {v.url}")
        if row:
            typer.echo(row["full_text"][:500])
    finally:
        conn.close()


@app.command()
def status():
    """Show counts by status."""
    cfg = load_config()
    conn = db.connect(cfg.db_path)
    try:
        db.init_db(conn)
        rows = conn.execute("SELECT status, COUNT(*) c FROM videos GROUP BY status").fetchall()
        if not rows:
            typer.echo("empty")
            return
        for r in rows:
            typer.echo(f"{r['status'] or '(none)'}: {r['c']}")
    finally:
        conn.close()


if __name__ == "__main__":
    app()
