"""Live benchmark runner (roadmap Ch 12) — go-live evidence.

For each benchmark scenario: feed the intake brief to the live LLM through the real decision path, get a
contract-valid decision, have an independent LLM-judge score it against the scenario's rubric (0-2 per
criterion, informed by the traps a good run must catch), then run the deterministic CP-8 harness
(`score_run`) for pass/fail. Everything is written to a timestamped folder under `benchmark-runs/`.

The judge scores are what CP-9 will use to *derive* the freeze threshold T — this run produces that data.

Free-tier note: calls are paced and 429s are retried once (per the API's suggested delay) then recorded as
quota-blocked, so a run that outgrows the free quota still saves what it got instead of crashing.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import sys
import time
from pathlib import Path

from edos.config import settings
from edos.engines.model_router import Capability, ModelRouter
from edos.engines.providers._common import extract_json
from edos.eval.benchmarks import load_all
from edos.models.decision import decision_contract, validate_against_contract

REPO = Path(__file__).resolve().parents[1]
HOME = Path.home()
PACE_SECONDS = 8  # gap between live calls to respect free-tier per-minute limits


def _intake_text(intake_ref: str) -> str:
    """Load the intake brief (never the Evaluation Key). Falls back to '' if the file isn't present."""
    if not intake_ref:
        return ""
    p = HOME / intake_ref if not intake_ref.startswith("/") else Path(intake_ref)
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _is_quota_error(exc: Exception) -> bool:
    s = str(exc)
    return "429" in s or "RESOURCE_EXHAUSTED" in s or "quota" in s.lower()


def _is_transient(exc: Exception) -> bool:
    s = str(exc).lower()
    return any(t in s for t in ("network is unreachable", "connecterror", "timeout", "temporarily", "503", "unavailable"))


def _call(fn, retries: int = 3):
    """Run a live call with backoff: quota → ~35s, transient network → ~6s. Re-raise after `retries`."""
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            if attempt >= retries:
                raise
            if _is_quota_error(exc):
                print("    …429 quota hit; waiting 35s")
                time.sleep(35)
            elif _is_transient(exc):
                print(f"    …transient network error; retry {attempt+1}/{retries} in 6s")
                time.sleep(6)
            else:
                raise


def _decide(router: ModelRouter, intake: str, bench) -> dict:
    """Live decision over the intake brief (traps are NOT shown to the model)."""
    context = {
        "scenario": bench.title,
        "domain": bench.domain,
        "intake_brief": intake or f"(brief unavailable — reason over the {bench.domain} concept: {bench.title})",
        "request": "Review this concept as an engineering decision. Surface contradictions, do the math, "
        "flag only genuine blockers, and state what must be resolved before proceeding.",
    }
    out = _call(lambda: router.execute(Capability.decision, context=context, schema=decision_contract()))
    validate_against_contract(out)
    if out.get("status") in ("verified", "frozen"):
        out["status"] = "recommended"  # Decision Engine never self-promotes
    return out


def _judge(intake: str, bench, decision: dict) -> dict:
    """Independent LLM-judge: score each rubric criterion 0-2 and note which traps were caught."""
    from google import genai

    keys = [c.key for c in bench.rubric.criteria]
    prompt = f"""You are a strict, neutral evaluator of an engineering-reasoning system's output.

SCENARIO: {bench.title} ({bench.domain})

TRAPS a competent review MUST catch (this is your scoring key — the system did NOT see this list):
{json.dumps(bench.traps, indent=2)}

THE SYSTEM'S DECISION (JSON it produced from the intake brief):
{json.dumps(decision, indent=2)}

Score each criterion 0, 1, or 2 (2 = fully met, 1 = partial, 0 = absent/wrong). Be strict: award 2 only on
clear evidence in the decision. A manufactured/inflated blocker on a sound point LOWERS calibration/discipline
scores; a fabricated value is a no_hallucination = 0.

Return STRICT JSON only, exactly these keys under "scores": {keys}
{{"scores": {{ {", ".join(f'"{k}": 0' for k in keys)} }},
  "traps_caught": ["..."], "rationale": "one or two sentences"}}"""
    client = genai.Client(api_key=settings.gemini_api_key)
    resp = _call(
        lambda: client.models.generate_content(
            model=settings.gemini_frontier_model, contents=prompt, config={"max_output_tokens": 4000}
        )
    )
    parsed = extract_json(getattr(resp, "text", "") or "")
    raw = parsed.get("scores", {}) if isinstance(parsed, dict) else {}
    # clamp to valid range so score_run never rejects a judge slip
    scores = {k: max(0, min(2, int(raw.get(k, 0) or 0))) for k in keys}
    return {"scores": scores, "traps_caught": parsed.get("traps_caught", []), "rationale": parsed.get("rationale", "")}


