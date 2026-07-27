"""Wave 3 · Step 8 — deterministic checks: verify the model's own arithmetic, never fabricate."""
import math

import pytest

from edos.engines import checks


# ---- safe arithmetic (the verifier's core; must never execute code) ----
def test_safe_arith_evaluates_pure_expressions_and_strips_units():
    assert checks.safe_arith("(3.3 - 1.8) * 0.5 A") == pytest.approx(0.75)   # LDO dissipation
    assert checks.safe_arith("25 + 0.5 * 40 C/W") == pytest.approx(45.0)      # thermal rise
    assert checks.safe_arith("220 mAh / 0.11 mA") == pytest.approx(2000.0)    # battery life


def test_safe_arith_refuses_non_arithmetic():
    assert checks.safe_arith("__import__('os').system('x')") is None
    assert checks.safe_arith("power + 3") is None    # a name, not a number
    assert checks.safe_arith("open('f')") is None
    assert checks.safe_arith("") is None


# ---- verify_computations: catch the model's arithmetic mistakes ----
def test_verifies_correct_and_flags_wrong_math():
    comps = [
        {"quantity": "LDO dissipation", "expression": "(5 - 3.3) * 0.5", "result": 0.85},   # correct
        {"quantity": "junction temp", "expression": "25 + 2 * 40", "result": 150},           # WRONG (=105)
    ]
    out = checks.verify_computations(comps)
    assert out[0]["verified"] is True
    assert out[1]["verified"] is False
    assert out[1]["computed"] == pytest.approx(105.0)   # the real answer is surfaced


def test_unqualified_expression_is_unchecked_not_falsely_verified():
    out = checks.verify_computations([{"quantity": "x", "expression": "depends on the datasheet", "result": 5}])
    assert out[0]["verified"] is None    # unchecked — never a false ✓


def test_verify_computations_is_robust_to_garbage():
    assert checks.verify_computations(None) == []
    assert checks.verify_computations("not a list") == []
    assert checks.verify_computations([{"no": "expression"}, 42]) == []


# ---- canonical formulas: correct, and never fabricate a missing input ----
def test_ldo_and_thermal_and_battery_and_budget():
    assert checks.ldo_dissipation(5.0, 3.3, 0.5)["value"] == pytest.approx(0.85)
    tj = checks.thermal_junction(2.0, 40.0, 25.0, tj_max_c=125.0)
    assert tj["value"] == pytest.approx(105.0) and tj["within_limit"] is True and tj["headroom_C"] == pytest.approx(20.0)
    bl = checks.battery_life(220.0, 0.11)
    assert bl["value"] == pytest.approx(2000.0) and bl["days"] == pytest.approx(83.33, abs=0.1)
    pb = checks.power_budget([{"name": "3v3", "voltage_v": 3.3, "current_a": 0.1},
                              {"name": "1v8", "voltage_v": 1.8, "current_a": 0.2}])
    assert pb["value"] == pytest.approx(0.33 + 0.36)


def test_formulas_do_not_fabricate_missing_inputs():
    with pytest.raises(ValueError):
        checks.battery_life(220.0, 0.0)          # divide-by-zero guard, not a silent default
    with pytest.raises((KeyError, TypeError)):
        checks.power_budget([{"name": "x"}])     # missing voltage/current -> error, never assumed


def test_deepdive_wiring_verifies_math_best_effort():
    # the decision path recomputes the model's arithmetic; a wrong figure is flagged, not shipped.
    from edos.engines.deepdive import _verify_computations
    out = _verify_computations([{"quantity": "Tj", "expression": "25 + 2*40", "result": 150}])
    assert out and out[0]["verified"] is False and out[0]["computed"] == 105.0
    assert _verify_computations(None) == []      # robust to the heuristic path (no computations)


def test_every_formula_reports_its_provenance():
    for r in (checks.ldo_dissipation(5, 3.3, 0.5),
              checks.thermal_junction(2, 40, 25),
              checks.battery_life(220, 0.11)):
        assert r["formula"] and r["inputs"]      # the arithmetic and its inputs are always shown
        assert not math.isnan(r["value"])


def test_auto_compute_thermal_and_battery():
    from edos.engines.checks import auto_compute, verify_computations
    ctx = ["Power stage dissipates 0.85 W into a package with Rθ 110 C/W",
           "CR2032 225 mAh, average current 40 uA in sleep"]
    got = auto_compute(ctx)
    quantities = {c["quantity"] for c in got}
    assert any("Thermal" in q for q in quantities)
    assert any("Battery" in q for q in quantities)
    # thermal ΔT = 0.85*110 = 93.5
    thermal = next(c for c in got if "Thermal" in c["quantity"])
    assert abs(thermal["result"] - 93.5) < 0.01
    # the EDOS-computed facts pass their OWN verification (they are real arithmetic)
    verified = verify_computations(got)
    assert all(v["verified"] is True for v in verified)


def test_auto_compute_is_conservative_when_ambiguous():
    from edos.engines.checks import auto_compute
    # a peak (not average) current must NOT be used for battery life; no Rθ => no thermal
    assert auto_compute(["CR2032 225 mAh, peak current 8 mA"]) == []
    assert auto_compute(["some prose with no stated quantities"]) == []
