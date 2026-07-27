"""Feedback / learning loop (CP-17) — outcomes make the system smarter over time.

Trace → Reason → Learn → Replay: each decision's outcome (accepted / challenged / reversed) is captured with
the confidence it carried, so we can measure **calibration** (do confident decisions actually hold up?) and
propose ranking adjustments.

Calibration is measured, not guessed. Ranking-weight tuning is **advisory only** here — auto-applying it is
gated on the retrieval eval (OD-3 threshold unset), so we never silently move retrieval quality on a hunch.
"""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from edos.db.models import DecisionOutcome, LensFeedback, ProjectItem
from edos.engines import decision_store

VALID_OUTCOMES = {"accepted", "challenged", "reversed"}

# How much a decision's outcome nudges the usefulness of each item that fed it (#7 feedback loop).
_FEEDBACK_DELTA = {"accepted": 0.5, "challenged": -0.2, "reversed": -0.5}
_FEEDBACK_CLAMP = 3.0


def apply_context_feedback(session: Session, *, decision_row, outcome: str) -> int:
    """Propagate a decision's outcome to the retrieval items that fed it: accepted → boost, reversed →
    penalise. The item ids were recorded on the decision (`decision_detail.context_item_ids`) at decide time.
    Bounded so a single outcome nudges, never dominates. Returns how many items were adjusted."""
    delta = _FEEDBACK_DELTA.get(outcome, 0.0)
    if not delta or not decision_row.decision_detail:
        return 0
    try:
        item_ids = json.loads(decision_row.decision_detail).get("context_item_ids") or []
    except (ValueError, TypeError):
        return 0
    if not item_ids:
        return 0
    rows = session.scalars(select(ProjectItem).where(ProjectItem.id.in_(item_ids))).all()
    for it in rows:
        it.feedback_score = max(-_FEEDBACK_CLAMP, min(_FEEDBACK_CLAMP, (it.feedback_score or 0.0) + delta))
    session.flush()
    return len(rows)


def _spine_keys_and_deep_lenses(decision_row) -> tuple[list[str], list[str]]:
    """Read the reasoning frame stored on a decision → (spine 'axis:value' tokens, deep lens_ids). Empty on
    any missing/malformed data."""
    if not decision_row.decision_detail:
        return [], []
    try:
        frame = json.loads(decision_row.decision_detail).get("reasoning_frame") or {}
    except (ValueError, TypeError):
        return [], []
    keys: list[str] = []
    for ln in frame.get("spine") or []:
        if not isinstance(ln, str) or ":" not in ln or ln.lower().startswith("unknown"):
            continue
        axis, _, val = ln.partition(":")
        if axis.strip() and val.strip():
            keys.append(f"{axis.strip()}:{val.strip()}")
    deep = [x.get("lens_id") for x in (frame.get("lenses") or [])
            if isinstance(x, dict) and x.get("deep") and x.get("lens_id")]
    return keys, deep


def apply_lens_feedback(session: Session, *, decision_row, outcome: str) -> int:
    """Self-tuning lens weights (Feature 2): the lenses that were load-bearing (deep) in a decision get their
    learned score nudged for that project's DIRECTION — accepted → boost, reversed → penalise — keyed by each
    spine 'axis:value' token. So on the next similar-direction project those lenses rank a little higher.
    Best-effort and bounded; returns how many (key, lens) scores were adjusted."""
    delta = _FEEDBACK_DELTA.get(outcome, 0.0)
    if not delta:
        return 0
    keys, deep = _spine_keys_and_deep_lenses(decision_row)
    if not keys or not deep:
        return 0
    n = 0
    for key in keys:
        for lid in deep:
            row = session.scalars(
                select(LensFeedback).where(LensFeedback.key == key, LensFeedback.lens_id == lid)
            ).first()
            if row is None:
                row = LensFeedback(key=key, lens_id=lid, score=0.0)
                session.add(row)
            row.score = max(-_FEEDBACK_CLAMP, min(_FEEDBACK_CLAMP, (row.score or 0.0) + delta))
            n += 1
    session.flush()
    return n


def lens_learned_weights(session: Session, spine) -> dict[str, float]:
    """For a project's spine, the learned score per lens = bounded sum of `LensFeedback` over the spine's
    'axis:value' tokens. Best-effort — returns {} on any error (e.g. the table not yet created on a live DB),
    so a decision never depends on it."""
    try:
        keys = [f"{axis}:{val}" for axis, val in spine.values.items()]
        if not keys:
            return {}
        rows = session.scalars(select(LensFeedback).where(LensFeedback.key.in_(keys))).all()
        out: dict[str, float] = {}
        for r in rows:
            out[r.lens_id] = out.get(r.lens_id, 0.0) + (r.score or 0.0)
        return out
    except Exception:  # noqa: BLE001 — learned weights are an enhancement; never break a decision on them
        return {}


def record_outcome(session: Session, *, decision_id: str, outcome: str) -> DecisionOutcome | None:
    if outcome not in VALID_OUTCOMES:
        raise ValueError(f"outcome must be one of {sorted(VALID_OUTCOMES)}")
    latest = decision_store.get_latest(session, decision_id)
    if latest is None:
        return None
    row = DecisionOutcome(decision_id=decision_id, outcome=outcome,
                          confidence_at_outcome=latest.confidence)
    session.add(row)
    apply_context_feedback(session, decision_row=latest, outcome=outcome)  # #7: learn which items helped
    try:
        apply_lens_feedback(session, decision_row=latest, outcome=outcome)  # F2: learn which lenses helped
    except Exception:  # noqa: BLE001, S110 — best-effort; a missing table must not fail outcome recording
        pass
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
