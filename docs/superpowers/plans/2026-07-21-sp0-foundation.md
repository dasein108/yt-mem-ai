# YouTube Summary SP0 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the single-video ingestion pipeline: `url → yt-dlp metadata + audio → transcript (captions-first, faster-whisper fallback) → SQLite`, with Webshare proxy, Chrome cookies, dedup memory, and a Claude Code `summarize-video` skill.

**Architecture:** Small, single-responsibility Python modules under `yt_summary/`. A Typer CLI orchestrates: download → transcript → store. Transcript layer tries `youtube-transcript-api` (proxied via Webshare) and falls back to `faster-whisper` on the downloaded audio. SQLite persists metadata, transcripts, timestamped segments, and (later) skill summaries. Summarization is done by a Claude Code skill reading transcripts from SQLite — no API dependency in SP0.

**Tech Stack:** Python 3.11+, Typer, yt-dlp, youtube-transcript-api, faster-whisper, ffmpeg (system), python-dotenv, SQLite (stdlib `sqlite3`), pytest.

## Global Constraints

- Python 3.11+ (use `X | None` union syntax, `datetime.UTC`).
- Package manager: `uv`. Project layout is a single installable package `yt_summary` with console script `yt-ai`.
- Secrets ONLY from `.env` via `python-dotenv`; never hardcode; `.env` is gitignored. Webshare creds shared in chat are considered exposed.
- youtube-transcript-api ≥ 1.0: instance API `YouTubeTranscriptApi(proxy_config=WebshareProxyConfig(...)).fetch(video_id)`; snippets expose `.text`, `.start`, `.duration`.
- faster-whisper: `WhisperModel(size, device, compute_type)`, `segments, info = model.transcribe(path, beam_size=5)`; each segment has `.start`, `.end`, `.text`; `info.language` is the detected lang. Default model config on Mac: `small` / `cpu` / `int8`.
- yt-dlp Python API: `YoutubeDL(opts).extract_info(url, download=...)`. Cookies via `cookiesfrombrowser: ("chrome",)`. Proxy via `proxy: "http://user:pass@host:port"`.
- All timestamps stored as ISO8601 UTC strings.
- Every task ends green (`pytest -q`) and is committed.

---

## File Structure

```
pyproject.toml              # uv project, deps, console script yt-ai
.env.example                # documented env keys (no real values)
yt_summary/
  __init__.py
  config.py                 # Config dataclass + load_config()
  proxy.py                  # webshare_config(), ytdlp_proxy_url()
  cookies.py                # cookie_opts()
  download.py               # fetch_metadata(), download_audio(), download()
  memory.py                 # is_seen(), mark_status()
  transcript/
    __init__.py             # get_transcript() orchestrator + TranscriptResult
    captions.py             # fetch_captions()
    whisper.py              # transcribe_audio()
  store/
    __init__.py
    models.py               # Video, Segment, TranscriptResult-ish dataclasses
    db.py                   # connect(), init_db(), CRUD
  cli.py                    # Typer app: fetch, transcript, show, status
tests/
  test_config.py
  test_db.py
  test_memory.py
  test_proxy.py
  test_cookies.py
  test_download.py
  test_captions.py
  test_whisper.py
  test_transcript_orchestrator.py
  test_cli.py
skills/
  summarize-video/SKILL.md
```

---

## Task 1: Project scaffold + config loading

**Files:**
- Create: `pyproject.toml`, `.env.example`, `yt_summary/__init__.py`, `yt_summary/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Config` dataclass with fields `db_path: Path`, `downloads_dir: Path`, `proxy_username: str | None`, `proxy_password: str | None`, `cookies_browser: str | None`, `whisper_model: str`, `whisper_device: str`, `whisper_compute_type: str`, `openrouter_api_key: str | None`. `load_config(env_path: Path | None = None) -> Config`.

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "yt-summary"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "typer>=0.12",
    "yt-dlp>=2024.8",
    "youtube-transcript-api>=1.0",
    "faster-whisper>=1.0",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.scripts]
yt-ai = "yt_summary.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create `.env.example`**

```bash
# Webshare rotating residential proxy
WEBSHARE_PROXY_USERNAME=
WEBSHARE_PROXY_PASSWORD=
# Browser to pull cookies from (chrome|brave|edge|firefox); blank = none
YT_COOKIES_BROWSER=chrome
# Storage
YT_DB_PATH=yt_summary.db
YT_DOWNLOADS_DIR=downloads
# faster-whisper
YT_WHISPER_MODEL=small
YT_WHISPER_DEVICE=cpu
YT_WHISPER_COMPUTE_TYPE=int8
# Optional LLM (SP0 unused; automation path)
OPENROUTER_API_KEY=
```

- [ ] **Step 3: Write the failing test**

