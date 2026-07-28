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


# A3 Tier-1 plumbing guard: run the REAL selection pipeline over the gold set (stub config in tests) and
# assert it isn't broken. This is a deterministic *plumbing* check (does retrieval end-to-end still find
# relevant items?), NOT a quality gate — quality is measured live in Tier-2 (eval.yml). Skips without a DB.
def test_retrieval_pipeline_plumbing_floor(session):
    import json
    from pathlib import Path

    from edos.engines import ingestion, retrieval
    spec = json.loads((Path(__file__).resolve().parents[1] / "evals" / "retrieval_eval.json").read_text())
    pid = "plumbing-eval"
    for it in spec["items"]:
        ingestion.ingest_item(session, id=f"{pid}-{it['id']}", project_id=pid,
                              item_type=it["type"], content=it["content"])
    session.flush()
    cases = []
    for q in spec["queries"]:
        chosen = retrieval.select_context(session, project_id=pid, query=q["query"], top_k=5)
        got = [c["ref_id"] for c in chosen][:5]
        cases.append(ev.EvalCase(question=q["query"], retrieved_ids=got,
                                 gold_ids=[f"{pid}-{e}" for e in q["expected"]]))
    m = ev.evaluate(cases, k=5)
    assert m["n"] == len(spec["queries"])        # every gold query ran end to end
    assert m["recall@k"] > 0.0                    # the pipeline still surfaces relevant items (not broken)
