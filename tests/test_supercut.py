import json
from pathlib import Path
from types import SimpleNamespace

import lancedb

from yt_summary import supercut as S
from yt_summary.config import Config
from tests.support import fake_embedder
from yt_summary.store import db as store
from yt_summary.store.models import Video


def _cfg(**over):
    base = dict(downloads_dir=Path("dl"), proxy_username="u", proxy_password="p",
                cookies_browser="chrome", whisper_model="small", whisper_device="cpu",
                whisper_compute_type="int8", openrouter_api_key=None, openrouter_model="m",
                store_path=Path("s"), embedding_backend="local", embedding_model=None,
                chunk_target_s=45.0, openai_api_key=None)
    base.update(over)
    return Config(**base)


def _clip(video_id="v", start=10.0, end=40.0, label="A moment", title="Vid"):
    return SimpleNamespace(video_id=video_id, start_s=start, end_s=end, label=label,
                           title=title, duration_s=end - start,
                           link=f"https://www.youtube.com/watch?v={video_id}&t={int(start)}s")


def test_label_text_includes_label_ts_source():
    t = S.label_text(_clip(start=75.0, label="key point", title="My Video"))
    assert "key point" in t and "01:15" in t and "My Video" in t


def test_download_section_opts_range_format_proxy():
    opts = S.download_section_opts(_clip(start=10.0, end=40.0), _cfg(), "/w/v.mp4")
    assert opts["format"] == "bestvideo[height<=720]+bestaudio/best[height<=720]"
    assert opts["force_keyframes_at_cuts"] is True
    assert opts["proxy"] == "http://u:p@p.webshare.io:80"        # from build_opts
    assert opts["outtmpl"] == "/w/v.mp4"
    assert callable(opts["download_ranges"])                     # download_range_func instance


def test_normalize_label_cmd_has_scale_pad_fps_drawtext():
    argv = S.normalize_label_cmd("/in.mp4", "/out.mp4", "/labels/0.txt")
    joined = " ".join(argv)
    assert argv[0] == "ffmpeg"
    assert "scale=1280:720:force_original_aspect_ratio=decrease" in joined
    assert "pad=1280:720" in joined and "fps=30" in joined
    assert "drawtext=textfile=/labels/0.txt" in joined or "textfile='/labels/0.txt'" in joined
    assert "libx264" in joined and "aac" in joined
    assert argv[-1] == "/out.mp4"


def test_concat_cmd_and_list(tmp_path):
    lst = tmp_path / "list.txt"
    S.write_concat_list(str(lst), ["/a.mp4", "/b.mp4"])
    assert lst.read_text().splitlines() == ["file '/a.mp4'", "file '/b.mp4'"]
    argv = S.concat_cmd(str(lst), "/out.mp4")
    j = " ".join(argv)
    assert "-f concat" in j and "-safe 0" in j and "-c copy" in j and argv[-1] == "/out.mp4"


def test_refs_markdown_lists_rendered_and_failed():
    md = S.refs_markdown([_clip(start=10.0, label="hi", title="V1")],
                         [_clip(video_id="bad", label="nope", title="V2")])
    assert "hi" in md and "watch?v=v&t=10s" in md
    assert "Skipped" in md and "bad" in md


def _db(tmp_path):
    conn = lancedb.connect(str(tmp_path / "lance"))
    store.init_db(conn, fake_embedder())
    return conn


def _seed(conn, vid, highlights, spans):
    store.upsert_video(conn, Video(video_id=vid, url=f"https://y/{vid}", title=vid.upper(),
                                   status="summarized", published_at="2026-07-22"))
    store.replace_chunks(conn, vid, [
        {"id": f"{vid}:{i}", "video_id": vid, "start_s": s, "end_s": e, "text": f"c{i}"}
        for i, (s, e) in enumerate(spans)])
    store.upsert_summary(conn, vid, "s", json.dumps(highlights), "[]", "m", "t0")


def test_build_supercut_downloads_normalizes_concats(tmp_path):
    conn = _db(tmp_path)
    _seed(conn, "a", [{"start_s": 0, "label": "hi-a"}], [(0, 30)])
    _seed(conn, "b", [{"start_s": 0, "label": "hi-b"}], [(0, 30)])
    calls = {"download": [], "ffmpeg": []}

    def fake_download(clip, cfg, out_path):
        calls["download"].append(clip.video_id)
        Path(out_path).write_text("raw")            # fake downloaded section

    def fake_ffmpeg(argv):
        calls["ffmpeg"].append(argv)
        Path(argv[-1]).write_text("out")            # fake ffmpeg output

    res = S.build_supercut(conn, since="2026-07-01", max_minutes=20,
                           out_path=str(tmp_path / "reel.mp4"), workdir=str(tmp_path / "work"),
                           download_fn=fake_download, ffmpeg_fn=fake_ffmpeg)
    assert set(calls["download"]) == {"a", "b"}     # both downloaded
    # one normalize per clip + one concat
    assert len(calls["ffmpeg"]) == 3
    assert res.out_path.endswith("reel.mp4")
    assert len(res.rendered) == 2 and res.failed == []
    assert Path(str(tmp_path / "reel.mp4") + ".refs.md").exists()


def test_build_supercut_skips_failed_download(tmp_path):
    conn = _db(tmp_path)
    _seed(conn, "ok", [{"start_s": 0, "label": "ok"}], [(0, 30)])
    _seed(conn, "bad", [{"start_s": 0, "label": "bad"}], [(0, 30)])

    def fake_download(clip, cfg, out_path):
        if clip.video_id == "bad":
            raise RuntimeError("blocked")
        Path(out_path).write_text("raw")

    def fake_ffmpeg(argv):
        Path(argv[-1]).write_text("out")

    res = S.build_supercut(conn, since="2026-07-01", max_minutes=20,
                           out_path=str(tmp_path / "r.mp4"), workdir=str(tmp_path / "w"),
                           download_fn=fake_download, ffmpeg_fn=fake_ffmpeg)
    assert [c.video_id for c in res.rendered] == ["ok"]
    assert [c.video_id for c in res.failed] == ["bad"]