```python
# tests/test_config.py
from pathlib import Path
from yt_summary.config import load_config

def test_load_config_reads_env(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "WEBSHARE_PROXY_USERNAME=user1\n"
        "WEBSHARE_PROXY_PASSWORD=pass1\n"
        "YT_COOKIES_BROWSER=chrome\n"
        "YT_DB_PATH=my.db\n"
        "YT_DOWNLOADS_DIR=dl\n"
        "YT_WHISPER_MODEL=small\n"
        "YT_WHISPER_DEVICE=cpu\n"
        "YT_WHISPER_COMPUTE_TYPE=int8\n"
    )
    cfg = load_config(env)
    assert cfg.proxy_username == "user1"
    assert cfg.proxy_password == "pass1"
    assert cfg.cookies_browser == "chrome"
    assert cfg.db_path == Path("my.db")
    assert cfg.downloads_dir == Path("dl")
    assert cfg.whisper_model == "small"

def test_load_config_defaults_when_missing(tmp_path):
    cfg = load_config(tmp_path / "nope.env")
    assert cfg.proxy_username is None
    assert cfg.whisper_device == "cpu"
    assert cfg.db_path == Path("yt_summary.db")
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -q`
Expected: FAIL (`ModuleNotFoundError: yt_summary.config`)

- [ ] **Step 5: Implement `yt_summary/config.py`**

```python
# yt_summary/config.py
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import dotenv_values


@dataclass(frozen=True)
class Config:
    db_path: Path
    downloads_dir: Path
    proxy_username: str | None
    proxy_password: str | None
    cookies_browser: str | None
    whisper_model: str
    whisper_device: str
    whisper_compute_type: str
    openrouter_api_key: str | None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def load_config(env_path: Path | None = None) -> Config:
    data: dict[str, str | None] = {}
    if env_path is not None and Path(env_path).exists():
        data.update(dotenv_values(env_path))
    # process env overrides file
    for key in (
        "WEBSHARE_PROXY_USERNAME", "WEBSHARE_PROXY_PASSWORD", "YT_COOKIES_BROWSER",
        "YT_DB_PATH", "YT_DOWNLOADS_DIR", "YT_WHISPER_MODEL", "YT_WHISPER_DEVICE",
        "YT_WHISPER_COMPUTE_TYPE", "OPENROUTER_API_KEY",
    ):
        if os.environ.get(key) is not None:
            data[key] = os.environ[key]

    return Config(
        db_path=Path(_clean(data.get("YT_DB_PATH")) or "yt_summary.db"),
        downloads_dir=Path(_clean(data.get("YT_DOWNLOADS_DIR")) or "downloads"),
        proxy_username=_clean(data.get("WEBSHARE_PROXY_USERNAME")),
        proxy_password=_clean(data.get("WEBSHARE_PROXY_PASSWORD")),
        cookies_browser=_clean(data.get("YT_COOKIES_BROWSER")),
        whisper_model=_clean(data.get("YT_WHISPER_MODEL")) or "small",
        whisper_device=_clean(data.get("YT_WHISPER_DEVICE")) or "cpu",
        whisper_compute_type=_clean(data.get("YT_WHISPER_COMPUTE_TYPE")) or "int8",
        openrouter_api_key=_clean(data.get("OPENROUTER_API_KEY")),
    )
```

Also create empty `yt_summary/__init__.py`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py -q`
Expected: PASS (2 passed)

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .env.example yt_summary/__init__.py yt_summary/config.py tests/test_config.py
git commit -m "feat: project scaffold + config loading"
```

---

## Task 2: Data models

**Files:**
- Create: `yt_summary/store/__init__.py`, `yt_summary/store/models.py`
- Test: `tests/test_db.py` (models portion; full DB in Task 3 — combine into one test file)

**Interfaces:**
- Produces dataclasses:
  - `Video(video_id, channel_id, title, url, duration_s, published_at, fetched_at, audio_path, status)`
  - `Segment(video_id, start_s, end_s, text, id=None)`
  - `TranscriptRow(video_id, source, lang, full_text, created_at)`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db.py
from yt_summary.store.models import Video, Segment, TranscriptRow

def test_video_dataclass_defaults():
    v = Video(video_id="abc", url="https://y/abc")
    assert v.video_id == "abc"
    assert v.status == "discovered"
    assert v.channel_id is None

def test_segment_and_transcript():
    s = Segment(video_id="abc", start_s=0.0, end_s=1.5, text="hi")
    assert s.id is None and s.end_s == 1.5
    t = TranscriptRow(video_id="abc", source="captions", lang="en",
                      full_text="hi there", created_at="2026-07-21T00:00:00+00:00")
    assert t.source == "captions"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_db.py -q`
Expected: FAIL (`ModuleNotFoundError: yt_summary.store.models`)

- [ ] **Step 3: Implement `yt_summary/store/models.py`**

```python
# yt_summary/store/models.py
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class Video:
    video_id: str
    url: str
    channel_id: str | None = None
    title: str | None = None
    duration_s: int | None = None
    published_at: str | None = None
    fetched_at: str | None = None
    audio_path: str | None = None
    status: str = "discovered"


@dataclass
class Segment:
    video_id: str
    start_s: float
    end_s: float
    text: str
    id: int | None = None


@dataclass
class TranscriptRow:
    video_id: str
    source: str
    lang: str | None
    full_text: str
    created_at: str
