# yt_summary/api/summarize.py
from __future__ import annotations
import json
from datetime import datetime, UTC
from ..config import Config
from ..store import db as store
from .. import memory

_SYSTEM = (
    "You summarize a YouTube video transcript. Respond with a JSON object with keys: "
    "summary_md (2-4 sentence executive summary plus key bullets, markdown), "
    "highlights (array of {start_s: number, label: string}, 3-8 items), "
    "qa (array of {q: string, a: string}, 3-6 items). "
    "Ground everything in the transcript. Pick start_s values from the provided chunk anchors."
)


def _nearest(sorted_starts: list[float], x: float) -> float:
    if not sorted_starts:
        return x
    return min(sorted_starts, key=lambda s: abs(s - x))


def _client(cfg: Config):
    from openai import OpenAI
    return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=cfg.openrouter_api_key)


def summarize_video(cfg: Config, db, video_id: str, client=None) -> dict:
    text = store.get_transcript_text(db, video_id)
    if not text:
        raise ValueError(f"no transcript for {video_id}; fetch it first")
    chunks = store.list_chunks(db, video_id)
    anchors = [{"start_s": c.get("start_s"), "text": c.get("text")} for c in chunks]

    if client is None:
        if not cfg.openrouter_api_key:
            raise ValueError("summarization requires OPENROUTER_API_KEY")
        client = _client(cfg)

    user = json.dumps({"transcript": text, "chunk_anchors": anchors})
    resp = client.chat.completions.create(
        model=cfg.openrouter_model,
        messages=[{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
        response_format={"type": "json_object"},
    )
    data = json.loads(resp.choices[0].message.content)

    starts = sorted(float(c["start_s"]) for c in chunks if c.get("start_s") is not None)
    for h in data.get("highlights", []):
        s = h.get("start_s")
        if isinstance(s, (int, float)):
            h["start_s"] = _nearest(starts, float(s))

    store.upsert_summary(
        db, video_id, data.get("summary_md", ""),
        json.dumps(data.get("highlights", [])), json.dumps(data.get("qa", [])),
        cfg.openrouter_model, datetime.now(UTC).isoformat())
    memory.mark_status(db, video_id, "summarized")
    return data
