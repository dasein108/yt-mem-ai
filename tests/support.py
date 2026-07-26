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