```

Create empty `yt_summary/store/__init__.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_db.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add yt_summary/store/__init__.py yt_summary/store/models.py tests/test_db.py
git commit -m "feat: core data models"
```

---

## Task 3: SQLite store (schema + CRUD)

**Files:**
- Create: `yt_summary/store/db.py`
- Modify: `tests/test_db.py` (append)

**Interfaces:**
- Consumes: `Video`, `Segment`, `TranscriptRow` from Task 2.
- Produces:
  - `connect(db_path) -> sqlite3.Connection` (row_factory=Row, FK on)
  - `init_db(conn) -> None`
  - `upsert_video(conn, v: Video) -> None`
  - `get_video(conn, video_id) -> Video | None`
  - `insert_transcript(conn, t: TranscriptRow) -> None`
  - `insert_segments(conn, segments: list[Segment]) -> None`
  - `list_videos(conn) -> list[Video]`

- [ ] **Step 1: Write the failing test (append to `tests/test_db.py`)**

```python
from yt_summary.store import db
from yt_summary.store.models import Video, Segment, TranscriptRow

def _conn():
    conn = db.connect(":memory:")
    db.init_db(conn)
    return conn

def test_upsert_and_get_video():
    conn = _conn()
    db.upsert_video(conn, Video(video_id="abc", url="u", title="T", status="downloaded"))
    got = db.get_video(conn, "abc")
    assert got is not None and got.title == "T" and got.status == "downloaded"

def test_upsert_video_is_idempotent_update():
    conn = _conn()
    db.upsert_video(conn, Video(video_id="abc", url="u", status="discovered"))
    db.upsert_video(conn, Video(video_id="abc", url="u", status="transcribed"))
    assert db.get_video(conn, "abc").status == "transcribed"
    assert len(db.list_videos(conn)) == 1

def test_transcript_and_segments_roundtrip():
    conn = _conn()
    db.upsert_video(conn, Video(video_id="abc", url="u"))
    db.insert_transcript(conn, TranscriptRow("abc", "captions", "en", "hello", "2026-07-21T00:00:00+00:00"))
    db.insert_segments(conn, [Segment("abc", 0.0, 1.0, "hello")])
    row = conn.execute("SELECT full_text FROM transcripts WHERE video_id='abc'").fetchone()
    assert row["full_text"] == "hello"
    seg = conn.execute("SELECT text FROM segments WHERE video_id='abc'").fetchone()
    assert seg["text"] == "hello"

def test_get_missing_video_returns_none():
    assert db.get_video(_conn(), "missing") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_db.py -q`
Expected: FAIL (`ModuleNotFoundError: yt_summary.store.db`)

- [ ] **Step 3: Implement `yt_summary/store/db.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_db.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add yt_summary/store/db.py tests/test_db.py
git commit -m "feat: sqlite schema + CRUD"
```

---

## Task 4: Dedup memory

**Files:**
- Create: `yt_summary/memory.py`
- Test: `tests/test_memory.py`

**Interfaces:**
- Consumes: `db`, `Video` from earlier tasks.
- Produces:
  - `is_seen(conn, video_id) -> bool` — True when a transcript row exists for the video.
  - `mark_status(conn, video_id, status: str) -> None`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_memory.py
from yt_summary.store import db
from yt_summary.store.models import Video, TranscriptRow
from yt_summary import memory

def _conn():
    c = db.connect(":memory:"); db.init_db(c); return c

def test_unseen_when_no_transcript():
    conn = _conn()
    db.upsert_video(conn, Video(video_id="abc", url="u"))
    assert memory.is_seen(conn, "abc") is False

def test_seen_after_transcript():
    conn = _conn()
    db.upsert_video(conn, Video(video_id="abc", url="u"))
    db.insert_transcript(conn, TranscriptRow("abc", "captions", "en", "t", "2026-07-21T00:00:00+00:00"))
    assert memory.is_seen(conn, "abc") is True

def test_mark_status_updates_video():
    conn = _conn()
    db.upsert_video(conn, Video(video_id="abc", url="u"))
    memory.mark_status(conn, "abc", "downloaded")
    assert db.get_video(conn, "abc").status == "downloaded"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_memory.py -q`
Expected: FAIL (`ModuleNotFoundError: yt_summary.memory`)

- [ ] **Step 3: Implement `yt_summary/memory.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_memory.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add yt_summary/memory.py tests/test_memory.py
git commit -m "feat: dedup memory"
```

---

## Task 5: Proxy config

**Files:**
- Create: `yt_summary/proxy.py`
- Test: `tests/test_proxy.py`

**Interfaces:**
- Consumes: `Config` from Task 1.
- Produces:
  - `webshare_config(cfg) -> WebshareProxyConfig | None` — for youtube-transcript-api.
  - `ytdlp_proxy_url(cfg) -> str | None` — `http://<user>:<pass>@p.webshare.io:80` (rotating endpoint) for yt-dlp.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_proxy.py
from yt_summary.config import Config
from pathlib import Path
from yt_summary import proxy

