"""Execution Context — the handoff (UI-CP-9, PDF p24).

*"Instead of generating a prompt, EDOS emits an Execution Context that any AI coding agent can consume —
Claude Code, Codex, Cursor, or whatever comes next.* **EDOS decides. Agents execute.**"

This engine assembles a coherent, **machine-readable spec** from what the project has actually decided and
learned — accepted decisions + first-class assumptions + findings/graph — into the dark spec-card sections of
the PDF: **ACCEPTED DECISIONS · CONSTRAINTS · INTERFACES · ACCEPTANCE CRITERIA · STANDARDS · OPEN RISKS**.

It is a *spec, not a prompt*: every line is derived deterministically (no LLM) from persisted state, so the
same project always emits the same context. Nothing is fabricated — if a section has no source, it is an empty
list. ``build`` accepts an optional ``now`` (injected timestamp) so ``meta.generated_at`` never depends on the
wall clock in tests; the endpoint passes a real ``now`` live.

Responsibilities (one engine, one job — CLAUDE.md): read the decision store / assumption ledger / graph /
coverage and *project* them into the export shape. It holds no reasoning of its own.
"""
from __future__ import annotations

import datetime as dt
import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from edos.db.models import ProjectItem
from edos.engines import assumptions as assumptions_engine
from edos.engines import coverage, decision_store, graph_view

# ---- statuses (persistence envelope) -------------------------------------------------------------
_ACCEPTED = "accepted"
# fall-back statuses used when a project has no accepted decisions yet (marked provisional in the output)
_PROVISIONAL_STATUSES: frozenset[str] = frozenset({"recommended", "verified", "proposed"})

# ---- interface protocol vocabulary (heuristic scan) ----------------------------------------------
# canonical label → set of surface spellings matched as whole tokens (case-insensitive)
_INTERFACE_KEYWORDS: tuple[str, ...] = (
    "isoSPI", "SPI", "CAN-FD", "CAN", "I2C", "I3C", "UART", "USART", "BLE", "Bluetooth", "ADC", "DAC",
    "GPIO", "PWM", "JTAG", "SWD", "LIN", "MODBUS", "Ethernet", "RS-485", "RS485", "RS-232", "USB",
    "LoRa", "Wi-Fi", "WiFi", "NFC", "Zigbee", "1-Wire", "QSPI",
)

# ---- standards / regulatory vocabulary (heuristic scan) ------------------------------------------
# (canonical label, compiled matcher). Order matters only for readability; matches are de-duped by label.
_STANDARD_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (label, re.compile(pattern, re.IGNORECASE))
    for label, pattern in (
        ("ISO 26262", r"ISO[\s\-]?26262"),
        ("ISO 16750", r"ISO[\s\-]?16750"),
        ("AEC-Q100", r"AEC[\s\-]?Q100"),
        ("AEC-Q200", r"AEC[\s\-]?Q200"),
        ("UN 38.3", r"UN[\s\-]?38\.3"),
        ("AIS 156", r"AIS[\s\-]?156"),
        ("ECE R100", r"ECE[\s\-]?R100"),
        ("IEC 62619", r"IEC[\s\-]?62619"),
        ("IEC 62368", r"IEC[\s\-]?62368"),
        ("UL 2580", r"UL[\s\-]?2580"),
        ("IATF 16949", r"IATF[\s\-]?16949"),
        ("CISPR 25", r"CISPR[\s\-]?25"),
        ("IP67", r"IP6[5-9]"),
        ("ASIL", r"ASIL[\s\-]?[ABCD]?"),
        ("RoHS", r"RoHS"),
        ("REACH", r"\bREACH\b"),
        ("FCC Part 15", r"FCC(\s+Part)?\s*15"),
        ("CE marking", r"\bCE\s+mark"),
    )
)

# ---- measurable-acceptance cues (a requirement item that reads like a testable criterion) --------
_MEASURABLE_CUES: tuple[str, ...] = (
    "shall", "must", "≤", "≥", "<=", ">=", "±", "+/-", "%", "threshold", "min ", "max ",
    "pass/fail", "within", "no more than", "at least", "tolerance", "accuracy",
)

# project items that count as hard constraints / requirements
_REQUIREMENT_TYPES: frozenset[str] = frozenset({"requirement", "constraint"})


# ==================================================================================================
# corpus helpers (for the keyword scans)
# ==================================================================================================
def _decision_text(row) -> str:
    dec = decision_store.to_decision(row)
    parts = [dec.summary, dec.recommendation]
    parts += [r.description for r in dec.risks]
    parts += [a.statement for a in dec.assumptions]
    parts += list(dec.next_actions)
    return " ".join(p for p in parts if p)


def _corpus(session: Session, project_id: str, decisions, assumption_rows, items) -> list[tuple[str, str]]:
    """All searchable ``(ref, text)`` fragments in the project — items, decisions, assumptions."""
    docs: list[tuple[str, str]] = []
    for it in items:
        docs.append((it.id, it.content or ""))
    for row in decisions:
        docs.append((row.id, _decision_text(row)))
    for a in assumption_rows:
        docs.append((a.id, " ".join(x for x in (a.statement, a.risk_if_wrong) if x)))
    return docs


