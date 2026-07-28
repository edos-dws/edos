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
from edos.engines.model_router import Capability, ModelRouter
from edos.models.decision import Decision

_PENALTY_PER_ISSUE = 0.1

# Engine-internal validation schema (invariant: all production LLM output is JSON-validated). Mirrors the
# `verification_prompt.v1` declared output exactly. NOT a locked contract (not under contracts/), so adding it
# is not a contract-change ticket.
_VERDICT_SCHEMA = {
    "type": "object",
    "required": ["agreement", "adjusted_confidence", "issues"],
    "properties": {
        "agreement": {"type": "boolean"},
        "adjusted_confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "issues": {"type": "array", "items": {"type": "string"}},
    },
}


@dataclass
class Verdict:
    agreement: bool
    adjusted_confidence: float
    issues: list[str] = field(default_factory=list)
    faithfulness: float | None = None


class VerificationEngine:
    def __init__(self, router: ModelRouter | None = None) -> None:
        self.router = router or ModelRouter()

    def verify(self, decision: Decision, context_refs: Iterable[str] | None = None) -> Verdict:
        """Critique the decision. Confidence can only go down (or stay); never up. When `context_refs` are
        given, a faithfulness pass (CP-14) adds ungrounded claims as issues (Self-RAG hardening, CP-16).

        Beyond the deterministic structural floor, an **independent LLM critic** (`verification_prompt.v1`,
        frontier tier) reasons over the decision + its evidence and may add issues and/or lower confidence.
        The critic **augments** — it never regenerates, and confidence monotonicity is enforced in CODE below
        (the clamp), never trusted to the model. Offline / on any malformed critic output the engine degrades
        to the deterministic floor with zero behaviour change."""
        issues = self._find_issues(decision)  # deterministic floor (unchanged)

        faithfulness_score: float | None = None
        if context_refs is not None:
            fr = faithfulness.check(decision, context_refs)
            faithfulness_score = fr.faithfulness_score
            issues += [f"ungrounded claim (not traceable to context): {c}" for c in fr.ungrounded_claims]

        # independent LLM critic — augments the floor; degrades to floor offline / on malformed output.
        llm_conf: float | None = None
        try:
            raw = self.router.execute(
                Capability.verification,
                {"decision": decision.to_contract_dict()},  # critic reasons over the decision + its evidence
                schema=_VERDICT_SCHEMA,
            )
            if not raw.get("agreement", True):
                issues += [str(i) for i in (raw.get("issues") or [])]
            if raw.get("adjusted_confidence") is not None:
                llm_conf = float(raw["adjusted_confidence"])
        except Exception:  # noqa: BLE001, S110 — critic (incl. MalformedOutputError) must never break the path
            pass  # no live/valid critic → deterministic floor only

        # confidence: monotonic-DOWN, enforced in code. base ≤ decision.confidence (min), and the final clamp
        # keeps adjusted ≤ decision.confidence — the critic can only lower or hold, never raise, regardless of
        # what the model returns.
        base = decision.confidence if llm_conf is None else min(decision.confidence, llm_conf)
        agreement = not issues
        penalty = min(_PENALTY_PER_ISSUE * len(issues), base)
        adjusted = max(0.0, min(base - penalty, decision.confidence))
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
