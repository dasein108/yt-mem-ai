from pathlib import Path
from yt_summary.config import load_config

def test_load_config_reads_env(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "WEBSHARE_PROXY_USERNAME=user1\n"
        "WEBSHARE_PROXY_PASSWORD=pass1\n"
        "YT_COOKIES_BROWSER=chrome\n"
        "YT_DOWNLOADS_DIR=dl\n"
        "YT_WHISPER_MODEL=small\n"
        "YT_WHISPER_DEVICE=cpu\n"
        "YT_WHISPER_COMPUTE_TYPE=int8\n"
    )
    cfg = load_config(env)
    assert cfg.proxy_username == "user1"
    assert cfg.proxy_password == "pass1"
    assert cfg.cookies_browser == "chrome"
    assert cfg.downloads_dir == Path("dl")
    assert cfg.whisper_model == "small"

def test_load_config_defaults_when_missing(tmp_path):
    cfg = load_config(tmp_path / "nope.env")
    assert cfg.proxy_username is None
    assert cfg.whisper_device == "cpu"

def test_load_config_defaults_to_dotenv_in_cwd(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("WEBSHARE_PROXY_USERNAME=cwduser\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("WEBSHARE_PROXY_USERNAME", raising=False)
    cfg = load_config()
    assert cfg.proxy_username == "cwduser"

def test_load_config_lance_fields(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "YT_STORE_PATH=mylance\n"
        "YT_EMBEDDING_BACKEND=openai\n"
        "YT_EMBEDDING_MODEL=text-embedding-3-small\n"
        "YT_CHUNK_TARGET_S=30\n"
        "OPENAI_API_KEY=sk-test\n"
    )
    from yt_summary.config import load_config
    from pathlib import Path
    cfg = load_config(env)
    assert cfg.store_path == Path("mylance")
    assert cfg.embedding_backend == "openai"
    assert cfg.embedding_model == "text-embedding-3-small"
    assert cfg.chunk_target_s == 30.0
    assert cfg.openai_api_key == "sk-test"


def test_load_config_lance_defaults(tmp_path):
    from yt_summary.config import load_config
    from pathlib import Path
    cfg = load_config(tmp_path / "none.env")
    assert cfg.store_path == Path("yt_lance")
    assert cfg.embedding_backend == "local"
    assert cfg.embedding_model is None
    assert cfg.chunk_target_s == 45.0
    assert cfg.openai_api_key is None
