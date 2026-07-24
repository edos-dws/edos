"""CP-14 — faithfulness / grounding gate: evidence-source traceability + Self-RAG gate action."""
from edos.engines import faithfulness as fg
from edos.models.decision import Decision


def _decision(evidence, confidence=0.8, freeze=None):
    return Decision(summary="s", recommendation="r", confidence=confidence, status="recommended",
                    evidence=evidence, freeze_blockers=freeze or [])


def test_grounded_when_all_sources_in_context():
    d = _decision([{"claim": "c1", "source": "REQ-1", "kind": "fact"},
                   {"claim": "c2", "source": "DEC-1", "kind": "fact"}])
    r = fg.check(d, ["REQ-1", "DEC-1", "REQ-2"])
    assert r.grounded is True
    assert r.faithfulness_score == 1.0
    assert r.ungrounded_claims == []


def test_ungrounded_claim_detected():
    d = _decision([{"claim": "real", "source": "REQ-1", "kind": "fact"},
                   {"claim": "hallucinated", "source": "GHOST-9", "kind": "fact"}])
    r = fg.check(d, ["REQ-1"])
    assert r.faithfulness_score == 0.5
    assert "hallucinated" in r.ungrounded_claims
    assert r.grounded is True  # 0.5 == floor


def test_no_evidence_is_ungrounded():
    r = fg.check(_decision([]), ["REQ-1"])
    assert r.grounded is False
    assert r.faithfulness_score == 0.0


def test_gate_lowers_confidence_never_raises():
    d = _decision([{"claim": "x", "source": "GHOST", "kind": "fact"}], confidence=0.9)
    r = fg.check(d, ["REQ-1"])            # 0/1 grounded -> score 0
    gated = fg.apply_gate(d, r)
    assert gated.confidence == 0.0        # 0.9 * 0.0
    assert gated.confidence <= d.confidence
    assert any("ungrounded claim" in b for b in gated.freeze_blockers)


def test_gate_preserves_confidence_when_fully_grounded():
    d = _decision([{"claim": "x", "source": "REQ-1", "kind": "fact"}], confidence=0.8)
    gated = fg.apply_gate(d, fg.check(d, ["REQ-1"]))
    assert gated.confidence == 0.8        # 0.8 * 1.0
    assert gated.freeze_blockers == []
