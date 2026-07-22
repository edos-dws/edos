"""Context Engine (roadmap Ch 5/15).

"The LLM never searches the project. The Context Engine does." Deterministic pipeline: score candidate
items with the Ch 15 formula, sort highest-first, compress to a budget, and assemble a valid
`ContextPackage`. Rule expansion adds related concerns without an LLM call.

CP-3 delivers the deterministic skeleton. Semantic retrieval + graph distance come from real embeddings /
the graph at later checkpoints; here those signals are supplied per candidate.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence

from edos.engines.ranking import rank_score
from edos.engines.rules import expand
from edos.models.context import ContextItem, ContextPackage


class ContextEngine:
    def build(
        self,
        *,
        project_id: str,
        intent: str,
        entities: Iterable[str],
        candidates: Sequence[dict],
        token_budget: int | None = None,
    ) -> ContextPackage:
        """Assemble a ranked context package.

        `candidates`: dicts of {type, ref_id, content, signals:{graph,semantic,recency,confidence,focus}}.
        """
        scored: list[ContextItem] = []
        for cand in candidates:
            signals = cand["signals"]
            score = rank_score(**signals)
            scored.append(
                ContextItem(
                    type=cand["type"],
                    ref_id=cand.get("ref_id"),
                    content=cand["content"],
                    score=round(score, 6),
                    confidence=signals.get("confidence"),
                )
            )

        scored.sort(key=lambda item: item.score, reverse=True)
        if token_budget is not None:
            scored = self._compress(scored, token_budget)

        entities = list(entities)
        expanded = [e for e in expand(entities) if e not in entities]

        return ContextPackage(
            project_id=project_id,
            intent=intent,
            entities=entities + expanded,
            items=scored,
            token_estimate=sum(len(item.content) for item in scored),
        )

    @staticmethod
    def _compress(items: list[ContextItem], token_budget: int) -> list[ContextItem]:
        """Drop lowest-ranked items once the budget is exceeded (Ch 5). Char count proxies tokens for now."""
        kept: list[ContextItem] = []
        used = 0
        for item in items:
            cost = len(item.content)
            if kept and used + cost > token_budget:
                break
            kept.append(item)
            used += cost
        return kept
