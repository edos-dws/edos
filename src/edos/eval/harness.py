"""Evaluation harness (roadmap Ch 12).

Scores a benchmark run against a rubric. A run assigns 0..max per criterion; the harness computes the total,
enforces *critical* criteria (must be maxed) and *hard-fail-if-zero* criteria (e.g. hallucination), and
returns pass/fail with reasons.

The default rubric mirrors `concept-dry-run/scenarios/Scenario-02 — Evaluation Key`. Real run outputs come
from live-LLM benchmark runs at go-live; this harness scores them. It also produces the data CP-9 needs to
*derive* (not guess) the freeze threshold.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Criterion:
    key: str
    max_score: int = 2
    critical: bool = False          # must score max_score to pass
    hard_fail_if_zero: bool = False  # scoring 0 fails the whole run regardless of total


@dataclass(frozen=True)
class Rubric:
    criteria: list[Criterion]
    pass_total: int

    def max_total(self) -> int:
        return sum(c.max_score for c in self.criteria)


@dataclass
class Evaluation:
    total: int
    max_total: int
    passed: bool
    reasons: list[str] = field(default_factory=list)


def score_run(rubric: Rubric, scores: dict[str, int]) -> Evaluation:
    """Score one run. `scores` maps criterion key -> points."""
    reasons: list[str] = []
    total = 0
    for c in rubric.criteria:
        s = scores.get(c.key, 0)
        if not 0 <= s <= c.max_score:
            raise ValueError(f"{c.key}: score {s} out of range 0..{c.max_score}")
        total += s
        if c.hard_fail_if_zero and s == 0:
            reasons.append(f"hard fail: '{c.key}' scored 0")
        if c.critical and s < c.max_score:
            reasons.append(f"critical '{c.key}' not maxed ({s}/{c.max_score})")
    if total < rubric.pass_total:
        reasons.append(f"total {total} < pass bar {rubric.pass_total}")
    return Evaluation(total=total, max_total=rubric.max_total(), passed=not reasons, reasons=reasons)


# Default rubric — the 10 criteria from Scenario-02's Evaluation Key (pass ≥16/20; traps 1–3 critical;
# no-hallucination is a hard fail if zero).
EDOS_BENCHMARK_RUBRIC = Rubric(
    criteria=[
        Criterion("factual_correctness", critical=True),
        Criterion("regulatory_contradiction", critical=True),
        Criterion("energy_budget", critical=True),
        Criterion("over_engineering"),
        Criterion("unbounded_buffer"),
        Criterion("cross_variant"),
        Criterion("no_hallucination", hard_fail_if_zero=True),
        Criterion("confidence_calibration"),
        Criterion("calculation_quality"),
        Criterion("freeze_discipline"),
    ],
    pass_total=16,
)
