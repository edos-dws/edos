"""Step 2 — the benchmark dataset loads and scores through the CP-8 harness."""
from edos.eval.benchmarks import load_all
from edos.eval.harness import score_run

BENCH = load_all()


def test_all_benchmarks_load():
    assert len(BENCH) >= 5  # scenarios 02–06
    for b in BENCH:
        assert b.id and b.title and b.rubric.criteria
        assert b.traps, f"{b.id} has no traps listed"
        assert b.intake, f"{b.id} has no intake reference"


def test_each_benchmark_scores_a_perfect_run_as_pass():
    for b in BENCH:
        perfect = {c.key: c.max_score for c in b.rubric.criteria}
        ev = score_run(b.rubric, perfect)
        assert ev.passed, f"{b.id} perfect run should pass ({ev.reasons})"
        assert ev.total == ev.max_total


def test_missing_a_critical_trap_fails():
    for b in BENCH:
        crit = next((c for c in b.rubric.criteria if c.critical), None)
        if not crit:
            continue
        scores = {c.key: c.max_score for c in b.rubric.criteria}
        scores[crit.key] = 1  # a critical dimension not maxed
        ev = score_run(b.rubric, scores)
        assert not ev.passed, f"{b.id}: not maxing critical '{crit.key}' should fail"


def test_hallucination_zero_hard_fails_every_benchmark():
    for b in BENCH:
        hf = next((c for c in b.rubric.criteria if c.hard_fail_if_zero), None)
        assert hf, f"{b.id} has no hard-fail (hallucination) criterion"
        scores = {c.key: c.max_score for c in b.rubric.criteria}
        scores[hf.key] = 0
        ev = score_run(b.rubric, scores)
        assert not ev.passed, f"{b.id}: hallucination=0 must hard-fail"
