"""Embedding providers (semantic retrieval). Provider-agnostic behind one factory: `get_embedder()`.

Everything that needs a vector (retrieval, ingestion, skip-known, coverage) calls `get_embedder()` / the
`EmbeddingProvider` interface — none of them know or care which provider is live. Adding a provider is one
class + one line in `_REGISTRY`; swapping providers is an env var (`EDOS_EMBEDDER`) + a re-embed backfill.

Providers:
- `StubEmbeddingProvider` — deterministic token-hash placeholder. NOT semantic; offline/tests only.
- `GeminiEmbeddingProvider` — real semantic embeddings via a Gemini embedding model (model-agnostic; the
  model id is config). Gemini models are 3072-dim; we request `EMBED_DIM` via Matryoshka and **re-normalise**
  (truncated Gemini vectors are not unit-length, which cosine similarity requires).

Note: Anthropic/Claude has no embeddings API — for a Claude-reasoning setup, use Gemini or Voyage here.
"""
from __future__ import annotations

import hashlib
from typing import Protocol

from edos.config import settings
from edos.db.models import EMBED_DIM


class EmbeddingProvider(Protocol):
    name: str
    dim: int

    def embed(self, text: str) -> list[float]: ...


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = sum(v * v for v in vec) ** 0.5
    return vec if norm == 0.0 else [v / norm for v in vec]


class StubEmbeddingProvider:
    """Deterministic bag-of-tokens hash embedding. NOT semantic-quality — a reproducible placeholder."""

    name = "stub"

    def __init__(self, dim: int = EMBED_DIM) -> None:
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in text.lower().split():
            h = int(hashlib.md5(token.encode()).hexdigest(), 16)  # non-crypto, deterministic bucket
            vec[h % self.dim] += 1.0
        return _l2_normalize(vec)


class GeminiEmbeddingProvider:
    """Real semantic embeddings via a Gemini embedding model (id from config → model-agnostic). Truncates the
    native 3072-dim vector to `dim` (Matryoshka) and re-normalises so cosine similarity is valid."""

    name = "gemini"

    def __init__(self, model: str, api_key: str, dim: int = EMBED_DIM) -> None:
        self.model = model
        self.dim = dim
        self._api_key = api_key
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google import genai  # lazy — only needed for a live call
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def embed(self, text: str) -> list[float]:
        from google.genai import types
        resp = self._get_client().models.embed_content(
            model=self.model, contents=text or " ",
            config=types.EmbedContentConfig(output_dimensionality=self.dim),
        )
        vals = list(resp.embeddings[0].values)
        if len(vals) != self.dim:
            # Never silently store a wrong-dimension vector: the pgvector column is fixed at EMBED_DIM and a
            # mismatched vector would corrupt the space. Fail loudly so ingest catches it and stores NULL.
            raise ValueError(f"Gemini embed returned {len(vals)}-dim vector, expected {self.dim}")
        return _l2_normalize(vals)


# Registry: add a provider here (+ its class) and it's selectable via EDOS_EMBEDDER — nothing else changes.
_REGISTRY = {"stub", "gemini"}


def _build(name: str) -> EmbeddingProvider:
    if name == "gemini":
        return GeminiEmbeddingProvider(model=settings.embed_model, api_key=settings.gemini_api_key)
    return StubEmbeddingProvider()


def _select() -> str:
    """Resolve EDOS_EMBEDDER, honouring 'auto' (gemini when a key exists, else the offline stub)."""
    choice = settings.embedder
    if choice == "auto":
        return "gemini" if settings.gemini_api_key else "stub"
    return choice if choice in _REGISTRY else "stub"


_cached: EmbeddingProvider | None = None


def get_embedder() -> EmbeddingProvider:
    """The single, cached embedder for the whole app (provider chosen by config)."""
    global _cached
    if _cached is None:
        _cached = _build(_select())
    return _cached


def default_embedder() -> EmbeddingProvider:
    """Backwards-compatible alias — callers keep using this; it now returns the configured provider."""
    return get_embedder()
