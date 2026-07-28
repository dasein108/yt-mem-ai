# yt_mem_ai/settings.py
"""Read/write yt-mem-ai settings (the `.env` variables) at runtime.

Powers `yt-ai config …` and the MCP `config_*` tools so an agent or user can
reconfigure the engine from chat — set Webshare proxy creds, switch the
embedding model, point at a cookies browser, etc.

Two files feed `load_config`, lowest precedence first:
  1. the **global** config file  (`$YT_MEM_AI_HOME/config.env`, default
     `~/.yt-mem-ai/config.env`) — written by `config set` by default so it
     applies to the MCP server no matter which directory it's launched in;
  2. the **project** `.env` in the current working directory.
Process environment variables still override both (a host that sets `YT_*` in
its MCP `env` block wins — `config list` shows the effective source so that's
visible).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values


@dataclass(frozen=True)
class KeySpec:
    key: str
    description: str
    secret: bool = False
    default: str | None = None
    choices: tuple[str, ...] | None = None


# Registry of settable keys (mirrors .env.example). Only these can be `set`.
_SPECS: tuple[KeySpec, ...] = (
    KeySpec("YT_USE_WEBSHARE", "Route yt-dlp + transcripts through the Webshare proxy.",
            default="false", choices=("true", "false")),
    KeySpec("YT_CAPTIONS_USE_WEBSHARE", "Route ONLY the transcript API through Webshare (yt-dlp stays direct).",
            default="false", choices=("true", "false")),
    KeySpec("WEBSHARE_PROXY_USERNAME", "Webshare rotating-proxy username."),
    KeySpec("WEBSHARE_PROXY_PASSWORD", "Webshare rotating-proxy password.", secret=True),
    KeySpec("YT_COOKIES_BROWSER", "Browser to pull cookies from for yt-dlp (blank = none).",
            default="chrome", choices=("chrome", "brave", "edge", "firefox", "")),
    KeySpec("YT_DOWNLOADS_DIR", "Directory for downloaded audio.", default="downloads"),
    KeySpec("YT_CAPTION_LANGS", "Preferred caption languages, comma-separated (priority order).",
            default="en"),
    KeySpec("YT_WHISPER_MODEL", "faster-whisper model size (tiny/base/small/medium/large-v3).",
            default="small"),
    KeySpec("YT_WHISPER_DEVICE", "faster-whisper device.", default="cpu", choices=("cpu", "cuda", "auto")),
    KeySpec("YT_WHISPER_COMPUTE_TYPE", "faster-whisper compute type (int8/float16/float32).",
            default="int8"),
    KeySpec("YT_STORE_PATH", "LanceDB store directory.", default="yt_lance"),
    KeySpec("YT_EMBEDDING_BACKEND", "Embedding backend.", default="local", choices=("local", "openai")),
    KeySpec("YT_EMBEDDING_MODEL",
            "Embedding model (local: all-MiniLM-L6-v2 | paraphrase-multilingual-MiniLM-L12-v2; "
            "openai: text-embedding-3-small | text-embedding-3-large). Blank = backend default."),
    KeySpec("YT_CHUNK_TARGET_S", "Transcript chunk target length (seconds).", default="45"),
    KeySpec("OPENAI_API_KEY", "OpenAI API key (for YT_EMBEDDING_BACKEND=openai).", secret=True),
    KeySpec("OPENROUTER_API_KEY", "OpenRouter API key (desktop automation path).", secret=True),
    KeySpec("YT_OPENROUTER_MODEL", "OpenRouter model id (desktop automation path).",
            default="openai/gpt-4o-mini"),
    KeySpec("HF_TOKEN", "HuggingFace token (higher rate limits for local models).", secret=True),
    KeySpec("YT_LOG_FILE", "Structured log file path.", default="logs/common.jsonl"),
    KeySpec("YT_DISCOVER_TIMEOUT_S", "discover: per-extraction timeout (s).", default="30"),
    KeySpec("YT_DISCOVER_FEED_LIMIT", "discover: cap newest feed entries pulled per run.", default="60"),
    KeySpec("YT_DISCOVER_OVERLAP_S", "discover: incremental re-fetch overlap (s).", default="3600"),
    KeySpec("YT_JOB_CONCURRENCY", "desktop backend: job worker concurrency.", default="3"),
    KeySpec("YT_DISCOVER_INTERVAL_S", "desktop backend: background discover timer (s).", default="3600"),
)
KNOWN: dict[str, KeySpec] = {s.key: s for s in _SPECS}


class UnknownKey(KeyError):
    """Raised when a key isn't a recognized yt-mem-ai setting."""


