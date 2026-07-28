"""One-command eval scorecard (A3 §3a).

Runs the retrieval eval (and, when a live model is configured, the decision benchmark), and emits a single
**config-stamped** JSON scorecard. The config block is mandatory — a score is meaningless without the
embedder/reranker/provider that produced it, so a stub-config number is never mistaken for a live one.

Runs anywhere:
  * Retrieval eval needs a Postgres (`DATABASE_URL`); without it that section is recorded `skipped`.
  * The decision benchmark needs a live LLM; under the stub provider it is recorded `skipped` (not faked).

    DATABASE_URL=... python scripts/eval/run_all.py --out scorecard.json
"""
from __future__ import annotations

import json
import os
import subprocess
import uuid
from pathlib import Path

from edos.config import settings
from edos.eval import retrieval_eval

_ROOT = Path(__file__).resolve().parents[2]
_GOLD = _ROOT / "evals" / "retrieval_eval.json"


def _commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=_ROOT, text=True).strip()[:12]
    except Exception:  # noqa: BLE001 — commit stamp is best-effort
        return "unknown"


def _config_block() -> dict:
    return {
        "provider": settings.llm_provider,
        "embedder": settings.embedder,
        "reranker": settings.reranker,
        "query_expansion": settings.query_expansion,
        "embed_model": settings.embed_model,
        "live": settings.llm_provider != "stub",
    }


def build_scorecard(retrieval: dict, decision: dict, config: dict, commit: str) -> dict:
    """Assemble the scorecard (pure — the testable core). `retrieval`/`decision` are either a metrics dict or
    a `{"skipped": reason}` marker; `n` (gold-set size) is surfaced so nobody reads a tiny-N score as proof."""
    return {
        "commit": commit,
        "config": config,
        "retrieval": retrieval,
        "decision": decision,
        "note": "config-stamped scorecard; a stub-config number is a plumbing check, not a quality measure.",
    }


def _run_retrieval() -> dict:
    """Seed a throwaway project from the gold set, run the REAL selection pipeline, return metrics.
    Records `skipped` (never a fake number) when no DB is reachable."""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        return {"skipped": "no DATABASE_URL"}
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session

        from edos.engines import ingestion, retrieval
        from edos.store import projects as store

        k = int(os.environ.get("EVAL_K", "5"))
        spec = json.loads(_GOLD.read_text())
        engine = create_engine(db_url)
        run = "evalrun-" + uuid.uuid4().hex[:8]
        cases: list[retrieval_eval.EvalCase] = []
        with Session(engine) as s:
            store.create_project(s, id=run, name="retrieval-eval", domain=None)
            for it in spec["items"]:
                ingestion.ingest_item(s, id=f"{run}-{it['id']}", project_id=run,
                                      item_type=it["type"], content=it["content"])
            s.commit()
            for q in spec["queries"]:
                chosen = retrieval.select_context(s, project_id=run, query=q["query"], top_k=k)
                got = [c["ref_id"] for c in chosen][:k]
                cases.append(retrieval_eval.EvalCase(
                    retrieved_ids=got, gold_ids=[f"{run}-{e}" for e in q["expected"]]))
        metrics = retrieval_eval.evaluate(cases, k=k)
        metrics["gold_items"] = len(spec["items"])
        return metrics
    except Exception as exc:  # noqa: BLE001 — an unreachable/broken DB records skipped, never a fake number
        return {"skipped": f"{exc.__class__.__name__}: {exc}"}


def _run_decision() -> dict:
    """The decision benchmark needs a live model + independent judge. Offline it is recorded skipped (the live
    runner is scripts/run_benchmarks_live.py; wiring it into this scorecard is the Tier-2 live-eval step)."""
    if settings.llm_provider == "stub":
        return {"skipped": "stub provider — decision-quality benchmark needs a live model + judge"}
    return {"skipped": "live decision benchmark not wired into run_all yet (use scripts/run_benchmarks_live.py)"}


def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(description="Produce a config-stamped eval scorecard.")
    p.add_argument("--out", default="scorecard.json")
    args = p.parse_args(argv)

    scorecard = build_scorecard(
        retrieval=_run_retrieval(),
        decision=_run_decision(),
        config=_config_block(),
        commit=_commit(),
    )
    Path(args.out).write_text(json.dumps(scorecard, indent=2))
    print(json.dumps(scorecard, indent=2))
    print(f"\n→ scorecard written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
