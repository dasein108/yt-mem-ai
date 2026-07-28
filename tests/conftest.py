import pytest


@pytest.fixture(autouse=True)
def _isolate_global_config(tmp_path_factory, monkeypatch):
    """Point YT_MEM_AI_HOME at a fresh empty dir for every test.

    Keeps the global config file (`$YT_MEM_AI_HOME/config.env`, read by
    load_config and written by `config set`) out of the real home directory, so a
    developer who has run `yt-ai config set` can't perturb the default-config
    tests, and config tests don't leak into each other.
    """
    home = tmp_path_factory.mktemp("yt-home")
    monkeypatch.setenv("YT_MEM_AI_HOME", str(home))
