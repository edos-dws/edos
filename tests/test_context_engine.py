"""Ticket 4.1 — Context Engine assembles a valid, ranked context package."""
from edos.engines.context import ContextEngine
from edos.models.context import validate_against_contract


def _cand(type_, ref, content, g, s, r, c, f):
    return {
        "type": type_, "ref_id": ref, "content": content,
        "signals": {"graph": g, "semantic": s, "recency": r, "confidence": c, "focus": f},
    }


def test_build_validates_and_ranks_desc():
    eng = ContextEngine()
    candidates = [
        _cand("decision", "D-1", "nRF52840 choice", 0.2, 0.2, 0.2, 0.5, 0.0),      # low
        _cand("requirement", "R-3", "report every 10s", 1.0, 0.9, 1.0, 1.0, 1.0),  # high
    ]
    pkg = eng.build(project_id="p1", intent="architecture_review",
                    entities=["nRF52840 mcu"], candidates=candidates)

    validate_against_contract(pkg.to_contract_dict())  # must not raise
    scores = [it.score for it in pkg.items]
    assert scores == sorted(scores, reverse=True)
    assert pkg.items[0].ref_id == "R-3"


def test_entities_are_rule_expanded():
    eng = ContextEngine()
    pkg = eng.build(project_id="p1", intent="q", entities=["mcu swap"], candidates=[])
    # "mcu" triggers the expansion rule
    assert "drivers" in pkg.entities
    assert "clock_tree" in pkg.entities


def test_token_budget_drops_lowest_ranked():
    eng = ContextEngine()
    candidates = [
        _cand("document", "d1", "A" * 100, 1, 1, 1, 1, 1),        # top
        _cand("document", "d2", "B" * 100, 0.1, 0.1, 0.1, 0.1, 0.1),  # dropped
    ]
    pkg = eng.build(project_id="p1", intent="q", entities=[], candidates=candidates, token_budget=120)
    assert [it.ref_id for it in pkg.items] == ["d1"]
