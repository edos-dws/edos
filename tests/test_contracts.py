"""Baseline contract tests — STDLIB ONLY (no pytest, no pip installs required).

This is the green signal a continuous build agent must never break. Run either with:
    python3 -m pytest tests/          (once pytest is installed)
    python3 tests/test_contracts.py   (works today, zero dependencies)

As real engines land, ADD tests here that build objects and validate them against these schemas.
Do NOT weaken these checks to make a red build pass — fix the code instead.
"""
import json
import sys
from pathlib import Path

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"


def _load(name):
    with open(CONTRACTS / name, encoding="utf-8") as fh:
        return json.load(fh)


def test_contract_files_are_valid_json_with_ids():
    for name, expected_id in [
        ("decision.schema.json", "edos.decision.v1"),
        ("context_package.schema.json", "edos.context_package.v1"),
    ]:
        schema = _load(name)
        assert schema.get("$id") == expected_id, f"{name}: unexpected $id"
        assert schema.get("type") == "object", f"{name}: root must be object"
        assert schema.get("required"), f"{name}: must declare required fields"


def test_decision_schema_locks_the_reconciled_shape():
    schema = _load("decision.schema.json")
    props = schema["properties"]
    # Fields that MUST exist (the reconciliation of Ch 6 + Ch 16).
    for field in ["summary", "recommendation", "confidence", "status", "evidence", "freeze_blockers"]:
        assert field in props, f"decision schema missing locked field: {field}"
    assert props["confidence"]["minimum"] == 0 and props["confidence"]["maximum"] == 1
    assert set(props["status"]["enum"]) == {"proposed", "recommended", "verified", "frozen"}


def test_freeze_is_gated_not_default():
    # freeze_blockers must be part of the contract so the freeze gate has something to check.
    schema = _load("decision.schema.json")
    assert "freeze_blockers" in schema["properties"], "no freeze_blockers => no safe autonomous freeze"


def _run_all():
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
    print(f"\n{'OK' if failures == 0 else 'FAILURES: ' + str(failures)}")
    return failures


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
