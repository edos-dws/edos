"""Shared helpers for live providers: capability→model resolution and JSON extraction.

Kept vendor-neutral so Gemini and Anthropic providers stay thin. Neither function imports a vendor SDK.
"""
from __future__ import annotations

import json

from edos.engines.model_router import Capability, Tier, tier_for


def result_dict(capability, schema: dict | None, text: str) -> dict:
    """Shape a provider's raw text into what the Model Router expects.

    With a schema, return the parsed JSON object (the repair loop validates it — a parse failure returns a
    non-validating dict rather than raising, so `produce_valid` can move to repair/fallback). Without a
    schema, wrap the text so non-contract capabilities still return a dict.
    """
    cap = Capability(capability)
    if schema is None:
        return {"capability": cap.value, "text": text}
    return extract_json(text)


def extract_json(text: str) -> dict:
    """Best-effort extraction of a single JSON object from model output.

    Handles bare JSON, ```json fenced blocks, and prose-wrapped JSON. On failure returns a sentinel dict that
    will not satisfy any decision contract, so the router's repair/fallback attempts run instead of raising.
    """
    s = (text or "").strip()
    # whole-string parse first (the prompts ask for "JSON only")
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else {"_malformed": text}
    except json.JSONDecodeError:
        pass
    # strip a leading/trailing code fence if present
    if s.startswith("```"):
        s = s.split("\n", 1)[-1]
        if s.rstrip().endswith("```"):
            s = s.rstrip()[: -3]
        s = s.strip()
        try:
            obj = json.loads(s)
            return obj if isinstance(obj, dict) else {"_malformed": text}
        except json.JSONDecodeError:
            pass
    # last resort: first balanced {...} span
    start = s.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(s)):
            if s[i] == "{":
                depth += 1
            elif s[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(s[start : i + 1])
                        return obj if isinstance(obj, dict) else {"_malformed": text}
                    except json.JSONDecodeError:
                        break
    return {"_malformed": text}


def resolve_model(capability, models: dict[Tier, str]) -> str:
    """Pick the model id for a capability's tier from a {Tier: model_id} map."""
    return models[tier_for(Capability(capability))]
