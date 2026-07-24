"""Embedding provider (CP-12). Behind an interface so a real model plugs in at go-live (OD-1).

The stub is deterministic (token-hash → fixed-dim vector, L2-normalized) so tests are reproducible and
semantically-overlapping texts get closer vectors — enough to exercise the retrieval plumbing (CP-13)
without a live model. Real embeddings (and the true dimension) are an open decision (OD-1).
"""
from __future__ import annotations

import hashlib
from typing import Protocol

from edos.db.models import EMBED_DIM


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> list[float]: ...


class StubEmbeddingProvider:
    """Deterministic bag-of-tokens hash embedding. NOT semantic-quality — a reproducible placeholder."""

    def __init__(self, dim: int = EMBED_DIM) -> None:
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in text.lower().split():
            h = int(hashlib.md5(token.encode()).hexdigest(), 16)  # noqa: S324 — non-crypto, deterministic bucket
            vec[h % self.dim] += 1.0
        norm = sum(v * v for v in vec) ** 0.5
        if norm == 0.0:
            return vec
        return [v / norm for v in vec]


_default: EmbeddingProvider = StubEmbeddingProvider()


def default_embedder() -> EmbeddingProvider:
    return _default