def _scan_interfaces(docs: list[tuple[str, str]]) -> list[dict]:
    """Whole-token scan for interface/bus protocols. One entry per distinct protocol (first source wins)."""
    found: dict[str, str] = {}  # canonical label → first ref it appeared in
    for ref, text in docs:
        if not text:
            continue
        for kw in _INTERFACE_KEYWORDS:
            if kw in found:
                continue
            if re.search(rf"(?<![A-Za-z0-9]){re.escape(kw)}(?![A-Za-z0-9])", text, re.IGNORECASE):
                found[kw] = ref
    return [{"text": kw, "protocol": kw, "source": ref} for kw, ref in found.items()]


def _scan_standards(docs: list[tuple[str, str]]) -> list[dict]:
    """Scan for referenced standards / regulations. One entry per distinct standard (first source wins)."""
    found: dict[str, str] = {}
    for ref, text in docs:
        if not text:
            continue
        for label, pattern in _STANDARD_PATTERNS:
            if label in found:
                continue
            if pattern.search(text):
                found[label] = ref
    return [{"text": label, "source": ref} for label, ref in found.items()]


# ==================================================================================================
# per-decision projections
# ==================================================================================================
def _key_params(dec, detail: dict) -> list[str]:
    """Concise key parameters for an accepted decision — the recommended option's criteria values +
    impacted components, derived from the decision + its ``decision_detail`` (never fabricated)."""
    detail = detail or {}
    params: list[str] = []
    cm = detail.get("comparison_matrix") or {}
    criteria = cm.get("criteria") or []
    rec_opt = next((o for o in (cm.get("options") or []) if o.get("recommended")), None)
    if rec_opt:
        if rec_opt.get("name"):
            params.append(f"Chosen option: {rec_opt['name']}")
        for c, v in zip(criteria, rec_opt.get("values") or [], strict=False):
            if c and v:
                params.append(f"{c}: {v}")
    else:
        rec = detail.get("recommendation") or {}
        if isinstance(rec, dict) and rec.get("chosen"):
            params.append(f"Chosen option: {rec['chosen']}")
    comps = [c for c in (detail.get("impacted_components") or []) if c]
    if comps:
        params.append("Impacted components: " + ", ".join(comps))
    return params


def _detail_of(row) -> dict:
    """Tolerant parse of the persistence-envelope ``decision_detail`` (rich Decision-Card block)."""
    if not row or not row.decision_detail:
        return {}
    try:
        data = json.loads(row.decision_detail)
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


# ==================================================================================================
# build
# ==================================================================================================
def build(session: Session, project_id: str, *, now: dt.datetime | None = None) -> dict:
    """Assemble the Execution Context for a project. Deterministic; ``now`` (if given) stamps
    ``meta.generated_at``. Empty sections come back as empty lists — nothing is invented."""
    decisions = decision_store.list_for_project(session, project_id)
    assumption_rows = assumptions_engine.list_for_project(session, project_id)
    items = list(
        session.scalars(select(ProjectItem).where(ProjectItem.project_id == project_id)
                        .order_by(ProjectItem.created_at))
    )

    accepted_rows = [r for r in decisions if r.status == _ACCEPTED]
    provisional = False
    if not accepted_rows:
        # No accepted decisions yet → fall back to the latest recommended/verified ones, MARKED provisional.
        accepted_rows = [r for r in decisions if r.status in _PROVISIONAL_STATUSES]
        provisional = bool(accepted_rows)

    # ---- ACCEPTED DECISIONS ----
    accepted_decisions: list[dict] = []
    for row in accepted_rows:
        dec = decision_store.to_decision(row)
        detail = _detail_of(row)
        accepted_decisions.append({
            "id": row.id,
            "summary": dec.summary,
            "recommendation": dec.recommendation,
            "key_params": _key_params(dec, detail),
            "status": row.status,
            "provisional": provisional,
            "confidence": round(dec.confidence, 2),
        })

    # ---- CONSTRAINTS (requirement items + review_conditions + high/critical risks) ----
    constraints: list[dict] = []
    for it in items:
        if it.item_type in _REQUIREMENT_TYPES and (it.content or "").strip():
            constraints.append({"text": it.content.strip(), "source": it.id, "domain": it.domain})
    for row in accepted_rows:
        detail = _detail_of(row)
        for rc in detail.get("review_conditions") or []:
            if rc:
                constraints.append({"text": rc, "source": row.id})
        dec = decision_store.to_decision(row)
        for risk in dec.risks:
            if risk.severity in ("high", "critical"):
                text = risk.description
                if risk.mitigation:
                    text = f"{text} — mitigation: {risk.mitigation}"
                constraints.append({"text": text, "source": row.id, "severity": risk.severity})

    # ---- INTERFACES (impacted_components + protocol keyword scan) ----
    interfaces: list[dict] = []
    seen_comp: set[str] = set()
    for row in accepted_rows:
        detail = _detail_of(row)
        for comp in detail.get("impacted_components") or []:
            if comp and comp not in seen_comp:
                seen_comp.add(comp)
                interfaces.append({"text": comp, "source": row.id, "kind": "component"})
    interfaces += _scan_interfaces(_corpus(session, project_id, decisions, assumption_rows, items))

    # ---- ACCEPTANCE CRITERIA (next_actions + measurable requirement items) ----
    acceptance_criteria: list[dict] = []
    for row in accepted_rows:
        dec = decision_store.to_decision(row)
        for na in dec.next_actions:
            if na:
                acceptance_criteria.append({"text": na, "source": row.id})
    for it in items:
        content = (it.content or "")
        low = content.lower()
        if it.item_type in _REQUIREMENT_TYPES and (
            any(cue in low for cue in _MEASURABLE_CUES) or re.search(r"\d", content)
        ):
            acceptance_criteria.append({"text": content.strip(), "source": it.id, "measurable": True})

    # ---- STANDARDS (keyword scan across the whole project) ----
    standards = _scan_standards(_corpus(session, project_id, decisions, assumption_rows, items))

    # ---- OPEN RISKS (open/challenged assumptions + active contradictions + freeze blockers) ----
    open_risks: list[dict] = []
    for a in assumption_rows:
        if a.status in ("created", "challenged"):
            open_risks.append({
                "text": a.statement, "source": a.id, "kind": "assumption", "status": a.status,
                "risk_if_wrong": a.risk_if_wrong,
            })
    for con in graph_view.contradictions(session, project_id):
        if con.get("validity") == "active":
            open_risks.append({
                "text": con["explanation"], "source": f"{con['a']}⇄{con['b']}",
                "kind": "contradiction",
            })
    for row in accepted_rows:
        dec = decision_store.to_decision(row)
        for fb in dec.freeze_blockers:
            if fb:
                open_risks.append({"text": fb, "source": row.id, "kind": "freeze_blocker"})

    report = coverage.coverage_report(session, project_id)
    return {
        "accepted_decisions": accepted_decisions,
        "constraints": constraints,
        "interfaces": interfaces,
        "acceptance_criteria": acceptance_criteria,
        "standards": standards,
        "open_risks": open_risks,
        "meta": {
            "project_id": project_id,
            "generated_at": now.isoformat() if now else None,
            "coverage": report["overall"],
            "coverage_by_domain": report["by_domain"],
            "provisional": provisional,
        },
    }


