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

from edos.engines.model_router import Capability, ModelRouter
from edos.models.decision import Decision

# Below this fraction of grounded evidence, the decision is not safe to present as-is.
GROUNDING_FLOOR = 0.5

# Engine-internal validation for the Layer-2 NLI judge (invariant: production LLM output is JSON-validated).
# Not a locked contract. Mirrors `grounding_prompt.v1` exactly.
_GROUNDING_SCHEMA = {
    "type": "object",
    "required": ["judgments"],
    "properties": {"judgments": {"type": "array", "items": {
        "type": "object",
        "required": ["index", "support"],
        "properties": {
            "index": {"type": "integer"},
            "support": {"type": "string", "enum": ["entails", "neutral", "contradicts"]},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        },
    }}},
}


@dataclass
class FaithfulnessResult:
    grounded: bool
    faithfulness_score: float          # fraction of evidence whose source is in context
    citation_precision: float          # fraction of cited sources that exist in context
    ungrounded_claims: list[str] = field(default_factory=list)


def check(
    decision: Decision,
    context_refs: Iterable[str],
    context_texts: dict[str, str] | None = None,
    router: ModelRouter | None = None,
) -> FaithfulnessResult:
    """Grounding gate, in two layers.

    **Layer 1 (deterministic floor, always runs):** is each evidence item's cited `source` present in the
    retrieved context at all? Catches fabricated / dangling citations. Offline-safe, unchanged.

    **Layer 2 (semantic NLI, A1 — only when `context_texts` is given):** for each claim whose source *is*
    present, does the source TEXT actually **entail** the claim? A cited-but-`neutral` or cited-but-
    `contradicts` claim is now *ungrounded* — "cited" is no longer the same as "supported". One batched
    grounding call per decision (standard tier). Offline / on malformed judge output the call raises and is
    caught → **Layer-1 traceability only** (today's exact behaviour, zero change in CI/tests).
    """
    refs = {r for r in context_refs if r}
    evidence = list(decision.evidence)
    if not evidence:
        # No evidence to trace. Verification already flags this; from a grounding lens it is unsupported.
        return FaithfulnessResult(grounded=False, faithfulness_score=0.0, citation_precision=0.0,
                                  ungrounded_claims=["recommendation has no evidence to ground it"])

    # Layer 1 — deterministic traceability (floor).
    ungrounded = [e.claim for e in evidence if e.source not in refs]

    # Layer 2 — semantic support-judge over the present-source claims (degrade to Layer 1 offline).
    unsupported: set[str] = set()
    if context_texts:
        batch = [{"index": i, "claim": e.claim, "source_text": context_texts.get(e.source, "")}
                 for i, e in enumerate(evidence) if e.source in refs and context_texts.get(e.source)]
        if batch:
            try:
                raw = (router or ModelRouter()).execute(
                    Capability.grounding, {"claims": batch}, schema=_GROUNDING_SCHEMA)
                for j in raw["judgments"]:
                    if j["support"] != "entails":
                        e = evidence[j["index"]]
                        unsupported.add(e.claim)
                        ungrounded.append(f"cited but not supported ({j['support']}): {e.claim}")
            except Exception:  # noqa: BLE001, S110 — no live/valid judge → Layer-1 traceability only
                pass

    grounded_ev = [e for e in evidence if e.source in refs and e.claim not in unsupported]
    cited = [e for e in evidence if e.source]
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
