"""Ticket 4.2 — the Ch 15 ranking formula."""
import pytest

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
