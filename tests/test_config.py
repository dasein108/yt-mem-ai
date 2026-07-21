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

def test_load_config_defaults_to_dotenv_in_cwd(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("WEBSHARE_PROXY_USERNAME=cwduser\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("WEBSHARE_PROXY_USERNAME", raising=False)
    cfg = load_config()
    assert cfg.proxy_username == "cwduser"
