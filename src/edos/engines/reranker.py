"""Rerankers (retrieval precision). Provider-agnostic behind one factory: `get_reranker()`.

A bi-encoder (embeddings) match is coarse — it scores query and document independently. A reranker reads the
query and a candidate *together* and scores true relevance, so it can promote the genuinely-on-point items
out of a top-50 kNN pool down to a sharp top-K. Same pattern as embeddings: swap providers via `EDOS_RERANKER`
(1 class + 1 registry line), stub/no-op fallback keeps tests & offline runs deterministic.

Providers:
- `NoopReranker` — identity order (keeps the caller's existing rank). Offline/tests default.
- `GeminiReranker` — LLM-as-reranker via a cheap Gemini model (already-configured key; no new vendor).
  A dedicated cross-encoder (Cohere / Voyage rerank) plugs in here later with no caller changes.
"""
from __future__ import annotations

import json
import re
from typing import Protocol

from edos.config import settings


class RerankProvider(Protocol):
    name: str

    def rerank(self, query: str, docs: list[str], top_k: int) -> list[int]:
        """Return doc indices, most-relevant first, length ≤ top_k."""
        ...


class NoopReranker:
    name = "noop"

    def rerank(self, query: str, docs: list[str], top_k: int) -> list[int]:
        return list(range(min(top_k, len(docs))))


class GeminiReranker:
    """LLM-as-reranker: ask a cheap Gemini model to order candidates by relevance to the query."""

    name = "gemini"

    def __init__(self, model: str, api_key: str) -> None:
        self.model = model
        self._api_key = api_key
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google import genai  # lazy
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def rerank(self, query: str, docs: list[str], top_k: int) -> list[int]:
        if not docs:
            return []
        listing = "\n".join(f"[{i}] {(d or '')[:300]}" for i, d in enumerate(docs))
        prompt = (
            "You are a retrieval reranker. Order the documents by how directly they help answer / inform "
            f"the QUERY. Return ONLY JSON: {{\"order\": [indices]}} — most relevant first, at most {top_k} "
            "indices, drop clearly-irrelevant ones.\n\n"
            f"QUERY: {query}\n\nDOCUMENTS:\n{listing}"
        )
        try:
            resp = self._get_client().models.generate_content(
                model=self.model, contents=prompt,
                config={"max_output_tokens": 300, "response_mime_type": "application/json"},
            )
            raw = getattr(resp, "text", "") or ""
            order = json.loads(raw).get("order") if raw.strip().startswith("{") else None
            if order is None:  # tolerate a bare array or noisy text
                order = json.loads(re.search(r"\[[\d,\s]*\]", raw).group(0))
            seen, out = set(), []
            for i in order:
                i = int(i)
                if 0 <= i < len(docs) and i not in seen:
                    seen.add(i)
                    out.append(i)
                if len(out) >= top_k:
                    break
            return out or NoopReranker().rerank(query, docs, top_k)
        except Exception:  # noqa: BLE001 — any failure → identity order (never blocks retrieval)
            return NoopReranker().rerank(query, docs, top_k)


_REGISTRY = {"noop", "gemini"}


def _select() -> str:
    choice = settings.reranker
    if choice == "auto":
        return "gemini" if settings.gemini_api_key else "noop"
    return choice if choice in _REGISTRY else "noop"


_cached: RerankProvider | None = None


def get_reranker() -> RerankProvider:
    global _cached
    if _cached is None:
        name = _select()
        _cached = GeminiReranker(settings.rerank_model, settings.gemini_api_key) if name == "gemini" \
            else NoopReranker()
    return _cached