# ==================================================================================================
# plain-text spec (copy-pasteable handoff for a coding agent)
# ==================================================================================================
def _bullets(entries: list[dict], empty: str) -> list[str]:
    if not entries:
        return [f"  (none — {empty})"]
    lines: list[str] = []
    for e in entries:
        ref = e.get("source")
        suffix = f"  [{ref}]" if ref else ""
        lines.append(f"  - {e['text']}{suffix}")
    return lines


def to_text(context: dict) -> str:
    """Render the Execution Context as a copy-pasteable plain-text spec (the dark-card layout as text)."""
    meta = context.get("meta", {})
    out: list[str] = []
    out.append("=" * 68)
    out.append("EDOS EXECUTION CONTEXT")
    out.append("EDOS decides. Agents execute.")
    out.append("=" * 68)
    head = f"Project: {meta.get('project_id', '?')}    Coverage: {meta.get('coverage', 0)}%"
    if meta.get("generated_at"):
        head += f"    Generated: {meta['generated_at']}"
    out.append(head)
    if meta.get("provisional"):
        out.append("NOTE: no decisions ACCEPTED yet — showing latest RECOMMENDED (provisional).")
    out.append("")

    out.append("## ACCEPTED DECISIONS")
    if not context["accepted_decisions"]:
        out.append("  (none — accept a decision to populate this spec)")
    for d in context["accepted_decisions"]:
        tag = " (provisional)" if d.get("provisional") else ""
        out.append(f"  - [{d['id']}] {d['summary']}{tag}")
        out.append(f"      {d['recommendation']}")
        for kp in d.get("key_params") or []:
            out.append(f"        · {kp}")
    out.append("")

    out.append("## CONSTRAINTS")
    out.extend(_bullets(context["constraints"], "add requirements / review conditions"))
    out.append("")

    out.append("## INTERFACES")
    out.extend(_bullets(context["interfaces"], "no interfaces/protocols referenced yet"))
    out.append("")

    out.append("## ACCEPTANCE CRITERIA")
    out.extend(_bullets(context["acceptance_criteria"], "add next actions / measurable requirements"))
    out.append("")

    out.append("## STANDARDS & OPEN RISKS")
    if context["standards"]:
        out.append("  Standards:")
        for s in context["standards"]:
            ref = s.get("source")
            out.append(f"    - {s['text']}" + (f"  [{ref}]" if ref else ""))
    else:
        out.append("  Standards: (none referenced)")
    if context["open_risks"]:
        out.append("  Open risks:")
        for r in context["open_risks"]:
            kind = r.get("kind", "risk")
            ref = r.get("source")
            out.append(f"    - ({kind}) {r['text']}" + (f"  [{ref}]" if ref else ""))
    else:
        out.append("  Open risks: (none open)")
    out.append("")
    out.append("=" * 68)
    return "\n".join(out)
