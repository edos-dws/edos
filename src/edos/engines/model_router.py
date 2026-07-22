"""Model Router (roadmap Ch 4).

"Models are interchangeable. Route by capability, not vendor." The router picks a capability tier, calls a
provider, and (if a schema is given) guarantees the output validates before returning it.

CP-2: the only provider is `StubProvider` — deterministic, schema-valid fixtures, NO live LLM. Real
providers arrive at CP-4. The repair/fallback loop (ticket 3.3) is layered on in `engines/prompt.py`.
"""
from __future__ import annotations

from enum import Enum
from typing import Protocol

from edos.engines.prompt import produce_valid
from edos.models.decision import Decision
from edos.prompts.render import render


class Capability(str, Enum):
    intent = "intent"
    entity_extraction = "entity_extraction"
    summarization = "summarization"
    clarification = "clarification"
    knowledge_extraction = "knowledge_extraction"
    impact_triage = "impact_triage"
    decision = "decision"
    verification = "verification"


class Tier(int, Enum):
    lightweight = 1  # intent, tagging, summarization
    standard = 2     # clarification, knowledge extraction, impact triage
    frontier = 3     # engineering decisions, verification escalation


# Task → tier table (roadmap Ch 4).
CAPABILITY_TIER: dict[Capability, Tier] = {
    Capability.intent: Tier.lightweight,
    Capability.entity_extraction: Tier.lightweight,
    Capability.summarization: Tier.lightweight,
    Capability.clarification: Tier.standard,
    Capability.knowledge_extraction: Tier.standard,
    Capability.impact_triage: Tier.standard,
    Capability.decision: Tier.frontier,
    Capability.verification: Tier.frontier,
}


def tier_for(capability: Capability | str) -> Tier:
    return CAPABILITY_TIER[Capability(capability)]


class Provider(Protocol):
    def execute(
        self, capability: Capability, context: dict, schema: dict | None, prompt: str | None = None
    ) -> dict: ...


class StubProvider:
    """Deterministic, schema-valid fixtures. No live model. `prompt` is the fully-rendered prompt a real
    provider would send; the stub ignores it (it exists so the wiring is proven before go-live)."""

    def execute(
        self, capability: Capability, context: dict, schema: dict | None = None, prompt: str | None = None
    ) -> dict:
        cap = Capability(capability)
        if cap == Capability.decision:
            return Decision(
                summary="[stub] decision",
                recommendation="[stub] recommendation",
                confidence=0.5,
                status="recommended",  # stub never freezes
                evidence=[{"claim": "assembled context", "source": "stub", "kind": "inference"}],
            ).to_contract_dict()
        return {"capability": cap.value, "stub": True}


class ModelRouter:
    def __init__(self, provider: Provider | None = None, fallback: Provider | None = None) -> None:
        self.provider: Provider = provider or StubProvider()
        self.fallback: Provider = fallback or self.provider

    def execute(self, capability: Capability | str, context: dict, schema: dict | None = None) -> dict:
        cap = Capability(capability)
        _ = tier_for(cap)  # tier selection (routing to a real model happens at go-live)
        if schema is None:
            return self.provider.execute(cap, context, None, render(cap, context, None))
        # generate → repair-retry (same provider, repair hint) → fallback provider (Ch 9). Each attempt gets
        # its fully-rendered prompt. If none produce schema-valid JSON, produce_valid raises → nothing persists.
        repair_ctx = {**context, "_repair": True}
        return produce_valid(
            schema,
            [
                lambda: self.provider.execute(cap, context, schema, render(cap, context, schema)),
                lambda: self.provider.execute(cap, repair_ctx, schema, render(cap, repair_ctx, schema)),
                lambda: self.fallback.execute(cap, context, schema, render(cap, context, schema)),
            ],
        )
