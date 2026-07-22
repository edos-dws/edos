"""Ticket 9.1 — evaluation harness scores a fixture run against the rubric."""
import pytest

from edos.eval.harness import EDOS_BENCHMARK_RUBRIC, Criterion, Rubric, score_run

ALL_KEYS = [c.key for c in EDOS_BENCHMARK_RUBRIC.criteria]


def _perfect():
    return {k: 2 for k in ALL_KEYS}


def test_perfect_run_passes_with_expected_total():
    ev = score_run(EDOS_BENCHMARK_RUBRIC, _perfect())
    assert ev.total == 20
    assert ev.max_total == 20
    assert ev.passed is True
    assert ev.reasons == []


def test_critical_criterion_not_maxed_fails_even_if_total_high():
    scores = _perfect()
    scores["regulatory_contradiction"] = 1  # total 19 but a critical trap not maxed
    ev = score_run(EDOS_BENCHMARK_RUBRIC, scores)
    assert ev.total == 19
    assert ev.passed is False
    assert any("regulatory_contradiction" in r for r in ev.reasons)


def test_hallucination_zero_is_a_hard_fail():
    scores = _perfect()
    scores["no_hallucination"] = 0
    ev = score_run(EDOS_BENCHMARK_RUBRIC, scores)
    assert ev.passed is False
    assert any("no_hallucination" in r for r in ev.reasons)


def test_below_pass_bar_fails():
    scores = {k: 1 for k in ALL_KEYS}  # total 10 < 16
    ev = score_run(EDOS_BENCHMARK_RUBRIC, scores)
    assert ev.total == 10
    assert ev.passed is False


def test_out_of_range_score_raises():
    small = Rubric(criteria=[Criterion("x")], pass_total=1)
    with pytest.raises(ValueError):
        score_run(small, {"x": 5})
