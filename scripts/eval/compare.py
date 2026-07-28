"""Eval regression gate (A3 §3d) — diff a fresh scorecard against the committed baseline.

Pure logic (no DB, no network): loads `evals/baseline.json` and a fresh scorecard, computes per-metric
deltas, and decides pass/fail. A **regression** (a tracked metric dropping by more than `margin`) fails the
gate (nonzero exit) so a change that quietly degrades retrieval/decision quality can't land silently; smaller
downward moves warn; anything flat or up passes. Higher-is-better for every metric here (recall/precision/
MRR/nDCG/pass-rate).

Used by the Tier-2 live-eval workflow (`.github/workflows/eval.yml`) — never on the fast PR gate.
"""
from __future__ import annotations

import json
from pathlib import Path

# The metrics we track and gate on (all higher-is-better). Absent metrics are skipped, not treated as 0.
_RETRIEVAL_METRICS = ("recall@k", "precision@k", "mrr", "ndcg@k")
_DECISION_METRICS = ("pass_rate",)


def _metric(scorecard: dict, section: str, key: str) -> float | None:
    v = (scorecard.get(section) or {}).get(key)
    return float(v) if isinstance(v, (int, float)) else None


def compare(baseline: dict, scorecard: dict, margin: float = 0.05) -> dict:
    """Return {ok, regressions, warnings, deltas}. `ok` is False iff any tracked metric dropped by > margin.

    `deltas` lists every comparable metric with (baseline, current, delta). `regressions` are the hard fails
    (delta < -margin); `warnings` are smaller drops (−margin ≤ delta < 0)."""
    deltas: list[dict] = []
    regressions: list[dict] = []
    warnings: list[dict] = []

    for section, keys in (("retrieval", _RETRIEVAL_METRICS), ("decision", _DECISION_METRICS)):
        for key in keys:
            base = _metric(baseline, section, key)
            cur = _metric(scorecard, section, key)
            if base is None or cur is None:
                continue  # metric not present in one side — nothing to compare, don't fabricate a delta
            delta = round(cur - base, 6)
            row = {"metric": f"{section}.{key}", "baseline": base, "current": cur, "delta": delta}
            deltas.append(row)
            if delta < -margin:
                regressions.append(row)
            elif delta < 0:
                warnings.append(row)

    return {"ok": not regressions, "regressions": regressions, "warnings": warnings, "deltas": deltas}


def _render(result: dict, margin: float) -> str:
    lines = [f"Eval comparison vs baseline (regression margin = {margin}):", ""]
    if not result["deltas"]:
        lines.append("  (no comparable metrics — baseline and scorecard share no tracked keys)")
    for r in result["deltas"]:
        flag = "✗ REGRESSION" if r in result["regressions"] else "⚠ down" if r in result["warnings"] else "✓"
        lines.append(f"  {flag:14} {r['metric']:22} {r['baseline']:.4f} → {r['current']:.4f} "
                     f"({r['delta']:+.4f})")
    lines += ["", "RESULT: " + ("PASS" if result["ok"] else "FAIL — regression beyond margin")]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(description="Gate a fresh eval scorecard against the committed baseline.")
    p.add_argument("--baseline", default=str(Path("evals") / "baseline.json"))
    p.add_argument("--scorecard", required=True)
    p.add_argument("--margin", type=float, default=0.05)
    args = p.parse_args(argv)

    baseline_path = Path(args.baseline)
    if not baseline_path.exists():
        print(f"No baseline at {baseline_path} — nothing to compare against (capture one first). Skipping gate.")
        return 0  # no baseline yet is not a failure; the gate becomes real once a baseline is committed
    baseline = json.loads(baseline_path.read_text())
    scorecard = json.loads(Path(args.scorecard).read_text())
    result = compare(baseline, scorecard, margin=args.margin)
    print(_render(result, args.margin))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
