# yt_mem_ai/obs.py
from __future__ import annotations
import json
import os
from datetime import datetime, UTC
from pathlib import Path


def _log_path(log_file: str | None) -> Path:
    if log_file is not None:
        return Path(log_file)
    return Path(os.environ.get("YT_LOG_FILE") or "logs/common.jsonl")


def log_event(source: str, event: str, level: str = "info", msg: str = "",
              *, log_file: str | None = None, **ctx) -> None:
    try:
        path = _log_path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = {"ts": datetime.now(UTC).isoformat(), "source": source,
                "level": level, "event": event, "msg": msg, **ctx}
        with open(path, "a") as f:
            f.write(json.dumps(line, default=str) + "\n")
    except Exception:
        pass  # logging must never break the app


def blog(event: str, level: str = "info", msg: str = "", *,
         log_file: str | None = None, **ctx) -> None:
    log_event("backend", event, level, msg, log_file=log_file, **ctx)
