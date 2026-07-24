"""Tickets 6.1 + 6.2 — Verification Engine: critique (lower-only) + gated status promotion."""
from edos.engines.verification import VerificationEngine
from edos.models.decision import Decision

GOOD = Decision(
    summary="Use STM32WL", recommendation="Switch SoC", confidence=0.8, status="recommended",
    evidence=[{"claim": "nRF52840 has no LoRa", "source": "datasheet", "kind": "fact"}],
)
UNSUPPORTED = Decision(
    summary="Use STM32WL", recommendation="Switch SoC", confidence=0.8, status="recommended",
    evidence=[],  # no supporting evidence
)


def test_agreement_when_no_issues_keeps_confidence():
    v = VerificationEngine().verify(GOOD)
    assert v.agreement is True
    assert v.issues == []
    assert v.adjusted_confidence == 0.8  # unchanged


def test_unsupported_claim_lowers_confidence_and_disagrees():
    v = VerificationEngine().verify(UNSUPPORTED)
    assert v.agreement is False
    assert v.issues
    assert v.adjusted_confidence < 0.8  # only lowered


def test_confidence_never_increases():
    eng = VerificationEngine()
    for d in (GOOD, UNSUPPORTED):
        assert eng.verify(d).adjusted_confidence <= d.confidence


def test_promotion_to_verified_only_on_agreement():
    eng = VerificationEngine()
    promoted = eng.promote(GOOD, eng.verify(GOOD))
    assert promoted.status == "verified"
    assert promoted.freeze_blockers == []


def test_disagreement_blocks_promotion_and_records_blockers():
    eng = VerificationEngine()
    result = eng.promote(UNSUPPORTED, eng.verify(UNSUPPORTED))
    assert result.status == "recommended"  # not promoted
    assert result.freeze_blockers  # blockers recorded for the freeze gate (CP-9)


def test_verification_never_reaches_frozen():
    eng = VerificationEngine()
    assert eng.promote(GOOD, eng.verify(GOOD)).status != "frozen"


# --- regression: verify must never wipe the author's declared freeze_blockers ---
WITH_BLOCKERS = Decision(
    summary="Use STM32WL", recommendation="Switch SoC", confidence=0.8, status="recommended",
    evidence=[{"claim": "nRF52840 has no LoRa", "source": "datasheet", "kind": "fact"}],
    freeze_blockers=["Time-multiplex scheme must be proven on test bench before freezing schematic"],
)


def test_promotion_preserves_author_freeze_blockers():
    """Agreement promotes to verified but must carry the author's freeze_blockers forward, not wipe them.

    A verified decision can still hold freeze_blockers; only the CP-9 freeze gate clears/enforces them.
    """
    eng = VerificationEngine()
    promoted = eng.promote(WITH_BLOCKERS, eng.verify(WITH_BLOCKERS))
    assert promoted.status == "verified"
    assert promoted.freeze_blockers == WITH_BLOCKERS.freeze_blockers  # preserved, not []


def test_disagreement_appends_without_dropping_existing_blockers():
    eng = VerificationEngine()
    unsupported_with_blocker = UNSUPPORTED.model_copy(update={
        "freeze_blockers": ["Bench validation pending"],
    })
    result = eng.promote(unsupported_with_blocker, eng.verify(unsupported_with_blocker))
    assert result.status == "recommended"
    assert "Bench validation pending" in result.freeze_blockers  # original kept
    assert len(result.freeze_blockers) > 1  # verify issues appended on top
