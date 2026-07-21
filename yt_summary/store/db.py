# yt_summary/store/db.py
from __future__ import annotations
import sqlite3
from pathlib import Path
from .models import Video, Segment, TranscriptRow

SCHEMA = """
CREATE TABLE IF NOT EXISTS channels (
  channel_id TEXT PRIMARY KEY,
  title      TEXT,
  subscribed INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS videos (
  video_id     TEXT PRIMARY KEY,
  channel_id   TEXT REFERENCES channels(channel_id),
  title        TEXT,
  url          TEXT,
  duration_s   INTEGER,
  published_at TEXT,
  fetched_at   TEXT,
  audio_path   TEXT,
  status       TEXT
);
CREATE TABLE IF NOT EXISTS transcripts (
  video_id   TEXT PRIMARY KEY REFERENCES videos(video_id),
  source     TEXT,
  lang       TEXT,
  full_text  TEXT,
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS segments (
  id       INTEGER PRIMARY KEY,
  video_id TEXT REFERENCES videos(video_id),
  start_s  REAL,
  end_s    REAL,
  text     TEXT
);
CREATE TABLE IF NOT EXISTS summaries (
  video_id   TEXT PRIMARY KEY REFERENCES videos(video_id),
  summary_md TEXT,
  highlights TEXT,
  qa         TEXT,
  model      TEXT,
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS feedback (
  video_id   TEXT REFERENCES videos(video_id),
  signal     INTEGER,
  created_at TEXT,
  PRIMARY KEY (video_id, created_at)
);
CREATE INDEX IF NOT EXISTS idx_segments_video ON segments(video_id);
CREATE INDEX IF NOT EXISTS idx_videos_published ON videos(published_at);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def upsert_video(conn: sqlite3.Connection, v: Video) -> None:
    conn.execute(
        """
        INSERT INTO videos (video_id, channel_id, title, url, duration_s,
                            published_at, fetched_at, audio_path, status)
        VALUES (:video_id, :channel_id, :title, :url, :duration_s,
                :published_at, :fetched_at, :audio_path, :status)
        ON CONFLICT(video_id) DO UPDATE SET
            channel_id=excluded.channel_id, title=excluded.title, url=excluded.url,
            duration_s=excluded.duration_s, published_at=excluded.published_at,
            fetched_at=excluded.fetched_at, audio_path=excluded.audio_path,
            status=excluded.status
        """,
        v.__dict__,
    )
    conn.commit()


def get_video(conn: sqlite3.Connection, video_id: str) -> Video | None:
    row = conn.execute("SELECT * FROM videos WHERE video_id=?", (video_id,)).fetchone()
    return Video(**dict(row)) if row else None


def list_videos(conn: sqlite3.Connection) -> list[Video]:
    rows = conn.execute("SELECT * FROM videos ORDER BY published_at DESC").fetchall()
    return [Video(**dict(r)) for r in rows]


def insert_transcript(conn: sqlite3.Connection, t: TranscriptRow) -> None:
    conn.execute(
        """INSERT INTO transcripts (video_id, source, lang, full_text, created_at)
           VALUES (:video_id, :source, :lang, :full_text, :created_at)
           ON CONFLICT(video_id) DO UPDATE SET
               source=excluded.source, lang=excluded.lang,
               full_text=excluded.full_text, created_at=excluded.created_at""",
        t.__dict__,
    )
    conn.commit()


def insert_segments(conn: sqlite3.Connection, segments: list[Segment]) -> None:
    conn.executemany(
        "INSERT INTO segments (video_id, start_s, end_s, text) VALUES (?, ?, ?, ?)",
        [(s.video_id, s.start_s, s.end_s, s.text) for s in segments],
    )
    conn.commit()
