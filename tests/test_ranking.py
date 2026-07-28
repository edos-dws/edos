"""Ticket 4.2 — the Ch 15 ranking formula. + Consolidation golden tests: the two historical ranking
formulas (decision-path `rank_score`, selection-path `retrieval._rank_score`) were collapsed onto one
`ranking.blend`; these lock that the collapse is behaviour-preserving (same score as before)."""
import pytest

from edos.engines import ranking
from edos.engines.ranking import RANK_WEIGHTS, rank_score


def test_weights_sum_to_one():
    assert abs(sum(RANK_WEIGHTS.values()) - 1.0) < 1e-9


def test_pure_graph_equals_its_weight():
    assert rank_score(graph=1, semantic=0, recency=0, confidence=0, focus=0) == pytest.approx(0.40)


def test_hand_computed_mixed():
    # 0.40*0.5 + 0.30*0.5 + 0.15*1 + 0.10*1 + 0.05*0 = 0.20+0.15+0.15+0.10 = 0.60
    s = rank_score(graph=0.5, semantic=0.5, recency=1.0, confidence=1.0, focus=0.0)
    assert s == pytest.approx(0.60)


def test_higher_signals_rank_higher():
    high = rank_score(graph=1, semantic=1, recency=1, confidence=1, focus=1)
    low = rank_score(graph=0, semantic=0, recency=0, confidence=0, focus=1)
    assert high == pytest.approx(1.0)
    assert low == pytest.approx(0.05)
    assert high > low


def test_out_of_range_rejected():
    with pytest.raises(ValueError):
        rank_score(graph=2.0, semantic=0, recency=0, confidence=0, focus=0)


# --- Consolidation: the collapse onto one `blend` is behaviour-preserving ---------------------------------

def _old_decision_formula(s: dict) -> float:
    """The pre-refactor decision-path formula, inlined verbatim (graph-led, no feedback)."""
    return (0.40 * s["graph"] + 0.30 * s["semantic"] + 0.15 * s["recency"]
            + 0.10 * s["confidence"] + 0.05 * s["focus"])


def _old_selection_formula(s: dict) -> float:
    """The pre-refactor selection-path `_rank_score`, inlined verbatim (semantic-led + bounded feedback)."""
    fb = max(-1.0, min(1.0, s.get("feedback", 0.0) / 3.0))
    return (0.45 * s["semantic"] + 0.25 * s["graph"] + 0.15 * s["recency"]
            + 0.10 * s["focus"] + 0.05 * s["confidence"] + 0.10 * fb)


_GOLDEN_SIGNALS = [
    {"graph": 0.8, "semantic": 0.6, "recency": 0.4, "confidence": 0.9, "focus": 1.0, "feedback": 1.5},
    {"graph": 0.0, "semantic": 1.0, "recency": 0.5, "confidence": 0.3, "focus": 0.3, "feedback": -3.0},
    {"graph": 0.5, "semantic": 0.5, "recency": 0.5, "confidence": 0.5, "focus": 0.5, "feedback": 0.0},
]


@pytest.mark.parametrize("s", _GOLDEN_SIGNALS)
def test_blend_reproduces_old_decision_formula(s):
    # decision path = graph-led weights, NO feedback term — identical to the old inline formula
    assert ranking.blend(s, RANK_WEIGHTS) == pytest.approx(_old_decision_formula(s))


@pytest.mark.parametrize("s", _GOLDEN_SIGNALS)
def test_blend_reproduces_old_selection_formula(s):
    # selection path = semantic-led weights + bounded feedback nudge — identical to the old _rank_score
    got = ranking.blend(s, ranking.RETRIEVAL_WEIGHTS, feedback_weight=ranking.FEEDBACK_WEIGHT)
    assert got == pytest.approx(_old_selection_formula(s))


def test_both_weight_sets_are_base_normalised():
    assert abs(sum(RANK_WEIGHTS.values()) - 1.0) < 1e-9
    assert abs(sum(ranking.RETRIEVAL_WEIGHTS.values()) - 1.0) < 1e-9


def test_blend_ignores_signals_not_in_weight_set():
    # a signal key the weight set doesn't rank (e.g. feedback on the decision path) must not change the score
    s = {"graph": 0.7, "semantic": 0.2, "recency": 0.4, "confidence": 0.8, "focus": 0.1}
    assert ranking.blend({**s, "feedback": 2.0}, RANK_WEIGHTS) == pytest.approx(ranking.blend(s, RANK_WEIGHTS))


def test_feedback_nudge_is_bounded():
    # raw feedback well beyond ±3 is clamped, so the nudge can never exceed ±FEEDBACK_WEIGHT
    base = {"graph": 0.0, "semantic": 0.0, "recency": 0.0, "confidence": 0.0, "focus": 0.0}
    hi = ranking.blend({**base, "feedback": 99.0}, ranking.RETRIEVAL_WEIGHTS, feedback_weight=ranking.FEEDBACK_WEIGHT)
    lo = ranking.blend({**base, "feedback": -99.0}, ranking.RETRIEVAL_WEIGHTS, feedback_weight=ranking.FEEDBACK_WEIGHT)
    assert hi == pytest.approx(ranking.FEEDBACK_WEIGHT)
    assert lo == pytest.approx(-ranking.FEEDBACK_WEIGHT)