def _cfg(user, pw):
    return Config(db_path=Path("x"), downloads_dir=Path("d"),
                  proxy_username=user, proxy_password=pw, cookies_browser=None,
                  whisper_model="small", whisper_device="cpu",
                  whisper_compute_type="int8", openrouter_api_key=None)

def test_ytdlp_proxy_url_built():
    assert proxy.ytdlp_proxy_url(_cfg("u", "p")) == "http://u:p@p.webshare.io:80"

def test_ytdlp_proxy_url_none_when_missing():
    assert proxy.ytdlp_proxy_url(_cfg(None, None)) is None

def test_webshare_config_none_when_missing():
    assert proxy.webshare_config(_cfg(None, None)) is None

def test_webshare_config_built_when_present():
    cfg = proxy.webshare_config(_cfg("u", "p"))
    assert cfg is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_proxy.py -q`
Expected: FAIL (`ModuleNotFoundError: yt_summary.proxy`)

- [ ] **Step 3: Implement `yt_summary/proxy.py`**

```python
# yt_summary/proxy.py
from __future__ import annotations
from .config import Config


def ytdlp_proxy_url(cfg: Config) -> str | None:
    if cfg.proxy_username and cfg.proxy_password:
        return f"http://{cfg.proxy_username}:{cfg.proxy_password}@p.webshare.io:80"
    return None


def webshare_config(cfg: Config):
    if cfg.proxy_username and cfg.proxy_password:
        from youtube_transcript_api.proxies import WebshareProxyConfig
        return WebshareProxyConfig(
            proxy_username=cfg.proxy_username,
            proxy_password=cfg.proxy_password,
        )
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_proxy.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add yt_summary/proxy.py tests/test_proxy.py
git commit -m "feat: webshare proxy config"
```

---

## Task 6: Cookie options

**Files:**
- Create: `yt_summary/cookies.py`
- Test: `tests/test_cookies.py`

**Interfaces:**
- Consumes: `Config`.
- Produces: `cookie_opts(cfg) -> dict` — `{"cookiesfrombrowser": (browser,)}` or `{}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cookies.py
from pathlib import Path
from yt_summary.config import Config
from yt_summary import cookies

def _cfg(browser):
    return Config(db_path=Path("x"), downloads_dir=Path("d"), proxy_username=None,
                  proxy_password=None, cookies_browser=browser, whisper_model="small",
                  whisper_device="cpu", whisper_compute_type="int8", openrouter_api_key=None)

def test_cookie_opts_with_browser():
    assert cookies.cookie_opts(_cfg("chrome")) == {"cookiesfrombrowser": ("chrome",)}

def test_cookie_opts_empty_when_none():
    assert cookies.cookie_opts(_cfg(None)) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cookies.py -q`
Expected: FAIL (`ModuleNotFoundError: yt_summary.cookies`)

- [ ] **Step 3: Implement `yt_summary/cookies.py`**

```python
# yt_summary/cookies.py
from __future__ import annotations
from .config import Config


def cookie_opts(cfg: Config) -> dict:
    if cfg.cookies_browser:
        return {"cookiesfrombrowser": (cfg.cookies_browser,)}
    return {}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cookies.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add yt_summary/cookies.py tests/test_cookies.py
git commit -m "feat: chrome cookie options"
```

---

## Task 7: Downloader (yt-dlp)

**Files:**
- Create: `yt_summary/download.py`
- Test: `tests/test_download.py`

**Interfaces:**
- Consumes: `Config`, `proxy.ytdlp_proxy_url`, `cookies.cookie_opts`, `Video`.
- Produces:
  - `build_opts(cfg, download_audio: bool) -> dict` — yt-dlp options (proxy + cookies + audio format merged).
  - `video_from_info(info: dict, url: str) -> Video` — map yt-dlp info dict to `Video`.
  - `download(url, cfg, ydl_factory=YoutubeDL) -> tuple[Video, str | None]` — extracts info, downloads bestaudio→mp3, returns Video + audio path. `ydl_factory` injectable for tests.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_download.py
from pathlib import Path
from yt_summary.config import Config
from yt_summary import download

def _cfg(tmp_path):
    return Config(db_path=tmp_path / "x.db", downloads_dir=tmp_path / "dl",
                  proxy_username="u", proxy_password="p", cookies_browser="chrome",
                  whisper_model="small", whisper_device="cpu",
                  whisper_compute_type="int8", openrouter_api_key=None)

def test_build_opts_merges_proxy_and_cookies(tmp_path):
    opts = download.build_opts(_cfg(tmp_path), download_audio=True)
    assert opts["proxy"] == "http://u:p@p.webshare.io:80"
    assert opts["cookiesfrombrowser"] == ("chrome",)
    assert opts["format"] == "bestaudio/best"

def test_video_from_info_maps_fields():
    info = {"id": "abc", "title": "T", "duration": 120,
            "channel_id": "chan", "upload_date": "20260721",
            "webpage_url": "https://y/abc"}
    v = download.video_from_info(info, "https://y/abc")
    assert v.video_id == "abc" and v.duration_s == 120
    assert v.channel_id == "chan"
    assert v.published_at == "2026-07-21"

def test_download_uses_injected_factory(tmp_path):
    calls = {}
    class FakeYDL:
        def __init__(self, opts): calls["opts"] = opts
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def extract_info(self, url, download):
            calls["download"] = download
            return {"id": "abc", "title": "T", "duration": 10,
                    "webpage_url": url, "upload_date": "20260721",
                    "requested_downloads": [{"filepath": str(tmp_path / "abc.mp3")}]}
    v, audio = download.download("https://y/abc", _cfg(tmp_path), ydl_factory=FakeYDL)
    assert v.video_id == "abc"
    assert audio.endswith("abc.mp3")
    assert calls["download"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_download.py -q`
