"""Verification Engine (roadmap Ch 6/18) — the safety spine.

A second, independent pass that **critiques a decision, never regenerates it**. It can only *lower*
confidence, and it gates status promotion: `recommended → verified` only when it agrees; otherwise it
records `freeze_blockers` and the decision stays `recommended`.

CP-5 uses deterministic structural checks (no live LLM). The real independent critic model plugs in at
go-live, augmenting `_find_issues` — the promotion/confidence contract here does not change.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from edos.engines import faithfulness
from edos.models.decision import Decision

_PENALTY_PER_ISSUE = 0.1


@dataclass
class Verdict:
    agreement: bool
    adjusted_confidence: float
    issues: list[str] = field(default_factory=list)
    faithfulness: float | None = None


class VerificationEngine:
    def verify(self, decision: Decision, context_refs: Iterable[str] | None = None) -> Verdict:
        """Critique the decision. Confidence can only go down (or stay); never up. When `context_refs` are
        given, a faithfulness pass (CP-14) adds ungrounded claims as issues (Self-RAG hardening, CP-16)."""
        issues = self._find_issues(decision)
        faithfulness_score: float | None = None
        if context_refs is not None:
            fr = faithfulness.check(decision, context_refs)
            faithfulness_score = fr.faithfulness_score
            issues += [f"ungrounded claim (not traceable to context): {c}" for c in fr.ungrounded_claims]
        agreement = not issues
        penalty = min(_PENALTY_PER_ISSUE * len(issues), decision.confidence)
        adjusted = decision.confidence - penalty
        adjusted = max(0.0, min(adjusted, decision.confidence))  # clamp; never increase
        return Verdict(agreement=agreement, adjusted_confidence=round(adjusted, 6), issues=issues,
                       faithfulness=faithfulness_score)

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

        Verification critiques the *reasoning*; it never resolves the author's declared
        `freeze_blockers` (the preconditions that must be met before freeze). Those are always carried
        forward — a `verified` decision can still hold freeze_blockers, and the CP-9 freeze gate is the
        only stage allowed to clear/enforce them. Verification only *adds* its own disagreement issues as
        blockers; it never wipes existing ones. Never promotes to `frozen`.
        """
        if verdict.agreement and decision.status == "recommended":
            return decision.model_copy(update={
                "status": "verified",
                "confidence": verdict.adjusted_confidence,
                "freeze_blockers": list(decision.freeze_blockers),  # carry forward; never wipe
            })
        return decision.model_copy(update={
            "status": "recommended",
            "confidence": verdict.adjusted_confidence,
            "freeze_blockers": list(decision.freeze_blockers) + verdict.issues,
        })
