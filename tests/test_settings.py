"""Tests for the runtime settings (config get/set) surface."""
from __future__ import annotations

import pytest

from yt_mem_ai import settings as S
from yt_mem_ai.config import load_config


def test_set_writes_global_and_load_config_reads_it(tmp_path, monkeypatch):
    # YT_MEM_AI_HOME is isolated by conftest; run from an empty cwd (no ./.env).
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("WEBSHARE_PROXY_USERNAME", raising=False)
    r = S.set_setting("WEBSHARE_PROXY_USERNAME", "user42")
    assert r["scope"] == "global"
    assert S.global_config_path().exists()
    # load_config picks it up (global precedence)
    assert load_config().proxy_username == "user42"
    assert S.get_setting("WEBSHARE_PROXY_USERNAME")["value"] == "user42"


def test_project_scope_overrides_global(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("YT_EMBEDDING_MODEL", raising=False)
    S.set_setting("YT_EMBEDDING_MODEL", "global-model", scope="global")
    S.set_setting("YT_EMBEDDING_MODEL", "project-model", scope="project")
    assert (tmp_path / ".env").exists()
    v, src = S.resolve("YT_EMBEDDING_MODEL")
    assert (v, src) == ("project-model", "project")
    assert load_config().embedding_model == "project-model"


def test_process_env_wins_and_is_flagged(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("YT_EMBEDDING_BACKEND", "openai")
    r = S.set_setting("YT_EMBEDDING_BACKEND", "local")
    assert r["source"] == "env" and "warning" in r
    assert load_config().embedding_backend == "openai"  # env still wins


def test_secret_masked_unless_revealed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    S.set_setting("OPENAI_API_KEY", "sk-secret")
    assert S.get_setting("OPENAI_API_KEY")["value"] == "••••••••"
    assert S.get_setting("OPENAI_API_KEY", reveal=True)["value"] == "sk-secret"


def test_unknown_key_rejected():
    with pytest.raises(S.UnknownKey):
        S.set_setting("NOT_A_REAL_KEY", "x")
    with pytest.raises(S.UnknownKey):
        S.get_setting("NOPE")


def test_choice_validation():
    with pytest.raises(ValueError):
        S.set_setting("YT_EMBEDDING_BACKEND", "sqlite")  # not local/openai


def test_unset_removes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    S.set_setting("HF_TOKEN", "hf_x")
    assert load_config().hf_token == "hf_x"
    S.unset_setting("HF_TOKEN")
    assert load_config().hf_token is None


def test_value_with_spaces_or_hash_roundtrips(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("YT_EMBEDDING_MODEL", raising=False)
    S.set_setting("YT_EMBEDDING_MODEL", "model #1 special")
    assert S.resolve("YT_EMBEDDING_MODEL")[0] == "model #1 special"


def test_set_preserves_other_keys(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    S.set_setting("WEBSHARE_PROXY_USERNAME", "u")
    S.set_setting("WEBSHARE_PROXY_PASSWORD", "p")
    S.set_setting("WEBSHARE_PROXY_USERNAME", "u2")  # update, don't clobber pw
    vals = S.list_settings(reveal=True)
    by = {r["key"]: r["value"] for r in vals}
    assert by["WEBSHARE_PROXY_USERNAME"] == "u2"
    assert by["WEBSHARE_PROXY_PASSWORD"] == "p"


def test_list_covers_every_known_key():
    keys = {r["key"] for r in S.list_settings()}
    assert keys == set(S.KNOWN)