Expected: FAIL (`ModuleNotFoundError: yt_summary.download`)

- [ ] **Step 3: Implement `yt_summary/download.py`**

```python
# yt_summary/download.py
from __future__ import annotations
from datetime import datetime, UTC
from .config import Config
from .proxy import ytdlp_proxy_url
from .cookies import cookie_opts
from .store.models import Video


def build_opts(cfg: Config, download_audio: bool) -> dict:
    opts: dict = {
        "quiet": True,
        "noprogress": True,
        "outtmpl": str(cfg.downloads_dir / "%(id)s.%(ext)s"),
    }
    proxy = ytdlp_proxy_url(cfg)
    if proxy:
        opts["proxy"] = proxy
    opts.update(cookie_opts(cfg))
    if download_audio:
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
        }]
    return opts


def _fmt_date(upload_date: str | None) -> str | None:
    if not upload_date:
        return None
    return datetime.strptime(upload_date, "%Y%m%d").strftime("%Y-%m-%d")


def video_from_info(info: dict, url: str) -> Video:
    return Video(
        video_id=info["id"],
        url=info.get("webpage_url") or url,
        channel_id=info.get("channel_id"),
        title=info.get("title"),
        duration_s=info.get("duration"),
        published_at=_fmt_date(info.get("upload_date")),
        fetched_at=datetime.now(UTC).isoformat(),
        status="downloaded",
    )


def _audio_path(info: dict) -> str | None:
    reqs = info.get("requested_downloads") or []
    if reqs:
        return reqs[0].get("filepath")
    return None


def download(url: str, cfg: Config, ydl_factory=None) -> tuple[Video, str | None]:
    if ydl_factory is None:
        from yt_dlp import YoutubeDL as ydl_factory  # noqa: N813
    cfg.downloads_dir.mkdir(parents=True, exist_ok=True)
    opts = build_opts(cfg, download_audio=True)
    with ydl_factory(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    video = video_from_info(info, url)
    audio = _audio_path(info)
    video.audio_path = audio
    return video, audio
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_download.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add yt_summary/download.py tests/test_download.py
git commit -m "feat: yt-dlp downloader with proxy + cookies"
```

---

## Task 8: Captions provider

**Files:**
- Create: `yt_summary/transcript/__init__.py` (TranscriptResult only for now), `yt_summary/transcript/captions.py`
- Test: `tests/test_captions.py`

**Interfaces:**
- Consumes: `Config`, `Segment`, `proxy.webshare_config`.
- Produces:
  - `TranscriptResult(source, lang, full_text, segments: list[Segment])` (dataclass in `transcript/__init__.py`).
  - `fetch_captions(video_id, cfg, api_factory=None) -> TranscriptResult | None` — returns None when no captions. `api_factory` injectable for tests.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_captions.py
from pathlib import Path
from yt_summary.config import Config
from yt_summary.transcript import captions

def _cfg():
    return Config(db_path=Path("x"), downloads_dir=Path("d"), proxy_username=None,
                  proxy_password=None, cookies_browser=None, whisper_model="small",
                  whisper_device="cpu", whisper_compute_type="int8", openrouter_api_key=None)

class _Snip:
    def __init__(self, text, start, duration):
        self.text, self.start, self.duration = text, start, duration

class _Fetched:
    def __init__(self, snips, language_code="en"):
        self._snips, self.language_code = snips, language_code
    def __iter__(self): return iter(self._snips)

def test_fetch_captions_maps_segments():
    class FakeApi:
        def __init__(self, proxy_config=None): pass
        def fetch(self, vid, languages=("en",)):
            return _Fetched([_Snip("hello", 0.0, 1.0), _Snip("world", 1.0, 2.0)])
    res = captions.fetch_captions("abc", _cfg(), api_factory=FakeApi)
    assert res is not None
    assert res.source == "captions"
    assert res.full_text == "hello world"
    assert res.segments[1].start_s == 1.0
    assert res.segments[1].end_s == 3.0

def test_fetch_captions_returns_none_on_error():
    class FakeApi:
        def __init__(self, proxy_config=None): pass
        def fetch(self, vid, languages=("en",)):
            raise Exception("no transcript")
    assert captions.fetch_captions("abc", _cfg(), api_factory=FakeApi) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_captions.py -q`
Expected: FAIL (`ModuleNotFoundError: yt_summary.transcript`)

- [ ] **Step 3: Implement `transcript/__init__.py` (result type) and `transcript/captions.py`**

```python
# yt_summary/transcript/__init__.py
from __future__ import annotations
from dataclasses import dataclass, field
from ..store.models import Segment


