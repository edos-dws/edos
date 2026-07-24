"""Feedback / learning loop (CP-17) — outcomes make the system smarter over time.

Trace → Reason → Learn → Replay: each decision's outcome (accepted / challenged / reversed) is captured with
the confidence it carried, so we can measure **calibration** (do confident decisions actually hold up?) and
propose ranking adjustments.

Calibration is measured, not guessed. Ranking-weight tuning is **advisory only** here — auto-applying it is
gated on the retrieval eval (OD-3 threshold unset), so we never silently move retrieval quality on a hunch.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from edos.db.models import DecisionOutcome
from edos.engines import decision_store

VALID_OUTCOMES = {"accepted", "challenged", "reversed"}


def record_outcome(session: Session, *, decision_id: str, outcome: str) -> DecisionOutcome | None:
    if outcome not in VALID_OUTCOMES:
        raise ValueError(f"outcome must be one of {sorted(VALID_OUTCOMES)}")
    latest = decision_store.get_latest(session, decision_id)
    if latest is None:
        return None
    row = DecisionOutcome(decision_id=decision_id, outcome=outcome,
                          confidence_at_outcome=latest.confidence)
    session.add(row)
    session.flush()
    return row


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 6) if values else 0.0


def calibration_report(session: Session) -> dict:
    """Compare the confidence carried by decisions that held up (accepted) vs those that were reversed.

    A well-calibrated system shows accepted > reversed. `calibration_gap` = mean_accepted − mean_reversed
    (higher is better; negative means confident decisions are being reversed — miscalibration)."""
    rows = list(session.scalars(select(DecisionOutcome)))
    accepted = [r.confidence_at_outcome for r in rows if r.outcome == "accepted"]
    reversed_ = [r.confidence_at_outcome for r in rows if r.outcome == "reversed"]
    mean_accepted, mean_reversed = _mean(accepted), _mean(reversed_)
    return {
        "n": len(rows),
        "n_accepted": len(accepted),
        "n_reversed": len(reversed_),
        "mean_confidence_accepted": mean_accepted,
        "mean_confidence_reversed": mean_reversed,
        "calibration_gap": round(mean_accepted - mean_reversed, 6),
    }


def suggest_ranking_adjustment(report: dict) -> dict:
    """Advisory only (eval-gated). If confident decisions are being reversed (negative gap), suggest trusting
    the confidence signal less. Never auto-applied — surfaced for review."""
    gap = report.get("calibration_gap", 0.0)
    if report.get("n_reversed", 0) == 0:
        return {"apply": False, "note": "no reversals yet — nothing to learn from"}
    if gap < 0:
        return {"apply": False, "suggestion": "lower confidence-signal weight in rank_score",
                "reason": f"confident decisions are being reversed (gap {gap})"}
    return {"apply": False, "note": f"calibration positive (gap {gap}); no change suggested"}
