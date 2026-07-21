# yt_summary/memory.py
from __future__ import annotations
import sqlite3


def is_seen(conn: sqlite3.Connection, video_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM transcripts WHERE video_id=?", (video_id,)
    ).fetchone()
    return row is not None


def mark_status(conn: sqlite3.Connection, video_id: str, status: str) -> None:
    conn.execute("UPDATE videos SET status=? WHERE video_id=?", (status, video_id))
    conn.commit()
