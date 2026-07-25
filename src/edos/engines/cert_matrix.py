"""Certification Matrix (UI-CP-10, PDF p8).

Detects the certification standards a project actually mentions (reusing the same standards vocabulary the
Execution Context scan uses — single source of truth) and lays them out as a matrix:

    rows    = detected standards
    columns = regions (India, Europe) + optional Cost + optional Timeline

The **region applicability** per standard comes from a small, static, real-world map (e.g. AIS 156 → India,
ECE R100 → Europe, ISO 26262 / UN 38.3 / IEC 62619 → both). This is domain fact, not a fabricated number.

**Cost and Timeline are never invented.** A cost/timeline is attached to a standard *only* when a figure
(``$…`` / ``… weeks`` / ``… months``) actually co-occurs with that standard in the project text — i.e. it is
extracted, not guessed. If no figure exists, the cell is left blank (``None``).

Deterministic, no LLM. One responsibility: project the standards scan onto a regions×cost×timeline matrix.
"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from edos.db.models import ProjectItem
from edos.engines import assumptions as assumptions_engine
from edos.engines import decision_store
from edos.engines.execution_context import _STANDARD_PATTERNS, _decision_text

# The two regions this matrix scores (PDF p8 columns). Extend as markets are added.
REGIONS: list[str] = ["India", "Europe"]

# Static, real-world region applicability per standard label. A standard maps to the subset of REGIONS whose
# certification regime it belongs to; standards that belong to neither (e.g. US-only UL/FCC) map to []. This
# is engineering fact (which regulator owns which standard), not a fabricated score.
REGION_MAP: dict[str, list[str]] = {
    "ISO 26262": ["India", "Europe"],   # functional safety — international
    "ISO 16750": ["India", "Europe"],   # road-vehicle environmental — international
    "AEC-Q100": ["India", "Europe"],    # automotive electronics qualification — global
    "AEC-Q200": ["India", "Europe"],
    "UN 38.3": ["India", "Europe"],     # battery transport — international
    "AIS 156": ["India"],               # India EV/battery safety standard
    "ECE R100": ["Europe"],             # UNECE EV safety — Europe
    "IEC 62619": ["India", "Europe"],   # industrial secondary-cell safety — international
    "IEC 62368": ["India", "Europe"],   # AV/IT equipment safety — international
    "IATF 16949": ["India", "Europe"],  # automotive QMS — global
    "CISPR 25": ["India", "Europe"],    # automotive EMC — international
    "IP67": ["India", "Europe"],        # ingress protection — international
    "ASIL": ["India", "Europe"],        # ISO 26262 safety integrity level
    "RoHS": ["Europe"],                 # EU restriction of hazardous substances
    "REACH": ["Europe"],                # EU chemicals regulation
    "CE marking": ["Europe"],           # EU conformity mark
    "UL 2580": [],                       # US battery safety — outside India/Europe columns
    "FCC Part 15": [],                   # US EMC — outside India/Europe columns
}

# figure extractors — a cost or a schedule figure that co-occurs with a standard in the same text fragment.
_COST_RE = re.compile(
    r"(?:(?:US)?\$|USD|EUR|GBP|INR|₹|€|£)\s?\d[\d,]*(?:\.\d+)?\s?[KkMmBb]?"
    r"|\d[\d,]*(?:\.\d+)?\s?(?:lakh|crore|USD|EUR|dollars?|euros?|rupees?)\b",
    re.IGNORECASE,
)
_TIME_RE = re.compile(
    r"\d+(?:\s?[-–]\s?\d+)?\s?(?:weeks?|months?|days?|years?|wks?)\b", re.IGNORECASE
)


def _corpus(session: Session, project_id: str) -> list[str]:
    """All searchable text fragments in the project — items, decisions, assumptions."""
    frags: list[str] = []
    for it in session.scalars(select(ProjectItem).where(ProjectItem.project_id == project_id)):
        if it.content:
            frags.append(it.content)
    for row in decision_store.list_for_project(session, project_id):
        frags.append(_decision_text(row))
    for a in assumptions_engine.list_for_project(session, project_id):
        frags.append(" ".join(x for x in (a.statement, a.risk_if_wrong) if x))
    return [f for f in frags if f and f.strip()]


def build(session: Session, project_id: str) -> dict:
    """Assemble the certification matrix. Returns
    ``{regions:[...], standards:[{standard, regions:[...], cost?, timeline?}]}``.
    Empty ``standards`` == no standards mentioned yet (UI shows the empty state)."""
    frags = _corpus(session, project_id)

    standards: list[dict] = []
    seen: set[str] = set()
    for label, pattern in _STANDARD_PATTERNS:
        if label in seen:
            continue
        # collect the fragments that mention this standard (first-mention order preserved)
        hits = [f for f in frags if pattern.search(f)]
        if not hits:
            continue
        seen.add(label)
        # cost / timeline are extracted ONLY from text that co-mentions the standard — never fabricated
        cost = timeline = None
        for f in hits:
            if cost is None:
                m = _COST_RE.search(f)
                if m:
                    cost = m.group(0).strip().rstrip(",.;")
            if timeline is None:
                m = _TIME_RE.search(f)
                if m:
                    timeline = m.group(0).strip().rstrip(",.;")
        entry: dict = {"standard": label, "regions": REGION_MAP.get(label, [])}
        if cost is not None:
            entry["cost"] = cost
        if timeline is not None:
            entry["timeline"] = timeline
        standards.append(entry)

    return {"regions": REGIONS, "standards": standards}