def main() -> int:
    # Optional args = scenario-number filters (e.g. `03 04 06`); no args = all.
    wanted = {a.lstrip("scenario-").zfill(2) for a in sys.argv[1:]}
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = REPO / "benchmark-runs" / f"run-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    router = ModelRouter()
    provider = type(router.provider).__name__
    model = settings.gemini_frontier_model
    print(f"Runner: provider={provider} model={model}\nResults -> {out_dir}\n")
    if provider == "StubProvider":
        print("Refusing to run: router is on StubProvider (no live key). Set GEMINI_API_KEY in .env.")
        return 1

    benches = load_all()
    if wanted:
        benches = [b for b in benches if b.id.split("-")[-1].zfill(2) in wanted]

    rows = []
    for i, bench in enumerate(benches):
        print(f"[{i+1}/{len(benches)}] {bench.id} — {bench.title}")
        rec: dict = {"id": bench.id, "title": bench.title, "domain": bench.domain, "provider": provider, "model": model}
        try:
            intake = _intake_text(bench.intake)
            rec["intake_found"] = bool(intake)
            time.sleep(PACE_SECONDS)
            decision = _decide(router, intake, bench)
            rec["decision"] = decision
            print(f"    decision: conf={decision.get('confidence')} status={decision.get('status')} "
                  f"risks={len(decision.get('risks', []))} freeze_blockers={len(decision.get('freeze_blockers', []))}")
            time.sleep(PACE_SECONDS)
            judged = _judge(intake, bench, decision)
            ev = __import__("edos.eval.harness", fromlist=["score_run"]).score_run(bench.rubric, judged["scores"])
            rec["judge"] = judged
            rec["evaluation"] = {"total": ev.total, "max_total": ev.max_total, "passed": ev.passed, "reasons": ev.reasons}
            print(f"    score: {ev.total}/{ev.max_total}  passed={ev.passed}  {ev.reasons or ''}")
            rows.append((bench.id, bench.title, ev.total, ev.max_total, ev.passed, "; ".join(ev.reasons)))
        except Exception as exc:  # noqa: BLE001 — record and continue; don't lose earlier results
            rec["error"] = f"{type(exc).__name__}: {str(exc)[:400]}"
            quota = _is_quota_error(exc)
            print(f"    ERROR ({'quota-blocked' if quota else 'failed'}): {rec['error'][:160]}")
            rows.append((bench.id, bench.title, "", "", "ERROR", rec["error"][:120]))
            (out_dir / f"{bench.id}.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")
            if quota:
                print("    Stopping early — free-tier quota exhausted. Saved everything up to here.")
                break
            continue
        (out_dir / f"{bench.id}.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")

    # summary artifacts
    with open(out_dir / "scores.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "title", "total", "max", "passed", "notes"])
        w.writerows(rows)

    scored = [r for r in rows if isinstance(r[2], int)]
    lines = [
        f"# EDOS Live Benchmark Run — {stamp}",
        "",
        f"- Provider: **{provider}** · Model: **{model}** (Google AI Studio free tier)",
        f"- Scenarios attempted: {len(rows)} · scored: {len(scored)}",
        "- Judge: independent LLM pass over the scenario traps; harness = `edos.eval.harness.score_run`.",
        "",
        "| Scenario | Score | Pass | Notes |",
        "|----------|:-----:|:----:|-------|",
    ]
    for r in rows:
        score = f"{r[2]}/{r[3]}" if isinstance(r[2], int) else "—"
        lines.append(f"| {r[1]} | {score} | {r[4]} | {r[5][:80]} |")
    if scored:
        avg = sum(r[2] for r in scored) / len(scored)
        lines += ["", f"**Mean score:** {avg:.1f} / {scored[0][3]}  ·  "
                  f"**Passed:** {sum(1 for r in scored if r[4] is True)}/{len(scored)}"]
    lines += [
        "",
        "> Caveat: EDOS emits ONE contract-valid decision per scenario (not a 31-turn prose session), so a",
        "> single decision may not surface all traps. These scores are directional go-live evidence; the",
        "> freeze threshold T should be set from a stable, larger set of scored runs (ideally on a paid key",
        "> with a Pro frontier model). Freeze stays DISABLED until then.",
    ]
    (out_dir / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {out_dir}/SUMMARY.md + scores.csv + per-scenario JSON")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
