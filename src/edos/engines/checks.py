"""Deterministic engineering checks (Wave 3 · Step 8).

"AI reasons, software verifies." An LLM that *shows its arithmetic* still makes arithmetic mistakes, and an
expert distrusts a number the model merely reasoned to. This module recomputes the model's OWN stated math
deterministically — so a computed figure carries a real ✓, and a wrong one is caught, not shipped.

Two honest disciplines (CLAUDE.md truth rule — never fabricate a value):
  * We only VERIFY math the model already stated (`verify_computations`); we never invent inputs.
  * The canonical formula helpers (LDO dissipation, thermal rise, battery life, power budget) are pure
    references a caller can use when it *has* the numbers — each returns the formula it applied, for
    provenance. They compute; they do not guess missing inputs (missing input -> ValueError, never a default).

`safe_arith` evaluates a restricted arithmetic grammar via `ast` — numbers and + - * / ** ( ) only, no
names, calls, or attributes — so verifying a model-supplied expression can never execute code.
"""
from __future__ import annotations

import ast
import operator
import re

_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos,
}

# unit/suffix tokens we strip from a numeric expression before evaluating (case-insensitive), e.g.
# "3.3 V", "100 mA", "40 C/W", "220 mAh". We only strip units — we never rescale (no hidden milli→base).
_UNIT = re.compile(
    r"\b(?:mah|mwh|wh|kwh|ma|ua|na|a|mv|kv|v|mw|kw|w|mohm|kohm|ohm|khz|mhz|ghz|hz|"
    r"c/w|k/w|°c|c|k|mm|cm|m|ms|us|ns|s|%)\b",
    re.IGNORECASE,
)


def safe_arith(expr: str) -> float | None:
    """Evaluate a pure-arithmetic expression safely, or return None if it isn't pure arithmetic.

    Strips unit tokens first ("(3.3-1.8)*0.5 A" -> "(3.3-1.8)*0.5"). Only numbers and + - * / ** and
    parentheses are allowed; anything else (a name, a call, an attribute) returns None."""
    if not expr or not isinstance(expr, str):
        return None
    cleaned = _UNIT.sub(" ", expr).replace("×", "*").replace("÷", "/").strip()
    if not cleaned:
        return None
    try:
        node = ast.parse(cleaned, mode="eval").body
        return _eval_node(node)
    except (SyntaxError, ValueError, TypeError, ZeroDivisionError, KeyError):
        return None


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise TypeError("non-numeric constant")
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.operand))
    raise ValueError(f"disallowed expression node: {type(node).__name__}")


def verify_computation(expression: str, claimed_result: object, *, rel_tol: float = 0.02) -> dict:
    """Recompute one model-supplied `expression` and compare to its `claimed_result`.

    Returns `{expression, computed, claimed, verified, note}`. `verified` is True when the arithmetic
    re-evaluates within `rel_tol` of the claim, False when it disagrees, and None when the expression isn't
    pure arithmetic we can check (so the UI shows "unchecked", never a false ✓)."""
    computed = safe_arith(expression)
    claimed = _as_number(claimed_result)
    if computed is None:
        return {"expression": expression, "computed": None, "claimed": claimed,
                "verified": None, "note": "not a checkable arithmetic expression"}
    if claimed is None:
        return {"expression": expression, "computed": round(computed, 6), "claimed": claimed_result,
                "verified": None, "note": "no numeric result claimed to compare against"}
    denom = abs(claimed) if claimed else 1.0
    ok = abs(computed - claimed) <= rel_tol * denom
    return {"expression": expression, "computed": round(computed, 6), "claimed": claimed,
            "verified": ok, "note": "" if ok else "arithmetic does not match the stated result"}


def verify_computations(computations: object, *, rel_tol: float = 0.02) -> list[dict]:
    """Verify a list of `{quantity, expression, result}` items the model emitted. Non-list / malformed input
    yields an empty list (best-effort — never raises into the decision path)."""
    out: list[dict] = []
    if not isinstance(computations, list):
        return out
    for c in computations:
        if not isinstance(c, dict) or not c.get("expression"):
            continue
        v = verify_computation(str(c["expression"]), c.get("result"), rel_tol=rel_tol)
        v["quantity"] = str(c.get("quantity", "")).strip()
        if c.get("note"):
            v["note"] = (v["note"] + " · " + str(c["note"])).strip(" ·")
        out.append(v)
    return out


def _as_number(x: object) -> float | None:
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        return safe_arith(x)
    return None


# ---------------------------------------------------------------------------------------------------
# Canonical embedded formulas — pure references. Each returns {value, unit, formula, inputs}. They compute
# from GIVEN numbers; a missing input is an error, never a silent default (no fabrication).
# ---------------------------------------------------------------------------------------------------
def ldo_dissipation(vin_v: float, vout_v: float, iout_a: float) -> dict:
    """Linear-regulator power dissipation: P = (Vin − Vout) · Iout (watts)."""
    p = (vin_v - vout_v) * iout_a
    return {"value": round(p, 4), "unit": "W", "formula": "P = (Vin − Vout) · Iout",
            "inputs": {"Vin_V": vin_v, "Vout_V": vout_v, "Iout_A": iout_a}}


