"""Prompt composition (roadmap Ch 9/16).

Renders the full prompt a provider will send: the versioned template (with ERC core substituted) + the
pre-assembled context package + the output schema. This is what wires the authored prompts into the actual
request path — the Model Router renders here and hands the result to the provider.
"""
from __future__ import annotations

import json

from edos.prompts.registry import load_template

# Which registered prompt drives each capability.
CAPABILITY_PROMPT: dict[str, str] = {
    "decision": "decision_prompt:v1",
    "verification": "verification_prompt:v1",
    "intent": "planner_prompt:v1",
    "knowledge_extraction": "knowledge_extraction_prompt:v1",
    "deepdive": "deepdive_prompt:v1",
    "findings": "findings_prompt:v1",
    "challenge": "challenge_prompt:v1",
}


def _cap_key(capability) -> str:
    return capability.value if hasattr(capability, "value") else str(capability)


def prompt_ref_for(capability) -> str | None:
    return CAPABILITY_PROMPT.get(_cap_key(capability))


def render(capability, context: dict, schema: dict | None = None) -> str:
    """Compose template + context package + output schema into one prompt string."""
    ref = prompt_ref_for(capability)
    if ref is None:
        # No registered prompt for this capability — hand the provider the raw context.
        return json.dumps({"capability": _cap_key(capability), "context": context}, ensure_ascii=False)

    parts = [
        load_template(ref),
        "\n\n# CONTEXT PACKAGE\n",
        json.dumps(context, ensure_ascii=False, indent=2),
    ]
    if schema is not None:
        parts += ["\n\n# OUTPUT SCHEMA — return JSON matching this exactly\n",
                  json.dumps(schema, ensure_ascii=False)]
    return "".join(parts)
