import json
from yt_mem_ai import obs


def test_log_event_writes_jsonl(tmp_path):
    f = tmp_path / "common.jsonl"
    obs.log_event("backend", "fetch.done", "info", "ok", log_file=str(f), video_id="v1")
    obs.log_event("frontend", "ui.api_error", "error", "boom", log_file=str(f), status=500)
    lines = [json.loads(x) for x in f.read_text().splitlines()]
    assert len(lines) == 2
    assert lines[0]["source"] == "backend" and lines[0]["event"] == "fetch.done"
    assert lines[0]["video_id"] == "v1" and "ts" in lines[0]
    assert lines[1]["level"] == "error" and lines[1]["status"] == 500


def test_log_event_creates_parent_dir(tmp_path):
    f = tmp_path / "nested" / "d" / "common.jsonl"
    obs.log_event("backend", "e", log_file=str(f))
    assert f.exists()


def test_log_event_never_raises():
    # a directory path as the log file → open() would fail; must be swallowed
    obs.log_event("backend", "e", log_file="/")  # no exception


def test_blog_is_backend_source(tmp_path):
    f = tmp_path / "c.jsonl"
    obs.blog("api.start", log_file=str(f), port=8000)
    assert json.loads(f.read_text().splitlines()[0])["source"] == "backend"


def test_config_log_file_default_and_env(tmp_path):
    from yt_mem_ai.config import load_config
    assert load_config(tmp_path / "none.env").log_file.name == "common.jsonl"
    env = tmp_path / ".env"
    env.write_text("YT_LOG_FILE=/x/y.jsonl\n")
    from pathlib import Path
    assert load_config(env).log_file == Path("/x/y.jsonl")
