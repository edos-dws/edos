"""Retrieval evaluation (CP-13 ticket 13.12) — measure retrieval quality, don't guess it.

Given a gold set (question → the item ids that MUST be retrieved), compute recall@k / precision@k / MRR /
nDCG@k over the retriever's ranked output. These numbers gate merges once a real gold set exists.

**OD-3:** the merge-gate *threshold* (min recall@k) is intentionally left unset here — it must be derived
from real scored data, not fabricated. `RECALL_AT_K_GATE = None` disables enforcement until then (same
fail-safe stance as the freeze gate).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

RECALL_AT_K_GATE: float | None = None  # OD-3: set from data; None = not enforced yet (no fabrication)


@dataclass
class EvalCase:
    question: str
    retrieved_ids: list[str]  # ranked, best-first
    gold_ids: list[str]       # ids that must appear


def recall_at_k(retrieved: list[str], gold: list[str], k: int) -> float:
    if not gold:
        return 1.0
    top = set(retrieved[:k])
    return len(top & set(gold)) / len(gold)


def precision_at_k(retrieved: list[str], gold: list[str], k: int) -> float:
    if k <= 0:
        return 0.0
    top = retrieved[:k]
    if not top:
        return 0.0
    return len(set(top) & set(gold)) / len(top)


def mrr(retrieved: list[str], gold: list[str]) -> float:
    goldset = set(gold)
    for i, rid in enumerate(retrieved, start=1):
        if rid in goldset:
            return 1.0 / i
    return 0.0


def ndcg_at_k(retrieved: list[str], gold: list[str], k: int) -> float:
    goldset = set(gold)
    dcg = sum(1.0 / math.log2(i + 1) for i, rid in enumerate(retrieved[:k], start=1) if rid in goldset)
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(goldset), k) + 1))
    return dcg / ideal if ideal else 0.0


def evaluate(cases: list[EvalCase], k: int = 10) -> dict[str, float]:
    if not cases:
        return {"recall@k": 0.0, "precision@k": 0.0, "mrr": 0.0, "ndcg@k": 0.0, "k": k, "n": 0}
    n = len(cases)
    return {
        "recall@k": sum(recall_at_k(c.retrieved_ids, c.gold_ids, k) for c in cases) / n,
        "precision@k": sum(precision_at_k(c.retrieved_ids, c.gold_ids, k) for c in cases) / n,
        "mrr": sum(mrr(c.retrieved_ids, c.gold_ids) for c in cases) / n,
        "ndcg@k": sum(ndcg_at_k(c.retrieved_ids, c.gold_ids, k) for c in cases) / n,
        "k": k,
        "n": n,
    }


def gate_passes(metrics: dict[str, float]) -> bool:
    """Merge-gate: True unless a threshold is set and recall@k falls below it (OD-3)."""
    if RECALL_AT_K_GATE is None:
        return True
    return metrics.get("recall@k", 0.0) >= RECALL_AT_K_GATE
