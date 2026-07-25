"""Deep-dive per-capability tier routing: cheap tasks (question / follow-up generation) go to the LIGHTWEIGHT
chain, heavy reasoning (decide) to the FRONTIER chain — so the good model's limited quota is preserved.

A spy router records the `tier` it is handed and then raises, which sends deep-dive down its deterministic
heuristic fallback (all its LLM calls are wrapped in try/except). That lets these run with no DB and no LLM.
"""
from edos.engines import deepdive
from edos.engines.model_router import Tier


class _SpyRouter:
    """Records the tier of every execute() call, then raises so deep-dive uses its heuristic fallback."""

    def __init__(self) -> None:
        self.tiers: list[Tier | None] = []

    def execute(self, capability, context, schema=None, tier=None):
        self.tiers.append(tier)
        raise RuntimeError("spy: force the heuristic fallback")


def test_question_generation_routes_to_lightweight_tier():
    spy = _SpyRouter()
    deepdive._candidate_questions("Peak current 100A MOSFET selection", spy)
    assert spy.tiers == [Tier.lightweight]


def test_follow_up_generation_routes_to_lightweight_tier():
    spy = _SpyRouter()
    # object() session is fine: deep-dive's retrieval/persistence are best-effort (try/except).
    deepdive._llm_followups(object(), "p1", "some topic", [{"answer": "an answer"}], 2, spy)
    assert spy.tiers == [Tier.lightweight]


def test_decide_routes_to_frontier_tier():
    spy = _SpyRouter()
    deepdive.decide(object(), "p1", "Option A vs Option B power stage", [], router=spy)
    assert spy.tiers == [Tier.frontier]