@dataclass
class TranscriptResult:
    source: str
    lang: str | None
    full_text: str
    segments: list[Segment] = field(default_factory=list)
```

```python
# yt_summary/transcript/captions.py
from __future__ import annotations
from ..config import Config
from ..proxy import webshare_config
from ..store.models import Segment
from . import TranscriptResult


def fetch_captions(video_id: str, cfg: Config, api_factory=None) -> TranscriptResult | None:
    if api_factory is None:
        from youtube_transcript_api import YouTubeTranscriptApi as api_factory  # noqa: N813
    proxy = webshare_config(cfg)
    api = api_factory(proxy_config=proxy) if proxy else api_factory()
    try:
        fetched = api.fetch(video_id, languages=("en",))
    except Exception:
        return None
    segments: list[Segment] = []
    texts: list[str] = []
    for snip in fetched:
        start = float(snip.start)
        end = start + float(snip.duration)
        segments.append(Segment(video_id=video_id, start_s=start, end_s=end, text=snip.text))
        texts.append(snip.text)
    lang = getattr(fetched, "language_code", None)
    return TranscriptResult(source="captions", lang=lang,
                            full_text=" ".join(texts), segments=segments)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_captions.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add yt_summary/transcript/__init__.py yt_summary/transcript/captions.py tests/test_captions.py
git commit -m "feat: youtube captions provider (proxied)"
```

---

## Task 9: Whisper provider

**Files:**
- Create: `yt_summary/transcript/whisper.py`
- Test: `tests/test_whisper.py`

**Interfaces:**
- Consumes: `Config`, `Segment`, `TranscriptResult`.
- Produces: `transcribe_audio(audio_path, video_id, cfg, model_factory=None) -> TranscriptResult` (source="whisper").

- [ ] **Step 1: Write the failing test**

```python
# tests/test_whisper.py
from pathlib import Path
from yt_summary.config import Config
from yt_summary.transcript import whisper

def _cfg():
    return Config(db_path=Path("x"), downloads_dir=Path("d"), proxy_username=None,
                  proxy_password=None, cookies_browser=None, whisper_model="small",
                  whisper_device="cpu", whisper_compute_type="int8", openrouter_api_key=None)

class _Seg:
    def __init__(self, start, end, text): self.start, self.end, self.text = start, end, text

class _Info:
    language = "en"

def test_transcribe_audio_maps_segments():
    captured = {}
    class FakeModel:
        def __init__(self, model, device, compute_type):
            captured.update(model=model, device=device, compute_type=compute_type)
        def transcribe(self, path, beam_size=5):
            return iter([_Seg(0.0, 1.0, " hi"), _Seg(1.0, 2.0, " there")]), _Info()
    res = whisper.transcribe_audio("/a/b.mp3", "abc", _cfg(), model_factory=FakeModel)
    assert res.source == "whisper"
    assert res.lang == "en"
    assert res.full_text == "hi there"
    assert res.segments[0].end_s == 1.0
    assert captured["compute_type"] == "int8"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_whisper.py -q`
Expected: FAIL (`ModuleNotFoundError: yt_summary.transcript.whisper`)

- [ ] **Step 3: Implement `yt_summary/transcript/whisper.py`**

```python
# yt_summary/transcript/whisper.py
from __future__ import annotations
from ..config import Config
from ..store.models import Segment
from . import TranscriptResult


def transcribe_audio(audio_path: str, video_id: str, cfg: Config,
                     model_factory=None) -> TranscriptResult:
    if model_factory is None:
        from faster_whisper import WhisperModel as model_factory  # noqa: N813
    model = model_factory(cfg.whisper_model, device=cfg.whisper_device,
                          compute_type=cfg.whisper_compute_type)
    segments_iter, info = model.transcribe(audio_path, beam_size=5)
    segments: list[Segment] = []
    texts: list[str] = []
    for seg in segments_iter:
        text = seg.text.strip()
        segments.append(Segment(video_id=video_id, start_s=float(seg.start),
                                end_s=float(seg.end), text=text))
        texts.append(text)
    return TranscriptResult(source="whisper", lang=getattr(info, "language", None),
                            full_text=" ".join(texts), segments=segments)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_whisper.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add yt_summary/transcript/whisper.py tests/test_whisper.py
git commit -m "feat: faster-whisper transcription provider"
```

---

## Task 10: Transcript orchestrator

**Files:**
- Modify: `yt_summary/transcript/__init__.py` (add `get_transcript`)
- Test: `tests/test_transcript_orchestrator.py`

**Interfaces:**
- Consumes: `fetch_captions`, `transcribe_audio`, `Config`, `Video`.
- Produces: `get_transcript(video: Video, audio_path: str | None, cfg, captions_fn=fetch_captions, whisper_fn=transcribe_audio) -> TranscriptResult` — try captions; on None fall back to whisper (requires audio_path); if both unavailable raise `TranscriptUnavailable`.
- Also: `class TranscriptUnavailable(Exception)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_transcript_orchestrator.py
import pytest
from pathlib import Path
from yt_summary.config import Config
from yt_summary.store.models import Video, Segment
from yt_summary import transcript as T

