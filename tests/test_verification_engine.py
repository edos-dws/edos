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


# --- A2: independent LLM critic wired through the router (fake router = deterministic, offline) ---
class _CriticRouter:
    """A fake ModelRouter whose verification call returns a fixed verdict payload."""
    def __init__(self, verdict: dict) -> None:
        self.verdict = verdict
    def execute(self, capability, context, schema=None, tier=None) -> dict:
        return self.verdict


class _RaisingRouter:
    def execute(self, capability, context, schema=None, tier=None) -> dict:
        from edos.engines.prompt import MalformedOutputError
        raise MalformedOutputError("no schema-valid critic output")


def test_llm_critic_disagreement_lowers_confidence_and_records_blockers():
    # GOOD has no structural issue, but the independent critic disagrees → confidence strictly lower,
    # status stays recommended, and the critic's issues become freeze_blockers.
    router = _CriticRouter({"agreement": False, "adjusted_confidence": 0.3,
                            "issues": ["contradicts a prior decision on the SoC family"]})
    eng = VerificationEngine(router=router)
    v = eng.verify(GOOD)
    assert v.agreement is False
    assert v.adjusted_confidence < GOOD.confidence
    assert any("contradicts" in i for i in v.issues)
    promoted = eng.promote(GOOD, v)
    assert promoted.status == "recommended"                       # not promoted
    assert any("contradicts" in b for b in promoted.freeze_blockers)


def test_llm_critic_cannot_raise_confidence_adversarial():
    # Adversarial: the critic claims a HIGHER confidence than the decision. The clamp (code, not prompt)
    # must hold — confidence never increases.
    router = _CriticRouter({"agreement": True, "adjusted_confidence": 0.99, "issues": []})
    v = VerificationEngine(router=router).verify(GOOD)  # decision confidence 0.8
    assert v.adjusted_confidence <= GOOD.confidence
    assert v.adjusted_confidence == 0.8                            # held at the decision's own confidence


def test_llm_critic_malformed_degrades_to_deterministic_floor():
    # A critic that errors (offline / malformed) must never break verification — it degrades to the floor.
    eng = VerificationEngine(router=_RaisingRouter())
    assert eng.verify(GOOD).adjusted_confidence == 0.8            # floor: no structural issue
    v_bad = eng.verify(UNSUPPORTED)
    assert v_bad.agreement is False and v_bad.issues              # floor: structural issue still caught


def test_verify_with_no_refs_skips_faithfulness_double_run():
    # The /v1/analyze integration passes context_refs=None so faithfulness runs exactly once (in apply_gate),
    # not a second time inside verify. Proven here: no refs => no faithfulness score computed.
    assert VerificationEngine().verify(GOOD, context_refs=None).faithfulness is None
    # and when refs ARE given (the /v1/verify path), the faithfulness pass does run.
    assert VerificationEngine().verify(GOOD, context_refs=["R-1"]).faithfulness is not None
