"""Challenge My Decision (UI-CP-5) — EDOS argues AGAINST its own recommendation.

The iconic interaction (PDF p11): instead of defending the decision, EDOS behaves like a skeptical principal
engineer. It names the single **load-bearing assumption** the recommendation rests on, then shows, side by
side, **what that assumption is costing you** vs **what the alternative offers**, plus a red **cost callout**.
Marking the assumption *challenged* turns it from a silent assumption into a monitored risk (see
``resolution.challenge_assumption``).

``challenge(decision)`` returns::

    {assumption, this_costs[], alternative_offers[], cost_callout, alternative}

Like ``extraction.py`` / ``deepdive.py`` it routes through the Model Router with a JSON schema and falls back
to a deterministic heuristic offline (stub provider) / on malformed output — so the suite is deterministic and
honest offline, richer live. The heuristic NEVER fabricates dollar figures: the counter-case is built from the
assumption text + the decision's own tradeoffs/risks, and the cost callout stays qualitative unless real
numbers already exist in the decision (a live LLM may quantify).
"""
from __future__ import annotations

import re

from edos.engines.model_router import Capability, ModelRouter
from edos.models.decision import Assumption, Decision

# risk_if_wrong keyword → severity weight (transparent, tunable; not fabricated).
_SEVERITY_KW: tuple[tuple[str, float], ...] = (
    ("catastroph", 1.0), ("recall", 1.0), ("unsafe", 0.95), ("safety", 0.9), ("critical", 0.9),
    ("fire", 0.9), ("fail", 0.75), ("redesign", 0.7), ("respin", 0.7), ("invalidate", 0.6),
    ("miss", 0.5), ("cost", 0.45), ("delay", 0.4), ("rework", 0.5),
)


def _severity(text: str | None) -> float:
    low = (text or "").lower()
    return max((w for kw, w in _SEVERITY_KW if kw in low), default=0.0)


def load_bearing_assumption(decision: Decision) -> Assumption | None:
    """The single assumption the decision most rests on.

    Heuristic (per spec): the **lowest-confidence** assumption, biased toward the one whose ``risk_if_wrong``
    is most severe. Score = confidence − 0.4·severity; the minimum is the most load-bearing (a low-confidence
    assumption with a catastrophic downside beats a low-confidence one with no stated risk)."""
    if not decision.assumptions:
        return None
    return min(decision.assumptions, key=lambda a: a.confidence - 0.4 * _severity(a.risk_if_wrong))


def _chosen_option(decision: Decision) -> str:
    """The option the decision recommends — matched against its tradeoff options, else parsed from the text."""
    rec = (decision.recommendation or "").lower()
    for t in decision.tradeoffs:
        if t.option and t.option.lower() in rec:
            return t.option
    if decision.tradeoffs:
        return decision.tradeoffs[0].option
    m = re.search(r"recommend(?:s|ed)?\s+([A-Za-z0-9 /+-]{2,40})", decision.recommendation or "")
    return (m.group(1).strip(" .") if m else "the recommended option")


def _alternative_tradeoff(decision: Decision, chosen: str):
    """The strongest non-chosen tradeoff option (what we'd fall back to if the assumption breaks)."""
    for t in decision.tradeoffs:
        if t.option and t.option.lower() != chosen.lower():
            return t
    return None


_MONEY = re.compile(r"(?:\$\s?\d[\d,\.]*\s?[kKmM]?(?:\s?[-–]\s?\$?\d[\d,\.]*\s?[kKmM]?)?"
                    r"|\d[\d,\.]*\s?(?:units?|pcs|k units|/unit|per unit))")


def _existing_figures(decision: Decision) -> list[str]:
    """Pull any dollar/quantity figures the engineer already put in the decision. We only ever quote numbers
    that ALREADY exist — we never invent them offline."""
    blob = " ".join([
        decision.summary or "", decision.recommendation or "",
        *[f"{t.benefit} {t.drawback}" for t in decision.tradeoffs],
        *[r.description for r in decision.risks],
        *[f"{a.statement} {a.risk_if_wrong or ''}" for a in decision.assumptions],
    ])
    seen: list[str] = []
    for m in _MONEY.findall(blob):
        s = m.strip()
        if s and s not in seen:
            seen.append(s)
    return seen


