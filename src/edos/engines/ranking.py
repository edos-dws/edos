"""Context ranking (roadmap Ch 15) — ONE weighted blend, two DECLARED weight sets.

Two entry points rank candidate context, and they weight the signals DIFFERENTLY on purpose (a declared
choice, not a silent fork — this module is the one place that fork is written down):

  * the DECISION path (Context Engine.build → `/v1/analyze`) is **graph-led** — a decision should lean on
    the vetted decision graph. Weights = `RANK_WEIGHTS`; no feedback term (the locked Ch-15 formula).
  * the SELECTION/eval path (`retrieval.select_context` → deep-dive + the eval harness) is **semantic-led**
    — a deep-dive should cast a wider semantic net. Weights = `RETRIEVAL_WEIGHTS`, plus a bounded ±feedback
    nudge (learned usefulness, #7).

Both call the SINGLE `blend()` below, so there is one implementation, one feedback treatment, and one place
to change — the only per-path difference is the weight dict (and whether feedback is on). This kills the
drift-generator (two hand-maintained formulas that silently diverged on every edit).

TODO(A3-eval): WHICH weighting is actually better — graph-led vs semantic-led, and the ±0.10 feedback
magnitude — is an EMPIRICAL question, not a matter of taste. Both weight sets and `FEEDBACK_WEIGHT` are
currently untuned. Derive them from the A3 eval once it measures *decision-path* quality (not just retrieval
recall@k); until then they stay a declared choice, not a measured one. Do NOT unify graph-led→semantic-led
by hand — that silently changes the live decision path with no measurement.

Deterministic software — never an LLM.
"""
from __future__ import annotations

# DECISION path (graph-led). Base sums to 1.0. Locked Ch-15 formula; NO feedback term.
RANK_WEIGHTS: dict[str, float] = {
    "graph": 0.40,
    "semantic": 0.30,
    "recency": 0.15,
    "confidence": 0.10,
    "focus": 0.05,
}

# SELECTION/eval path (semantic-led). Base sums to 1.0; feedback is a separate bounded nudge (see below).
RETRIEVAL_WEIGHTS: dict[str, float] = {
    "semantic": 0.45,
    "graph": 0.25,
    "recency": 0.15,
    "focus": 0.10,
    "confidence": 0.05,
}

# Magnitude of the learned-usefulness (#7 feedback) nudge on the selection path. Bounded so it tunes, never
# dominates the base blend. Untuned — see TODO(A3-eval) above.
FEEDBACK_WEIGHT: float = 0.10


def blend(signals: dict, weights: dict, feedback_weight: float = 0.0) -> float:
    """The one ranking blend: weighted sum of signals + an optional bounded feedback nudge.

    `weights` maps signal-name → weight; each `signals[name]` is in [0, 1]. Signal keys NOT in `weights`
    are ignored, so a path may carry extra signals a given weight set doesn't rank (e.g. the decision path's
    weights ignore `feedback`). When `feedback_weight != 0`, the item's raw learned usefulness
    `signals['feedback']` (roughly [-3, 3]) is squashed to [-1, 1] and added as `feedback_weight * fb` — a
    bounded nudge ON TOP of the base blend, never mixed into it."""
    score = sum(w * signals.get(name, 0.0) for name, w in weights.items())
    if feedback_weight:
        fb = max(-1.0, min(1.0, signals.get("feedback", 0.0) / 3.0))
        score += feedback_weight * fb
    return score


def rank_score(*, graph: float, semantic: float, recency: float, confidence: float, focus: float) -> float:
    """DECISION-path score (graph-led, Ch-15 locked, no feedback). Thin wrapper over `blend` with
    `RANK_WEIGHTS`. All inputs in [0, 1]; returns the weighted score in [0, 1]. Validates the range because
    the decision path's signals are normalised and an out-of-range value there is a bug, not a nudge."""
    signals = {"graph": graph, "semantic": semantic, "recency": recency,
               "confidence": confidence, "focus": focus}
    for name, value in signals.items():
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be in [0, 1], got {value}")
    return blend(signals, RANK_WEIGHTS)
