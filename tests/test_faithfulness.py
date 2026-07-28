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


# --- A1: Layer-2 semantic support-judge (cited -> *supported*). Fake router = deterministic/offline. ---
class _JudgeRouter:
    def __init__(self, judgments):
        self.judgments = judgments
    def execute(self, capability, context, schema=None, tier=None):
        return {"judgments": self.judgments}


class _RaisingJudge:
    def execute(self, capability, context, schema=None, tier=None):
        from edos.engines.prompt import MalformedOutputError
        raise MalformedOutputError("no valid judge output")


def test_layer2_cited_but_contradicted_becomes_ungrounded():
    d = _decision([{"claim": "IP68 rated", "source": "DS-1", "kind": "fact"}], confidence=0.8)
    texts = {"DS-1": "The enclosure is IP54 rated."}  # contradicts the IP68 claim
    r = fg.check(d, ["DS-1"], context_texts=texts,
                 router=_JudgeRouter([{"index": 0, "support": "contradicts", "confidence": 0.9}]))
    assert r.faithfulness_score == 0.0                      # the cited-but-contradicted claim isn't grounded
    assert any("contradicts" in c for c in r.ungrounded_claims)
    gated = fg.apply_gate(d, r)
    assert gated.confidence < 0.8                           # scaled down
    assert any("contradicts" in b for b in gated.freeze_blockers)


def test_layer2_cited_and_entailed_stays_grounded():
    d = _decision([{"claim": "IP68 rated", "source": "DS-1", "kind": "fact"}], confidence=0.8)
    texts = {"DS-1": "The enclosure meets IP68 for submersion to 1.5 m."}
    r = fg.check(d, ["DS-1"], context_texts=texts,
                 router=_JudgeRouter([{"index": 0, "support": "entails", "confidence": 0.95}]))
    assert r.faithfulness_score == 1.0
    assert r.grounded is True
    assert r.ungrounded_claims == []


def test_layer2_degrades_to_layer1_on_error():
    d = _decision([{"claim": "IP68", "source": "DS-1", "kind": "fact"}], confidence=0.8)
    r = fg.check(d, ["DS-1"], context_texts={"DS-1": "some text"}, router=_RaisingJudge())
    assert r.faithfulness_score == 1.0                      # Layer-1 only: source present => grounded
    assert r.grounded is True


def test_layer1_still_catches_fabricated_citation_under_layer2():
    d = _decision([{"claim": "real", "source": "DS-1", "kind": "fact"},
                   {"claim": "fake", "source": "GHOST", "kind": "fact"}], confidence=0.8)
    r = fg.check(d, ["DS-1"], context_texts={"DS-1": "supports real"},
                 router=_JudgeRouter([{"index": 0, "support": "entails", "confidence": 0.9}]))
    assert "fake" in r.ungrounded_claims                    # dangling citation caught by Layer 1
    assert r.faithfulness_score == 0.5                      # 1 of 2 grounded