def _short(text: str, n: int = 70) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _heuristic(decision: Decision, assumption: Assumption) -> dict:
    """Deterministic counter-case from the assumption + the decision's own tradeoffs/risks. No invented $."""
    chosen = _chosen_option(decision)
    alt_t = _alternative_tradeoff(decision, chosen)
    alternative = alt_t.option if alt_t else "the alternative approach"
    chosen_drawback = next((t.drawback for t in decision.tradeoffs if t.option.lower() == chosen.lower()), "")

    this_costs = [
        (f"Holding \"{_short(assumption.statement)}\" is what locks in {chosen} — "
         f"if it's softer than assumed, {chosen} is the wrong default."),
    ]
    if chosen_drawback:
        this_costs.append(f"You inherit {chosen}'s drawback: {chosen_drawback}.")
    if assumption.risk_if_wrong:
        this_costs.append(f"If the assumption is wrong: {assumption.risk_if_wrong}.")
    # surface the most severe risk that this choice carries
    worst = max(decision.risks, key=lambda r: {"critical": 3, "high": 2, "medium": 1, "low": 0}
                .get(r.severity, 0), default=None)
    if worst is not None:
        this_costs.append(f"Live risk on this path: {worst.description}.")
    this_costs.append("Because it's an assumption, not a decision, no one is watching it decay.")

    alternative_offers = []
    if alt_t and alt_t.benefit:
        alternative_offers.append(f"{alternative} instead offers: {alt_t.benefit}.")
    alternative_offers += [
        f"It doesn't depend on \"{_short(assumption.statement)}\" being true, so it de-risks that assumption.",
        (f"Keeps the option open — you can revisit once \"{_short(assumption.statement, 40)}\" is actually "
         f"measured rather than assumed."),
    ]
    if alt_t and alt_t.drawback:
        alternative_offers.append(f"Cost of switching: {alt_t.drawback} — the price of removing the assumption.")

    # cost callout: qualitative offline; quote figures ONLY if the engineer already stated them.
    figures = _existing_figures(decision)
    if figures:
        cost_callout = (f"Assumption \"{_short(assumption.statement, 50)}\" is load-bearing at scale — "
                        f"against the stated {', '.join(figures[:2])} it is the difference between {chosen} "
                        f"and {alternative}, and right now it's an unmonitored guess.")
    else:
        cost_callout = (f"At volume, \"{_short(assumption.statement, 50)}\" quietly commits you to {chosen}: "
                        f"recurring BOM + firmware cost for a design a future variant may not need. "
                        f"The figure isn't in this decision yet — so it's a cost you're paying blind.")

    return {
        "assumption": assumption.model_dump(exclude_none=True),
        "this_costs": this_costs,
        "alternative_offers": alternative_offers,
        "cost_callout": cost_callout,
        "alternative": alternative,
    }


CHALLENGE_SCHEMA = {
    "type": "object",
    "properties": {
        "this_costs": {"type": "array", "items": {"type": "string"}},
        "alternative_offers": {"type": "array", "items": {"type": "string"}},
        "cost_callout": {"type": "string"},
        "alternative": {"type": "string"},
    },
    "required": ["this_costs", "alternative_offers", "cost_callout", "alternative"],
}


def challenge(decision: Decision, router: ModelRouter | None = None) -> dict | None:
    """Argue the counter-case against ``decision``. Returns the challenge payload, or ``None`` if the decision
    states no assumptions (nothing load-bearing to challenge). LLM first, deterministic heuristic fallback."""
    assumption = load_bearing_assumption(decision)
    if assumption is None:
        return None
    router = router or ModelRouter()
    try:
        out = router.execute(
            Capability.challenge,
            {"summary": decision.summary, "recommendation": decision.recommendation,
             "assumption": assumption.model_dump(exclude_none=True),
             "tradeoffs": [t.model_dump() for t in decision.tradeoffs],
             "risks": [r.model_dump(exclude_none=True) for r in decision.risks]},
            schema=CHALLENGE_SCHEMA,
        )
        costs = [str(c).strip() for c in out.get("this_costs", []) if str(c).strip()]
        offers = [str(o).strip() for o in out.get("alternative_offers", []) if str(o).strip()]
        if isinstance(out, dict) and costs and offers and out.get("cost_callout"):
            return {
                "assumption": assumption.model_dump(exclude_none=True),
                "this_costs": costs,
                "alternative_offers": offers,
                "cost_callout": str(out["cost_callout"]).strip(),
                "alternative": str(out.get("alternative") or _chosen_option(decision)).strip(),
            }
    except Exception:  # noqa: BLE001, S110 — any LLM/validation failure falls back to the heuristic below
        pass
    return _heuristic(decision, assumption)
