"""Ticket 3.3 — JSON validate → repair → fallback → reject; malformed is never returned/persisted."""
import pytest

from edos.engines.model_router import Capability, ModelRouter, Provider
from edos.engines.prompt import MalformedOutputError, produce_valid
from edos.models.decision import decision_contract

SCHEMA = {"type": "object", "required": ["ok"], "properties": {"ok": {"const": True}}}


def test_repair_returns_first_valid_attempt():
    calls = {"n": 0}
    seen_errors = []

    def flaky(err):  # attempts now receive the previous validation error (None on the first)
        calls["n"] += 1
        seen_errors.append(err)
        return {"ok": False} if calls["n"] == 1 else {"ok": True}  # malformed first, valid on repair

    out = produce_valid(SCHEMA, [flaky, flaky])
    assert out == {"ok": True}
    assert calls["n"] == 2  # repaired on the second attempt
    assert seen_errors[0] is None                    # first attempt has no prior error
    assert seen_errors[1] is not None                # the repair attempt is handed the concrete failure


def test_all_malformed_is_rejected_not_returned():
    with pytest.raises(MalformedOutputError):
        produce_valid(SCHEMA, [lambda _e: {"ok": False}, lambda _e: {"ok": "nope"}])


class _BadThenGoodProvider:
    """Malformed on first call, valid (decision) on repair — exercises the router's repair path."""

    def __init__(self) -> None:
        self.calls = 0

    def execute(self, capability: Capability, context: dict, schema: dict | None,
                prompt: str | None = None, tier=None) -> dict:
        self.calls += 1
        if self.calls == 1:
            return {"not": "a decision"}
        from edos.models.decision import Decision
        return Decision(
            summary="s", recommendation="r", confidence=0.5, status="recommended",
            evidence=[{"claim": "c", "source": "stub"}],
        ).to_contract_dict()


def test_router_repairs_malformed_provider_output():
    provider: Provider = _BadThenGoodProvider()
    router = ModelRouter(provider=provider)
    out = router.execute(Capability.decision, context={"project_id": "p1"}, schema=decision_contract())
    assert out["status"] == "recommended"
    assert provider.calls == 2  # first malformed, repaired on retry


class _AlwaysBadProvider:
    def execute(self, capability, context, schema, prompt=None, tier=None):
        return {"garbage": True}


def test_router_rejects_when_never_valid():
    router = ModelRouter(provider=_AlwaysBadProvider(), fallback=_AlwaysBadProvider())
    with pytest.raises(MalformedOutputError):
        router.execute(Capability.decision, context={}, schema=decision_contract())
