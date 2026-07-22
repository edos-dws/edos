"""Benchmark dataset loader (roadmap Ch 12).

Loads the scenario benchmark files under `benchmarks/` into `Rubric`s the CP-8 harness can score. Each file
pairs a scenario (its intake reference + the traps a good run must catch) with a generic embedded-reasoning
rubric. At go-live, real run outputs are scored against these; the scores are what CP-9 uses to *derive* the
freeze threshold (never guessed).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from edos.eval.harness import Criterion, Rubric

_BENCH_DIR = Path(__file__).resolve().parents[3] / "benchmarks"


@dataclass
class Benchmark:
    id: str
    title: str
    domain: str
    intake: str
    traps: list[str]
    rubric: Rubric


def _to_benchmark(data: dict) -> Benchmark:
    criteria = [
        Criterion(
            key=c["key"],
            max_score=c.get("max_score", 2),
            critical=c.get("critical", False),
            hard_fail_if_zero=c.get("hard_fail_if_zero", False),
        )
        for c in data["criteria"]
    ]
    return Benchmark(
        id=data["id"],
        title=data["title"],
        domain=data.get("domain", ""),
        intake=data.get("intake", ""),
        traps=data.get("traps", []),
        rubric=Rubric(criteria=criteria, pass_total=data["pass_total"]),
    )


def load_benchmark(path: str | Path) -> Benchmark:
    return _to_benchmark(json.loads(Path(path).read_text(encoding="utf-8")))


def load_all() -> list[Benchmark]:
    return [load_benchmark(p) for p in sorted(_BENCH_DIR.glob("*.json"))]
