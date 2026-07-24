"""Ticket 8.1 — Knowledge Engine: extraction → normalization → quality gates before persist."""
from edos.engines.knowledge import KnowledgeEngine
from edos.models.decision import Decision


def _decision(**over):
    base = {
        "summary": "Use STM32 H743", "recommendation": "Adopt STM32 H743 for headroom",
        "confidence": 0.8, "status": "verified",
        "evidence": [{"claim": "STM32 H743 has more RAM", "source": "datasheet", "kind": "fact"}],
    }
    base.update(over)
    return Decision(**base)


def test_produces_normalized_knowledge_that_passes_gates():
    items = KnowledgeEngine().process(_decision(), project_id="p1")
    assert items
    contents = [it.content for it in items]
    # normalization collapsed "STM32 H743" -> "STM32H743"
    assert any("STM32H743" in c for c in contents)
    assert all(it.project_id == "p1" for it in items)  # attribution present


def test_duplicate_facts_are_deduped_before_persist():
    d = _decision(evidence=[
        {"claim": "duplicate fact", "source": "a", "kind": "fact"},
        {"claim": "duplicate fact", "source": "b", "kind": "fact"},
    ])
    items = KnowledgeEngine().process(d, project_id="p1")
    facts = [it for it in items if it.content == "duplicate fact"]
    assert len(facts) == 1  # deduped


def test_low_confidence_recommendation_dropped():
    items = KnowledgeEngine().process(_decision(confidence=0.1), project_id="p1")
    # the recommendation (confidence 0.1 < floor) is dropped; only the fact (0.9) survives
    assert all(it.content != "Adopt STM32H743 for headroom" for it in items)


def test_missing_attribution_is_a_hard_gate_failure():
    eng = KnowledgeEngine()
    items = eng.extract(_decision(), project_id="")  # no attribution
    gate = eng.hard_gate(items)
    assert gate.passed is False
    assert "missing source attribution" in gate.reasons
