"""Freeze Gate (roadmap Ch 6/12) — the last line before an autonomous commit.

A decision may be frozen ONLY when every clause holds:
  confidence >= T  AND  status == "verified"  AND  freeze_blockers == []  AND  no open contradictions.

**T is the threshold that must be DERIVED from scored benchmark runs (CP-8), never guessed.** Until a human
sets it from real data, `threshold` stays `None` and **freeze is disabled** — the gate refuses every freeze.
This is the fail-safe: no autonomous freeze can happen by default.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from edos.models.decision import Decision


@dataclass
class FreezeResult:
    frozen: bool
    reasons: list[str] = field(default_factory=list)


class FreezeGate:
    def __init__(self, threshold: float | None = None) -> None:
        # None => threshold not yet derived from scored runs => freeze DISABLED (fail-safe).
        self.threshold = threshold

    def evaluate(self, decision: Decision, open_contradictions: int = 0) -> FreezeResult:
        reasons: list[str] = []
        if self.threshold is None:
            reasons.append("freeze threshold T not set (must be derived from scored runs) — freeze disabled")
        if decision.status != "verified":
            reasons.append(f"status is '{decision.status}', not 'verified'")
        if decision.freeze_blockers:
            reasons.append(f"{len(decision.freeze_blockers)} freeze_blocker(s) present")
        if open_contradictions > 0:
            reasons.append(f"{open_contradictions} open contradiction(s)")
        if self.threshold is not None and decision.confidence < self.threshold:
            reasons.append(f"confidence {decision.confidence} < threshold {self.threshold}")
        return FreezeResult(frozen=not reasons, reasons=reasons)

    def apply(self, decision: Decision, open_contradictions: int = 0) -> Decision:
        """Return a frozen decision only if the gate passes; otherwise the decision is unchanged."""
        result = self.evaluate(decision, open_contradictions)
        if result.frozen:
            return decision.model_copy(update={"status": "frozen", "freeze_blockers": []})
        return decision
