"""Anthropic (Claude) provider — real LLM behind the vendor-agnostic `Provider` seam.

The router hands `execute` a fully-rendered prompt (template + ERC core + context package + output schema);
this provider sends it to Claude and returns the parsed result. The `anthropic` SDK is imported lazily, so
nothing here needs the package installed until a live call is actually made — tests and CI stay offline.
"""
from __future__ import annotations

import json

from edos.config import settings
from edos.engines.model_router import Capability, Tier, tier_for
from edos.engines.providers._common import resolve_model, result_dict


class AnthropicProvider:
    """Routes by capability tier to a Claude model. Opus (frontier) reasons decisions/verification; Sonnet
    (standard) handles clarification/knowledge; Haiku (lightweight) handles intent/tagging."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._models: dict[Tier, str] = {
            Tier.frontier: settings.anthropic_frontier_model,
            Tier.standard: settings.anthropic_standard_model,
            Tier.lightweight: settings.anthropic_lightweight_model,
        }
        self._client = None  # lazily constructed on first call

    def _get_client(self):
        if self._client is None:
            import anthropic  # lazy — only needed for a live call

            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def execute(self, capability, context: dict, schema: dict | None = None, prompt: str | None = None) -> dict:
        cap = Capability(capability)
        tier = tier_for(cap)
        model = resolve_model(cap, self._models)
        text = prompt if prompt is not None else json.dumps({"capability": cap.value, "context": context})

        kwargs: dict = {
            "model": model,
            "max_tokens": settings.llm_max_output_tokens,
            "messages": [{"role": "user", "content": text}],
        }
        # Adaptive thinking + effort are supported on the frontier/standard tiers (Opus 4.8 / Sonnet 5) and
        # give the reasoning quality this task needs. The lightweight tier (Haiku 4.5) rejects them, so omit.
        if tier in (Tier.frontier, Tier.standard):
            kwargs["thinking"] = {"type": "adaptive"}
            kwargs["output_config"] = {"effort": "high"}

        resp = self._get_client().messages.create(**kwargs)
        out = "".join(
            block.text for block in resp.content if getattr(block, "type", None) == "text"
        )
        return result_dict(cap, schema, out)
