"""A3 — eval operationalization: the scorecard + regression-gate logic (pure, no DB/network)."""
import json

from scripts.eval import compare, run_all


def _sc(recall, pass_rate=None):
    d = {"retrieval": {"recall@k": recall, "precision@k": 0.8, "mrr": 1.0, "ndcg@k": 0.9}}
    if pass_rate is not None:
        d["decision"] = {"pass_rate": pass_rate}
    return d


def test_compare_passes_when_flat_or_up():
    base = _sc(0.90)
    assert compare.compare(base, _sc(0.90))["ok"] is True          # flat
    assert compare.compare(base, _sc(0.95))["ok"] is True           # up


def test_compare_fails_on_regression_beyond_margin():
    res = compare.compare(_sc(0.90), _sc(0.80), margin=0.05)         # −0.10 drop
    assert res["ok"] is False
    assert any(r["metric"] == "retrieval.recall@k" for r in res["regressions"])


def test_compare_warns_on_small_drop_but_passes():
    res = compare.compare(_sc(0.90), _sc(0.88), margin=0.05)         # −0.02 drop < margin
    assert res["ok"] is True
    assert any(r["metric"] == "retrieval.recall@k" for r in res["warnings"])


def test_compare_skips_missing_metrics_no_fabricated_delta():
    # baseline has decision.pass_rate, scorecard does not → that metric is simply not compared (not a 0-delta)
    res = compare.compare(_sc(0.9, pass_rate=0.7), _sc(0.9))
    assert res["ok"] is True
    assert all(r["metric"] != "decision.pass_rate" for r in res["deltas"])


def test_compare_regresses_on_decision_pass_rate_drop():
    res = compare.compare(_sc(0.9, pass_rate=0.8), _sc(0.9, pass_rate=0.5), margin=0.05)
    assert res["ok"] is False
    assert any(r["metric"] == "decision.pass_rate" for r in res["regressions"])


def test_compare_cli_no_baseline_skips_gate(tmp_path):
    scorecard = tmp_path / "sc.json"
    scorecard.write_text(json.dumps(_sc(0.9)))
    # no baseline file → gate is skipped (exit 0), not a failure
    rc = compare.main(["--baseline", str(tmp_path / "missing.json"), "--scorecard", str(scorecard)])
    assert rc == 0


def test_compare_cli_fails_on_regression(tmp_path):
    (tmp_path / "baseline.json").write_text(json.dumps(_sc(0.9)))
    (tmp_path / "sc.json").write_text(json.dumps(_sc(0.7)))
    rc = compare.main(["--baseline", str(tmp_path / "baseline.json"),
                       "--scorecard", str(tmp_path / "sc.json"), "--margin", "0.05"])
    assert rc == 1


def test_scorecard_is_config_stamped():
    sc = run_all.build_scorecard(retrieval={"recall@k": 0.9}, decision={"skipped": "stub"},
                                 config={"provider": "stub", "embedder": "stub"}, commit="abc123")
    assert sc["commit"] == "abc123"
    assert sc["config"]["provider"] == "stub"       # a score is meaningless without its config
    assert "retrieval" in sc and "decision" in sc
    assert "note" in sc