def _home() -> Path:
    return Path(os.environ.get("YT_MEM_AI_HOME") or (Path.home() / ".yt-mem-ai"))


def global_config_path() -> Path:
    """The global config file `config set` writes to by default."""
    return _home() / "config.env"


def project_env_path() -> Path:
    return Path(".env")


def config_paths() -> dict[str, str]:
    g, p = global_config_path(), project_env_path()
    return {
        "global": str(g), "global_exists": str(g.exists()),
        "project": str(p.resolve()), "project_exists": str(p.exists()),
    }


def _file_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return {k: v for k, v in dotenv_values(path).items() if v is not None}


def resolve(key: str) -> tuple[str | None, str]:
    """Return (effective_value, source) for a key.

    Source is env | project | global | default, matching load_config precedence.
    """
    if key in os.environ:
        return os.environ[key], "env"
    proj = _file_values(project_env_path())
    if key in proj:
        return proj[key], "project"
    glob = _file_values(global_config_path())
    if key in glob:
        return glob[key], "global"
    spec = KNOWN.get(key)
    return (spec.default if spec else None), "default"


def _mask(spec: KeySpec, value: str | None, reveal: bool) -> str | None:
    if value is None or value == "":
        return value
    if spec.secret and not reveal:
        return "••••••••"
    return value


def get_setting(key: str, reveal: bool = False) -> dict:
    if key not in KNOWN:
        raise UnknownKey(key)
    spec = KNOWN[key]
    value, source = resolve(key)
    return {
        "key": key, "value": _mask(spec, value, reveal), "source": source,
        "is_set": bool(value) and source != "default", "secret": spec.secret,
        "description": spec.description, "choices": list(spec.choices) if spec.choices else None,
    }


def list_settings(reveal: bool = False) -> list[dict]:
    return [get_setting(k, reveal=reveal) for k in KNOWN]


def _quote(value: str) -> str:
    # dotenv treats unquoted `#` as a comment and trims; quote when needed.
    if value == "" or any(c in value for c in ' \t#"\''):
        return '"' + value.replace('"', '\\"') + '"'
    return value


def _write_kv(path: Path, key: str, value: str | None) -> None:
    """Update-or-append `KEY=value` in a dotenv file (value=None removes it)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    prefix = f"{key}="
    out, replaced = [], False
    for line in lines:
        if line.lstrip().startswith(prefix) and not line.lstrip().startswith("#"):
            if value is not None and not replaced:
                out.append(f"{key}={_quote(value)}")
                replaced = True
            # else: drop the line (unset, or duplicate after replace)
            continue
        out.append(line)
    if value is not None and not replaced:
        out.append(f"{key}={_quote(value)}")
    path.write_text(("\n".join(out) + "\n") if out else "", encoding="utf-8")


def set_setting(key: str, value: str, scope: str = "global") -> dict:
    if key not in KNOWN:
        raise UnknownKey(key)
    spec = KNOWN[key]
    if spec.choices and value not in spec.choices:
        raise ValueError(f"{key} must be one of {list(spec.choices)}, got {value!r}")
    path = project_env_path() if scope == "project" else global_config_path()
    _write_kv(path, key, value)
    result = get_setting(key)
    result["written_to"] = str(path)
    result["scope"] = scope
    if result["source"] == "env":
        result["warning"] = (
            f"{key} is also set as a process environment variable, which overrides "
            "the file — the new value won't take effect until that env var is unset."
        )
    return result


def unset_setting(key: str, scope: str = "global") -> dict:
    if key not in KNOWN:
        raise UnknownKey(key)
    path = project_env_path() if scope == "project" else global_config_path()
    _write_kv(path, key, None)
    return {"key": key, "removed_from": str(path), "scope": scope}
