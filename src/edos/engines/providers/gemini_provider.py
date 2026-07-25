"""Gemini (Google) provider — real LLM behind the vendor-agnostic `Provider` seam.

The router hands `execute` a fully-rendered prompt; this provider sends it to Gemini and returns the parsed
result. The `google-genai` SDK is imported lazily, so nothing here needs the package installed until a live
call is actually made — tests and CI stay offline.

NOTE on the two temperament failure modes the EDOS benchmark surfaced for Gemini (manufacturing a false
"Critical" alarm on a sound design; caving on safety under adversarial pressure): these are addressed in the
prompt suite (`erc_core.md` — "Severity calibration" and "Holding the line on safety"), which every provider
receives verbatim through the render path. The hardening lives in the prompt, not in vendor code.
"""
from __future__ import annotations

import json

from edos.config import settings
from edos.engines.model_router import Capability, Tier
from edos.engines.providers._common import resolve_tier, result_dict

# Substrings (case-insensitive) that mark a Gemini error as retriable — the model is quota/rate limited or the
# id is wrong, so the NEXT model in the chain should be tried. An auth failure (401 / permission) is NOT here,
# so it raises immediately instead of silently walking the whole chain.
_RETRIABLE_MARKERS: tuple[str, ...] = (
    "429", "resource_exhausted", "resource exhausted", "quota", "rate limit", "rate-limit",
    "ratelimit", "too many requests", "404", "not found", "not_found",
)
# HTTP-style status codes some SDK exceptions expose as `.code`/`.status_code` — 429 (exhausted), 404 (bad id).
_RETRIABLE_CODES: frozenset[int] = frozenset({429, 404})


class GeminiProvider:
    """Routes by capability tier to an ORDERED Gemini model chain, falling forward on a retriable error.

    Each tier is a list of text models (best first). `execute` tries them in order via `generate_content`; on
    a 429 / quota / rate-limit / 404-not-found it moves to the next model, only re-raising the last error once
    the whole chain is exhausted. This keeps the engines on a real model when the primary is quota-limited,
    instead of dropping to static heuristics. `last_model` records which model actually served the last call.
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._chains: dict[Tier, list[str]] = {
            Tier.frontier: list(settings.gemini_frontier_chain),
            Tier.standard: list(settings.gemini_standard_chain),
            Tier.lightweight: list(settings.gemini_lightweight_chain),
        }
        self._client = None  # lazily constructed on first call
        self.last_model: str | None = None  # which chain model served the most recent successful call

    def _get_client(self):
        if self._client is None:
            from google import genai  # lazy — only needed for a live call

            self._client = genai.Client(api_key=self._api_key)
        return self._client

    @staticmethod
    def _is_retriable(exc: Exception) -> bool:
        """True when the error means "try the next model" (quota / rate / wrong-id), False for anything else
        (e.g. 401 auth → raise immediately). Inspects a numeric `code`/`status_code` and the string form."""
        for attr in ("code", "status_code", "status"):
            val = getattr(exc, attr, None)
            if isinstance(val, int) and val in _RETRIABLE_CODES:
                return True
        blob = str(exc).lower()
        return any(marker in blob for marker in _RETRIABLE_MARKERS)

    def execute(
        self, capability, context: dict, schema: dict | None = None, prompt: str | None = None,
        tier: Tier | None = None,
    ) -> dict:
        cap = Capability(capability)
        chain = self._chains[resolve_tier(cap, tier)]  # caller `tier` override wins over the capability tier
        text = prompt if prompt is not None else json.dumps({"capability": cap.value, "context": context})

        last_exc: Exception | None = None
        for model in chain:
            try:
                resp = self._get_client().models.generate_content(
                    model=model,
                    contents=text,
                    config={"max_output_tokens": settings.llm_max_output_tokens},
                )
            except Exception as exc:
                if self._is_retriable(exc):
                    last_exc = exc
                    continue  # this model is quota/rate limited or mis-named → try the next in the chain
                raise  # non-retriable (e.g. auth) → surface immediately
            self.last_model = model
            out = getattr(resp, "text", None) or ""
            return result_dict(cap, schema, out)

        # every model in the chain failed with a retriable error → raise the last one.
        raise last_exc if last_exc is not None else RuntimeError(
            f"no Gemini models configured for tier of capability {cap.value!r}")
