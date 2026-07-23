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
from edos.engines.model_router import Capability, Tier, tier_for
from edos.engines.providers._common import resolve_model, result_dict


class GeminiProvider:
    """Routes by capability tier to a Gemini model (Pro = frontier, Flash = standard/lightweight)."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._models: dict[Tier, str] = {
            Tier.frontier: settings.gemini_frontier_model,
            Tier.standard: settings.gemini_standard_model,
            Tier.lightweight: settings.gemini_lightweight_model,
        }
        self._client = None  # lazily constructed on first call

    def _get_client(self):
        if self._client is None:
            from google import genai  # lazy — only needed for a live call

            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def execute(self, capability, context: dict, schema: dict | None = None, prompt: str | None = None) -> dict:
        cap = Capability(capability)
        _ = tier_for(cap)  # tier is encoded in the model map
        model = resolve_model(cap, self._models)
        text = prompt if prompt is not None else json.dumps({"capability": cap.value, "context": context})

        resp = self._get_client().models.generate_content(
            model=model,
            contents=text,
            config={"max_output_tokens": settings.llm_max_output_tokens},
        )
        out = getattr(resp, "text", None) or ""
        return result_dict(cap, schema, out)
