"""Faithfulness / grounding gate (CP-14, P0) — the trust spine.

Before a decision is returned, every material claim must be **traceable to the retrieved context**. A claim
whose cited source is not in the context is ungrounded — a hallucination risk. The gate then acts (Self-RAG):
lower confidence and, if grounding is too thin, downgrade the decision to `needs_review` instead of returning
a confident answer built on air.

CP-14 does deterministic **evidence-source traceability** (source id must appear in the retrieved context).
The semantic per-claim NLI/LLM-judge (does the context actually *support* the claim, not just cite it) is
LLM-gated and deferred (OD-5) — same stub pattern as the other engines.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from edos.models.decision import Decision

# Below this fraction of grounded evidence, the decision is not safe to present as-is.
GROUNDING_FLOOR = 0.5


@dataclass
class FaithfulnessResult:
    grounded: bool
    faithfulness_score: float          # fraction of evidence whose source is in context
    citation_precision: float          # fraction of cited sources that exist in context
    ungrounded_claims: list[str] = field(default_factory=list)


def check(decision: Decision, context_refs: Iterable[str]) -> FaithfulnessResult:
    """Trace each evidence item's source to the retrieved context."""
    refs = {r for r in context_refs if r}
    evidence = list(decision.evidence)
    if not evidence:
        # No evidence to trace. Verification already flags this; from a grounding lens it is unsupported.
        return FaithfulnessResult(grounded=False, faithfulness_score=0.0, citation_precision=0.0,
                                  ungrounded_claims=["recommendation has no evidence to ground it"])

    grounded_ev = [e for e in evidence if e.source in refs]
    cited = [e for e in evidence if e.source]
    ungrounded = [e.claim for e in evidence if e.source not in refs]

    faithfulness_score = len(grounded_ev) / len(evidence)
    citation_precision = (len([e for e in cited if e.source in refs]) / len(cited)) if cited else 0.0
    return FaithfulnessResult(
        grounded=(faithfulness_score >= GROUNDING_FLOOR),
        faithfulness_score=round(faithfulness_score, 6),
        citation_precision=round(citation_precision, 6),
        ungrounded_claims=ungrounded,
    )


def apply_gate(decision: Decision, result: FaithfulnessResult) -> Decision:
    """Self-RAG gate action, using only valid contract fields: never *raise* confidence — scale it by
    faithfulness; record ungrounded claims as `freeze_blockers` (this must not be committed). The
    'needs_review' signal is surfaced at the API response envelope, not by inventing a decision status
    (the locked contract allows only proposed/recommended/verified/frozen)."""
    new_conf = round(min(decision.confidence, decision.confidence * result.faithfulness_score), 6)
    updates: dict = {"confidence": new_conf}
    if not result.grounded:
        blockers = list(decision.freeze_blockers)
        blockers += [f"ungrounded claim (not traceable to context): {c}" for c in result.ungrounded_claims]
        updates["freeze_blockers"] = blockers
    return decision.model_copy(update=updates)
