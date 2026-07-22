"""Verification Engine (roadmap Ch 6/18) — the safety spine.

A second, independent pass that **critiques a decision, never regenerates it**. It can only *lower*
confidence, and it gates status promotion: `recommended → verified` only when it agrees; otherwise it
records `freeze_blockers` and the decision stays `recommended`.

CP-5 uses deterministic structural checks (no live LLM). The real independent critic model plugs in at
go-live, augmenting `_find_issues` — the promotion/confidence contract here does not change.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from edos.models.decision import Decision

_PENALTY_PER_ISSUE = 0.1


@dataclass
class Verdict:
    agreement: bool
    adjusted_confidence: float
    issues: list[str] = field(default_factory=list)


class VerificationEngine:
    def verify(self, decision: Decision) -> Verdict:
        """Critique the decision. Confidence can only go down (or stay); never up."""
        issues = self._find_issues(decision)
        agreement = not issues
        penalty = min(_PENALTY_PER_ISSUE * len(issues), decision.confidence)
        adjusted = decision.confidence - penalty
        adjusted = max(0.0, min(adjusted, decision.confidence))  # clamp; never increase
        return Verdict(agreement=agreement, adjusted_confidence=round(adjusted, 6), issues=issues)

    @staticmethod
    def _find_issues(decision: Decision) -> list[str]:
        """Structural critique (deterministic placeholder for the independent critic LLM)."""
        issues: list[str] = []
        if not decision.evidence:
            issues.append("Recommendation has no supporting evidence.")
        for a in decision.assumptions:
            if a.confidence < 0.5 and not a.risk_if_wrong:
                issues.append(f"Low-confidence assumption without stated risk: {a.statement}")
        return issues

    def promote(self, decision: Decision, verdict: Verdict) -> Decision:
        """Promote `recommended → verified` only if verification agrees; else record freeze_blockers.

        Never promotes to `frozen` — that is the CP-9 freeze gate's job alone.
        """
        if verdict.agreement and decision.status == "recommended":
            return decision.model_copy(update={
                "status": "verified",
                "confidence": verdict.adjusted_confidence,
                "freeze_blockers": [],
            })
        return decision.model_copy(update={
            "status": "recommended",
            "confidence": verdict.adjusted_confidence,
            "freeze_blockers": list(decision.freeze_blockers) + verdict.issues,
        })