def thermal_junction(power_w: float, rtheta_c_per_w: float, ambient_c: float,
                     tj_max_c: float | None = None) -> dict:
    """Junction temperature: Tj = Tambient + P · Rθ. If `tj_max_c` given, reports headroom and a pass flag."""
    tj = ambient_c + power_w * rtheta_c_per_w
    out = {"value": round(tj, 2), "unit": "°C", "formula": "Tj = Tambient + P · Rθ",
           "inputs": {"P_W": power_w, "Rtheta_C_per_W": rtheta_c_per_w, "Tambient_C": ambient_c}}
    if tj_max_c is not None:
        out["headroom_C"] = round(tj_max_c - tj, 2)
        out["within_limit"] = tj <= tj_max_c
        out["inputs"]["Tj_max_C"] = tj_max_c
    return out


def battery_life(capacity_mah: float, avg_current_ma: float) -> dict:
    """Battery life at a constant average draw: hours = capacity / average current. Reports raw run-time; it
    does NOT apply a hidden derating factor (self-discharge, usable-capacity) — that is the engineer's call."""
    if avg_current_ma <= 0:
        raise ValueError("avg_current_ma must be > 0")
    hours = capacity_mah / avg_current_ma
    return {"value": round(hours, 2), "unit": "h", "formula": "t = Capacity(mAh) / I_avg(mA)",
            "days": round(hours / 24.0, 2),
            "inputs": {"capacity_mAh": capacity_mah, "I_avg_mA": avg_current_ma}}


def power_budget(rails: list[dict]) -> dict:
    """Total power from a list of rails, each `{name, voltage_v, current_a}`: P = Σ V·I."""
    total_w = 0.0
    per: list[dict] = []
    for r in rails:
        v, i = float(r["voltage_v"]), float(r["current_a"])
        w = v * i
        total_w += w
        per.append({"name": r.get("name", "?"), "power_W": round(w, 4)})
    return {"value": round(total_w, 4), "unit": "W", "formula": "P_total = Σ (V·I) per rail",
            "rails": per}


# ---------------------------------------------------------------------------------------------------
# Independent auto-compute (Feature 3): EDOS computes a budget ITSELF from quantities stated in the project,
# not just verifying the model. Deliberately CONSERVATIVE — only the checks whose inputs are unambiguous by
# unit are run (thermal ΔT: W and °C/W; battery life: mAh + an *explicitly labelled* average current). We do
# NOT auto-run LDO dissipation (which is which voltage is ambiguous) or a power-budget sum (peak-vs-average /
# which-rail is ambiguous) — a misattributed input presented as a ✓ would be worse than not computing. Results
# are emitted in the SAME `{quantity, expression, result}` shape the model uses, so they flow through
# `verify_computations` and render as computed ✓ with no special UI.
# ---------------------------------------------------------------------------------------------------
def _find_num(pattern: str, text: str) -> float | None:
    m = re.search(pattern, text, flags=re.IGNORECASE)
    try:
        return float(m.group(1)) if m else None
    except (ValueError, IndexError):
        return None


def auto_compute(context_texts: list[str]) -> list[dict]:
    """Return `[{quantity, expression, result, note}]` for the budgets EDOS can compute unambiguously from the
    stated quantities. Empty when the inputs aren't clearly present (the honest, common case)."""
    text = "\n".join(t for t in context_texts if t)
    if not text.strip():
        return []
    out: list[dict] = []

    # Thermal rise ΔT = P·Rθ — 'W' and '°C/W' disambiguate the inputs, so this is safe to auto-run.
    p_w = _find_num(r"(\d+(?:\.\d+)?)\s*W\b", text)          # a power in watts (not mW/kW: needs digit+space+W)
    rth = _find_num(r"(\d+(?:\.\d+)?)\s*°?\s*C\s*/\s*W", text)  # thermal resistance °C/W
    if p_w is not None and rth is not None:
        out.append({"quantity": "Thermal rise ΔT (°C)", "expression": f"{p_w} * {rth}",
                    "result": round(p_w * rth, 2), "note": "EDOS computed from the stated P and Rθ"})

    # Battery life = capacity / average current — capacity (mAh) is unambiguous; the current MUST be labelled
    # average/quiescent/sleep (using a peak current here would mislead, so we refuse to guess).
    cap_mah = _find_num(r"(\d+(?:\.\d+)?)\s*mAh", text)
    m = re.search(r"(?:average|avg|quiescent|sleep|standby)\D{0,20}(\d+(?:\.\d+)?)\s*(µA|uA|mA)",
                  text, flags=re.IGNORECASE)
    if cap_mah is not None and m:
        val = float(m.group(1))
        avg_ma = val * 1e-3 if m.group(2).lower() in ("µa", "ua") else val
        if avg_ma > 0:
            out.append({"quantity": "Battery life (hours)", "expression": f"{cap_mah} / {avg_ma}",
                        "result": round(cap_mah / avg_ma, 1),
                        "note": "EDOS computed (capacity ÷ the labelled average current)"})
    return out
