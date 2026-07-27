"""Query expansion (retrieval recall). Provider-agnostic behind one factory: `get_query_expander()`.

A bare topic ("how do I sense pack current?") is a weak search query — it's a *question*, and it embeds far
from the *answers*/facts stored in the project. HyDE (Hypothetical Document Embeddings) fixes this: an LLM
writes a short hypothetical answer, and we embed THAT — a hypothetical spec/decision lands much closer to the
real stored decisions and datasheet facts, so recall jumps. Same pattern as embeddings/reranker: swap via
`EDOS_QUERY_EXPANSION`, no-op fallback keeps offline/tests deterministic.

Providers:
- `NoopExpander` — returns the query unchanged (offline/tests default).
- `GeminiHyDE` — one cheap Gemini call → a hypothetical answer, appended to the query for embedding.
"""
from __future__ import annotations

from typing import Protocol

from edos.config import settings


class QueryExpander(Protocol):
    name: str

    def expand(self, query: str) -> str:
        """Return the text to embed for the dense search (may be the query enriched with a hypothetical answer)."""
        ...


class NoopExpander:
    name = "noop"

    def expand(self, query: str) -> str:
        return query


class GeminiHyDE:
    """HyDE: ask a cheap Gemini model for a short hypothetical technical answer and embed query + answer."""

    name = "hyde"

    def __init__(self, model: str, api_key: str) -> None:
        self.model = model
        self._api_key = api_key
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google import genai  # lazy
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def expand(self, query: str) -> str:
        if not (query or "").strip():
            return query
        prompt = (
            "Write a brief, concrete hypothetical engineering answer (2-3 sentences, specific parts / "
            "parameters / standards where natural) to the question below, as if pulled from a datasheet or a "
            "prior decision. Output ONLY the answer, no preamble.\n\n"
            f"Question: {query}"
        )
        try:
            resp = self._get_client().models.generate_content(
                model=self.model, contents=prompt, config={"max_output_tokens": 160},
            )
            hyp = (getattr(resp, "text", "") or "").strip()
            return f"{query}\n{hyp}" if hyp else query
        except Exception:  # noqa: BLE001 — any failure → the plain query (never blocks retrieval)
            return query


_REGISTRY = {"noop", "hyde"}


def _select() -> str:
    choice = settings.query_expansion
    if choice == "auto":
        return "hyde" if settings.gemini_api_key else "noop"
    return choice if choice in _REGISTRY else "noop"


_cached: QueryExpander | None = None


def get_query_expander() -> QueryExpander:
    global _cached
    if _cached is None:
        name = _select()
        _cached = GeminiHyDE(settings.rerank_model, settings.gemini_api_key) if name == "hyde" \
            else NoopExpander()
    return _cached
