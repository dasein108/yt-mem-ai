from __future__ import annotations
import os
from lancedb.embeddings import get_registry
from ..config import Config
from .models import Segment


def build_embedder(cfg: Config):
    backend = cfg.embedding_backend
    if backend == "local":
        # Surface HF_TOKEN to huggingface_hub/sentence-transformers (higher rate
        # limits, no unauthenticated-request warning). Don't override an env token.
        if cfg.hf_token:
            os.environ.setdefault("HF_TOKEN", cfg.hf_token)
        name = cfg.embedding_model or "all-MiniLM-L6-v2"
        return get_registry().get("sentence-transformers").create(name=name)
    if backend == "openai":
        if not cfg.openai_api_key:
            raise ValueError("embedding_backend='openai' requires OPENAI_API_KEY")
        name = cfg.embedding_model or "text-embedding-3-small"
        return get_registry().get("openai").create(name=name, api_key=cfg.openai_api_key)
    raise ValueError(f"unknown embedding backend: {backend!r}")


def chunk_segments(video_id: str, segments: list[Segment], target_s: float) -> list[dict]:
    if not segments:
        return []
    chunks: list[dict] = []
    start = segments[0].start_s
    end = segments[0].end_s
    parts = [segments[0].text]

    def flush() -> None:
        chunks.append({
            "id": f"{video_id}:{len(chunks)}",
            "video_id": video_id,
            "start_s": start,
            "end_s": end,
            "text": " ".join(p.strip() for p in parts).strip(),
        })

    for seg in segments[1:]:
        if end - start >= target_s:
            flush()
            start, end, parts = seg.start_s, seg.end_s, [seg.text]
        else:
            end = seg.end_s
            parts.append(seg.text)
    flush()
    return chunks
