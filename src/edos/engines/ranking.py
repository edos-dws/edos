"""Context ranking formula (roadmap Ch 15).

Final Score = 0.40*graph + 0.30*semantic + 0.15*recency + 0.10*confidence + 0.05*user_focus.
Deterministic software — never an LLM.
"""
from __future__ import annotations

RANK_WEIGHTS: dict[str, float] = {
    "graph": 0.40,
    "semantic": 0.30,
    "recency": 0.15,
    "confidence": 0.10,
    "focus": 0.05,
}


def rank_score(*, graph: float, semantic: float, recency: float, confidence: float, focus: float) -> float:
    """All inputs in [0, 1]; returns the weighted score in [0, 1]."""
    signals = {"graph": graph, "semantic": semantic, "recency": recency,
               "confidence": confidence, "focus": focus}
    for name, value in signals.items():
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be in [0, 1], got {value}")
    return sum(RANK_WEIGHTS[name] * value for name, value in signals.items())
