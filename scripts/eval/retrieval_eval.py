"""Retrieval eval harness — recall@k / precision@k / MRR for the context engine.

Seeds a throwaway project from evals/retrieval_eval.json, runs the REAL selection pipeline
(`retrieval.select_context` = HyDE → retrieve → rank → rerank → top-K) for each labeled query, and reports
how well the expected items are retrieved. Measures the exact set the LLM would see.

Run it under different configs to compare (the active config is printed):
  # baseline (no semantics)
  EDOS_EMBEDDER=stub EDOS_RERANKER=noop EDOS_QUERY_EXPANSION=noop DATABASE_URL=... python scripts/eval/retrieval_eval.py
  # full context engine
  EDOS_EMBEDDER=gemini EDOS_RERANKER=gemini EDOS_QUERY_EXPANSION=hyde DATABASE_URL=... python scripts/eval/retrieval_eval.py
"""
import json
import os
import uuid
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from edos.config import settings
from edos.engines import ingestion, retrieval
from edos.store import projects as store

K = int(os.environ.get("EVAL_K", "5"))
DATA = Path(__file__).resolve().parents[2] / "evals" / "retrieval_eval.json"


def main() -> None:
    spec = json.loads(DATA.read_text())
    engine = create_engine(os.environ["DATABASE_URL"])
    run = "eval-" + uuid.uuid4().hex[:8]

    print(f"config: embedder={settings.embedder} reranker={settings.reranker} "
          f"query_expansion={settings.query_expansion} | k={K}")

    with Session(engine) as s:
        store.create_project(s, id=run, name="retrieval-eval", domain=None)
        for it in spec["items"]:
            ingestion.ingest_item(s, id=f"{run}-{it['id']}", project_id=run,
                                  item_type=it["type"], content=it["content"])
        s.commit()

        recalls, precisions, rrs = [], [], []
        print(f"\n{'query':52s}  recall  prec   RR")
        for q in spec["queries"]:
            expected = {f"{run}-{e}" for e in q["expected"]}
            chosen = retrieval.select_context(s, project_id=run, query=q["query"], top_k=K)
            got = [c["ref_id"] for c in chosen][:K]
            recall = len(set(got) & expected) / len(expected)
            precision = len(set(got) & expected) / max(1, len(got))
            rr = next((1.0 / (rank + 1) for rank, i in enumerate(got) if i in expected), 0.0)
            recalls.append(recall); precisions.append(precision); rrs.append(rr)
            print(f"{q['query'][:52]:52s}  {recall:5.2f}  {precision:4.2f}  {rr:4.2f}")

        n = len(spec["queries"])
        print(f"\n{'AVERAGE':52s}  {sum(recalls)/n:5.2f}  {sum(precisions)/n:4.2f}  {sum(rrs)/n:4.2f}")
        print(f"→ recall@{K}={sum(recalls)/n:.2f}  precision@{K}={sum(precisions)/n:.2f}  "
              f"MRR={sum(rrs)/n:.2f}")


if __name__ == "__main__":
    main()
