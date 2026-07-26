import pytest

from yt_mem_ai import frame as F


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
