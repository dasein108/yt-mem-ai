from __future__ import annotations
import hashlib
from lancedb.embeddings import TextEmbeddingFunction, register, get_registry


@register("fake")
class FakeEmbedder(TextEmbeddingFunction):
    def generate_embeddings(self, texts):
        return [self._vec(t) for t in texts]

    def ndims(self) -> int:
        return 8

    def _vec(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [digest[i] / 255.0 for i in range(8)]


def fake_embedder():
    return get_registry().get("fake").create()


@register("fake16")
class FakeEmbedder16(TextEmbeddingFunction):
    def generate_embeddings(self, texts):
        return [self._vec(t) for t in texts]

    def ndims(self) -> int:
        return 16

    def _vec(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [digest[i % len(digest)] / 255.0 for i in range(16)]


def fake_embedder_16():
    return get_registry().get("fake16").create()


@register("fakeboom")
class FakeEmbedderBoom(TextEmbeddingFunction):
    """Declares 8 dims but returns wrong-length vectors so `table.add()` raises
    cleanly at embed time. (A raising `generate_embeddings` makes LanceDB hang
    rather than propagate.) Used to test that a failed re-embed preserves data."""
    def generate_embeddings(self, texts):
        return [[0.0, 0.0] for _ in texts]  # 2-dim ≠ declared 8 → clean add error

    def ndims(self) -> int:
        return 8


def fake_embedder_boom():
    return get_registry().get("fakeboom").create()
