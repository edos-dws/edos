"""Ticket 3.1 — Model Router: capability→tier routing + schema-valid stub output."""
import pytest

from edos.engines.model_router import Capability, ModelRouter, Tier, tier_for
from edos.models.decision import decision_contract, validate_against_contract


def test_capability_tier_table_matches_ch4():
    assert tier_for(Capability.intent) == Tier.lightweight
    assert tier_for(Capability.clarification) == Tier.standard
    assert tier_for(Capability.decision) == Tier.frontier
    assert tier_for(Capability.verification) == Tier.frontier


def test_decision_capability_returns_contract_valid_output():
    router = ModelRouter()
    out = router.execute(Capability.decision, context={"project_id": "p1"}, schema=decision_contract())
    validate_against_contract(out)  # must not raise
    assert out["status"] == "recommended"  # stub never freezes


def test_schema_mismatch_raises():
    router = ModelRouter()
    # non-decision capability returns a stub dict that will NOT satisfy the decision schema
    with pytest.raises(Exception):
        router.execute(Capability.intent, context={}, schema=decision_contract())


def test_no_schema_returns_raw_stub():
    router = ModelRouter()
    out = router.execute(Capability.intent, context={})
    assert out == {"capability": "intent", "stub": True}
