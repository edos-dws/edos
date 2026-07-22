"""Ticket 9.2 — freeze gate: refuses unless every clause holds; disabled while T is unset."""
from edos.engines.freeze import FreezeGate
from edos.models.decision import Decision


def _verified(confidence=0.95, blockers=None):
    return Decision(
        summary="s", recommendation="r", confidence=confidence, status="verified",
        evidence=[{"claim": "c", "source": "x", "kind": "fact"}],
        freeze_blockers=blockers or [],
    )


def test_freeze_disabled_when_threshold_unset():
    # Even a perfect verified decision must NOT freeze while T is undefined (fail-safe default).
    result = FreezeGate(threshold=None).apply(_verified())
    assert result.status == "verified"  # not frozen


def test_freezes_only_when_all_clauses_hold():
    gate = FreezeGate(threshold=0.85)  # example T supplied by a test, not the production value
    frozen = gate.apply(_verified(confidence=0.95))
    assert frozen.status == "frozen"
    assert frozen.freeze_blockers == []


def test_low_confidence_blocks_freeze():
    gate = FreezeGate(threshold=0.85)
    assert gate.apply(_verified(confidence=0.5)).status == "verified"


def test_blockers_present_blocks_freeze():
    gate = FreezeGate(threshold=0.85)
    assert gate.apply(_verified(blockers=["unverified assumption"])).status == "verified"


def test_open_contradiction_blocks_freeze():
    gate = FreezeGate(threshold=0.85)
    assert gate.apply(_verified(), open_contradictions=1).status == "verified"


def test_non_verified_status_blocks_freeze():
    gate = FreezeGate(threshold=0.85)
    recommended = Decision(
        summary="s", recommendation="r", confidence=0.99, status="recommended",
        evidence=[{"claim": "c", "source": "x"}],
    )
    assert gate.apply(recommended).status == "recommended"


def test_reasons_explain_refusal():
    result = FreezeGate(threshold=None).evaluate(
        Decision(summary="s", recommendation="r", confidence=0.4, status="recommended",
                 evidence=[{"claim": "c", "source": "x"}], freeze_blockers=["b"]),
        open_contradictions=2,
    )
    assert result.frozen is False
    assert len(result.reasons) >= 3  # threshold unset + not verified + blockers + contradictions