def _cfg():
    return Config(db_path=Path("x"), downloads_dir=Path("d"), proxy_username=None,
                  proxy_password=None, cookies_browser=None, whisper_model="small",
                  whisper_device="cpu", whisper_compute_type="int8", openrouter_api_key=None)

def _res(source):
    return T.TranscriptResult(source=source, lang="en", full_text="x",
                              segments=[Segment("abc", 0.0, 1.0, "x")])

def test_uses_captions_when_available():
    v = Video(video_id="abc", url="u")
    out = T.get_transcript(v, "/a.mp3", _cfg(),
                           captions_fn=lambda vid, cfg: _res("captions"),
                           whisper_fn=lambda p, vid, cfg: pytest.fail("should not call"))
    assert out.source == "captions"

def test_falls_back_to_whisper():
    v = Video(video_id="abc", url="u")
    out = T.get_transcript(v, "/a.mp3", _cfg(),
                           captions_fn=lambda vid, cfg: None,
                           whisper_fn=lambda p, vid, cfg: _res("whisper"))
    assert out.source == "whisper"

def test_raises_when_no_captions_and_no_audio():
    v = Video(video_id="abc", url="u")
    with pytest.raises(T.TranscriptUnavailable):
        T.get_transcript(v, None, _cfg(), captions_fn=lambda vid, cfg: None,
                         whisper_fn=lambda p, vid, cfg: _res("whisper"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_transcript_orchestrator.py -q`
Expected: FAIL (`AttributeError: module ... has no attribute 'get_transcript'`)

- [ ] **Step 3: Add to `yt_summary/transcript/__init__.py`**

Append below the `TranscriptResult` definition:

```python
class TranscriptUnavailable(Exception):
    pass


def get_transcript(video, audio_path, cfg, captions_fn=None, whisper_fn=None) -> "TranscriptResult":
    if captions_fn is None:
        from .captions import fetch_captions as captions_fn
    if whisper_fn is None:
        from .whisper import transcribe_audio as whisper_fn
    result = captions_fn(video.video_id, cfg)
    if result is not None:
        return result
    if audio_path:
        return whisper_fn(audio_path, video.video_id, cfg)
    raise TranscriptUnavailable(f"No captions and no audio for {video.video_id}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_transcript_orchestrator.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add yt_summary/transcript/__init__.py tests/test_transcript_orchestrator.py
git commit -m "feat: transcript orchestrator (captions then whisper)"
```

---

## Task 11: CLI (Typer)

**Files:**
- Create: `yt_summary/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: everything above.
- Produces Typer `app` with commands:
  - `fetch <url> [--force]` — download → transcript → store; skip if `is_seen` unless `--force`.
  - `transcript <url>` — transcript only (still downloads audio if needed for whisper).
  - `show <video_id>` — print stored metadata + transcript snippet.
  - `status` — count of videos by status.
- Produces `run_fetch(url, cfg, force=False, conn=None) -> str` — testable core returning the video_id, separated from Typer wiring.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py
from pathlib import Path
from yt_summary.config import Config
from yt_summary.store import db
from yt_summary.store.models import Video, Segment
from yt_summary import cli, transcript as T

def _cfg(tmp_path):
    return Config(db_path=tmp_path / "t.db", downloads_dir=tmp_path / "dl",
                  proxy_username=None, proxy_password=None, cookies_browser=None,
                  whisper_model="small", whisper_device="cpu",
                  whisper_compute_type="int8", openrouter_api_key=None)

def test_run_fetch_stores_video_and_transcript(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    conn = db.connect(":memory:"); db.init_db(conn)
    monkeypatch.setattr(cli, "download",
        lambda url, c: (Video(video_id="abc", url=url, status="downloaded"), "/a.mp3"))
    monkeypatch.setattr(cli, "get_transcript",
        lambda v, audio, c: T.TranscriptResult("captions", "en", "hello world",
                                               [Segment("abc", 0.0, 1.0, "hello world")]))
    vid = cli.run_fetch("https://y/abc", cfg, conn=conn)
    assert vid == "abc"
    assert db.get_video(conn, "abc").status == "transcribed"
    assert conn.execute("SELECT full_text FROM transcripts WHERE video_id='abc'").fetchone()["full_text"] == "hello world"

def test_run_fetch_skips_when_seen(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    conn = db.connect(":memory:"); db.init_db(conn)
    db.upsert_video(conn, Video(video_id="abc", url="u"))
    db.insert_transcript(conn, __import__("yt_summary.store.models", fromlist=["TranscriptRow"]).TranscriptRow("abc","captions","en","x","2026-07-21T00:00:00+00:00"))
    called = {"dl": False}
    def _dl(url, c): called["dl"] = True; raise AssertionError("should skip")
    monkeypatch.setattr(cli, "download", _dl)
    vid = cli.run_fetch("https://y/watch?v=abc", cfg, conn=conn, video_id="abc")
    assert vid == "abc"
    assert called["dl"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -q`
Expected: FAIL (`ModuleNotFoundError: yt_summary.cli`)

- [ ] **Step 3: Implement `yt_summary/cli.py`**

```python
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
    conn = db.connect(cfg.db_path); db.init_db(conn)
    v = db.get_video(conn, video_id)
    if not v:
        typer.echo("not found"); raise typer.Exit(1)
    row = conn.execute("SELECT full_text FROM transcripts WHERE video_id=?", (video_id,)).fetchone()
    typer.echo(f"{v.title or '(no title)'}  [{v.status}]  {v.url}")
    if row:
        typer.echo(row["full_text"][:500])


@app.command()
def status():
    """Show counts by status."""
    cfg = load_config()
    conn = db.connect(cfg.db_path); db.init_db(conn)
    rows = conn.execute("SELECT status, COUNT(*) c FROM videos GROUP BY status").fetchall()
    if not rows:
        typer.echo("empty"); return
    for r in rows:
        typer.echo(f"{r['status'] or '(none)'}: {r['c']}")


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -q`
Expected: PASS

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest -q`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add yt_summary/cli.py tests/test_cli.py
git commit -m "feat: typer cli (fetch/transcript/show/status)"
```

---

## Task 12: `summarize-video` Claude Code skill

**Files:**
- Create: `skills/summarize-video/SKILL.md`

**Interfaces:**
- Consumes: SQLite DB produced by CLI (reads `videos`, `transcripts`, `segments`; writes `summaries`).
- Produces: a skill that, given a `video_id`, reads the transcript and writes a `summaries` row with `summary_md`, `highlights` (JSON `[{start_s,label}]`), `qa` (JSON `[{q,a}]`), `model="claude-code-skill"`.

- [ ] **Step 1: Create `skills/summarize-video/SKILL.md`**

````markdown
---
name: summarize-video
description: Use when the user wants a summary, highlights, or Q&A for a YouTube video already ingested by yt-ai (present in the SQLite DB). Reads the stored transcript and writes summary/highlights/Q&A back to the summaries table.
---

# Summarize Video

Generate a summary, timestamped highlights, and Q&A for an ingested video, then
persist to the `summaries` table.

## Inputs
- `video_id` (required)
- DB path: default `yt_summary.db` (or `YT_DB_PATH` from `.env`)

## Steps

1. **Load the transcript.** Query:
   ```sql
   SELECT v.title, v.url, t.full_text, t.lang
   FROM videos v JOIN transcripts t ON t.video_id = v.video_id
   WHERE v.video_id = :video_id;
   ```
   If no row, tell the user to run `yt-ai fetch <url>` first and stop.

2. **Load segments for timestamps** (for highlights):
   ```sql
   SELECT start_s, text FROM segments WHERE video_id = :video_id ORDER BY start_s;
   ```

3. **Produce the analysis** (you, the model, do this — no API call):
   - Executive summary (2–4 sentences) + key bullet points → `summary_md`.
   - 3–8 highlights: pick the most significant moments; map each to the nearest
     `start_s` from segments. Format as JSON `[{"start_s": float, "label": str}]`.
   - 3–6 Q&A pairs a viewer would ask. JSON `[{"q": str, "a": str}]`.

4. **Persist.** Upsert into `summaries`:
   ```sql
   INSERT INTO summaries (video_id, summary_md, highlights, qa, model, created_at)
   VALUES (:video_id, :summary_md, :highlights, :qa, 'claude-code-skill', :now)
   ON CONFLICT(video_id) DO UPDATE SET
     summary_md=excluded.summary_md, highlights=excluded.highlights,
     qa=excluded.qa, model=excluded.model, created_at=excluded.created_at;
   ```
   Use an ISO8601 UTC timestamp for `:now`.

5. **Report** the summary + highlights (as `MM:SS — label`) + Q&A to the user in chat.

## Notes
- Highlight timestamps must come from real `segments.start_s` values, never invented.
- Keep everything grounded in the transcript; do not hallucinate content.
````

- [ ] **Step 2: Commit**

```bash
git add skills/summarize-video/SKILL.md
git commit -m "feat: summarize-video claude code skill"
```

---

## Self-Review Notes

- **Spec coverage:** download (T7), captions-first + whisper fallback (T8–T10), SQLite metadata+transcript+segments (T2–T3), dedup memory / "remember downloaded" (T4, T11 skip logic), proxy (T5), cookies (T6), config/.env secrets (T1), summarize skill (T12), CLI surface fetch/transcript/show/status (T11). SP1–SP5 intentionally out of scope (schema forward-compatible: `channels.subscribed`, `feedback`, `summaries.highlights` timestamps present).
- **Placeholder scan:** none — every code step is complete.
- **Type consistency:** `TranscriptResult(source, lang, full_text, segments)` used identically across T8–T11; `Video`/`Segment`/`TranscriptRow` signatures consistent; `download()`/`get_transcript()` signatures match their monkeypatched calls in T11.
- **Injectable factories** (`ydl_factory`, `api_factory`, `model_factory`, `captions_fn`/`whisper_fn`) keep all network/model code unit-testable without hitting YouTube or loading whisper weights.
