import os

import lancedb
import pytest

from tests.support import fake_embedder
from yt_mem_ai import frame as F
from yt_mem_ai.store import db as store
from yt_mem_ai.store.models import Video


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


def _seeded_store(tmp_path, video_id="vid", url="https://youtu.be/vid"):
    db = lancedb.connect(str(tmp_path / "s"))
    store.init_db(db, fake_embedder())
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
