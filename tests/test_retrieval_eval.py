"""CP-13 ticket 13.12 — retrieval eval metrics (recall@k / precision@k / MRR / nDCG)."""
from edos.eval import retrieval_eval as ev


def test_recall_and_precision():
    retrieved = ["A", "B", "C", "D"]
    gold = ["A", "C", "Z"]
    assert ev.recall_at_k(retrieved, gold, k=4) == 2 / 3     # A, C found of {A,C,Z}
    assert ev.precision_at_k(retrieved, gold, k=2) == 1 / 2  # A hit, B miss


def test_mrr_and_ndcg():
    assert ev.mrr(["X", "A"], ["A"]) == 0.5                  # first relevant at rank 2
    assert ev.ndcg_at_k(["A", "X"], ["A"], k=2) == 1.0       # relevant at top = ideal


def test_evaluate_aggregates():
    cases = [
        ev.EvalCase(question="q1", retrieved_ids=["A", "B"], gold_ids=["A"]),
        ev.EvalCase(question="q2", retrieved_ids=["C", "D"], gold_ids=["D"]),
    ]
    m = ev.evaluate(cases, k=2)
    assert m["recall@k"] == 1.0
    assert m["n"] == 2


def test_gate_disabled_by_default_no_fabrication():
    # OD-3: threshold unset → gate passes (fail-safe), never blocks on a fabricated number
    assert ev.RECALL_AT_K_GATE is None
    assert ev.gate_passes({"recall@k": 0.0}) is True
