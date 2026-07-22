"""End-to-end: Context Engine → Decision Engine → Verification → Freeze gate compose correctly.

Proves the pieces line up (all on the stub LLM). Two paths: a well-supported decision that can reach a
freeze only when the gate is armed; and an unsupported decision that verification refuses to promote.
"""
from edos.engines.context import ContextEngine
from edos.engines.decision import DecisionEngine
from edos.engines.freeze import FreezeGate
from edos.engines.verification import VerificationEngine
from edos.models.decision import Decision, validate_against_contract


def _pkg(items):
    return ContextEngine().build(project_id="p1", intent="architecture_review", entities=["mcu"],
                                 candidates=items)


def _cand(ref, content):
    return {"type": "requirement", "ref_id": ref, "content": content,
            "signals": {"graph": 0.9, "semantic": 0.9, "recency": 0.9, "confidence": 0.9, "focus": 0.9}}


def test_full_pipeline_supported_decision_can_reach_freeze_when_gate_armed():
    # 1. assemble context → 2. decide
    decision = DecisionEngine().analyze(_pkg([_cand("R1", "LoRaWAN reporting")]))
    assert isinstance(decision, Decision)
    validate_against_contract(decision.to_contract_dict())
    assert decision.status == "recommended"

    # give it real supporting evidence so verification can agree
    decision = decision.model_copy(update={
        "confidence": 0.95,
        "evidence": [{"claim": "requirement present", "source": "ctx:R1", "kind": "fact"}],
    })

    # 3. verify → promote to verified (agreement, no blockers)
    ve = VerificationEngine()
    verdict = ve.verify(decision)
    assert verdict.agreement is True
    verified = ve.promote(decision, verdict)
    assert verified.status == "verified"
    assert verified.freeze_blockers == []

    # 4. freeze gate DISABLED by default → no freeze
    assert FreezeGate(threshold=None).apply(verified).status == "verified"
    # 4b. gate armed with an example threshold → freezes only now
    frozen = FreezeGate(threshold=0.85).apply(verified)
    assert frozen.status == "frozen"


def test_full_pipeline_unsupported_decision_is_refused_all_the_way():
    # a decision with no evidence should never reach frozen
    bad = Decision(summary="s", recommendation="r", confidence=0.99, status="recommended", evidence=[])
    ve = VerificationEngine()
    verdict = ve.verify(bad)
    assert verdict.agreement is False
    promoted = ve.promote(bad, verdict)
    assert promoted.status == "recommended"        # not promoted
    assert promoted.freeze_blockers                 # blockers recorded
    # even with the gate armed, blockers + non-verified refuse the freeze
    assert FreezeGate(threshold=0.85).apply(promoted).status == "recommended"
