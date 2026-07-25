"""Tickets 5.1 + 5.2 — Decision Engine: valid decision, status cap, clarification (no guessing)."""
from edos.engines.decision import ClarificationNeeded, DecisionEngine
from edos.engines.model_router import Capability, ModelRouter
from edos.models.context import ContextItem, ContextPackage
from edos.models.decision import Decision, validate_against_contract


def _ctx(items):
    return ContextPackage(project_id="p1", intent="architecture_review", items=items)


NON_EMPTY = _ctx([ContextItem(type="requirement", content="report every 10s", score=0.9)])


def test_emits_contract_valid_decision_capped_at_recommended():
    result = DecisionEngine().analyze(NON_EMPTY)
    assert isinstance(result, Decision)
    validate_against_contract(result.to_contract_dict())
    assert result.status == "recommended"  # never verified/frozen from the Decision Engine


def test_empty_context_asks_for_clarification_not_a_guess():
    result = DecisionEngine().analyze(_ctx([]))
    assert isinstance(result, ClarificationNeeded)
    assert result.questions  # tells the caller what's missing


class _FrozenProvider:
    """A provider that (wrongly) returns a frozen decision — the engine must downgrade it."""

    def execute(self, capability: Capability, context: dict, schema: dict | None,
                prompt: str | None = None, tier=None) -> dict:
        return Decision(
            summary="s", recommendation="r", confidence=0.99, status="frozen",
            evidence=[{"claim": "c", "source": "x"}],
        ).to_contract_dict()


def test_status_is_capped_even_if_provider_returns_frozen():
    engine = DecisionEngine(router=ModelRouter(provider=_FrozenProvider()))
    result = engine.analyze(NON_EMPTY)
    assert isinstance(result, Decision)
    assert result.status == "recommended"  # frozen downgraded — no autonomous freeze here
