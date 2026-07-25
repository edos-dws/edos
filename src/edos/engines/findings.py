"""Engineering Review → Findings (UI-CP-3).

A **fast, no-question scan** of what the engineer is working on. Unlike Deep Dive (which asks targeted
questions), Review asks nothing — it immediately returns a list of categorized **findings**, each with a
severity, a one-paragraph detail, an "IF YOU IGNORE THIS" consequences list, and evidence chips.

The five finding categories (exact keys) and where each is sourced:

  * ``contradiction``       — the input conflicts with a stored decision, or an open ``conflicts_with``
                              edge already exists in the graph  (source: **graph / watchdog**, deterministic)
  * ``hidden_dependency``   — "you can't do X without Y"                    (source: **domain rules**)
  * ``best_practice``       — a standard approach that was missed           (source: **domain rules**)
  * ``assumption``          — you are guessing here                         (source: **LLM → heuristic**)
  * ``optimization``        — it works, but it could be better             (source: **LLM → heuristic**)

The LLM parts go through the Model Router with a JSON schema and fall back to a deterministic heuristic
exactly like ``extraction.py`` — so the suite is deterministic offline (stub provider) and it uses the real
model live. Findings are de-duped and sorted by severity (critical first).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from edos.db.models import DecisionRecord, GraphEdge, ProjectItem
from edos.engines import decision_store, domain, extraction
from edos.engines.model_router import Capability, ModelRouter

CATEGORIES = ("contradiction", "hidden_dependency", "assumption", "optimization", "best_practice")
_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
# procedural-memory rules use "info"; the finding severity scale has no "info" → map it to the lowest.
_SEVERITY_ALIAS = {"info": "low"}


@dataclass
class Finding:
    category: str                       # one of CATEGORIES
    severity: str                       # critical | high | medium | low
    title: str
    detail: str
    if_ignored: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _norm_severity(sev: str) -> str:
    sev = (sev or "").lower().strip()
    sev = _SEVERITY_ALIAS.get(sev, sev)
    return sev if sev in _SEVERITY_ORDER else "medium"


# --------------------------------------------------------------------------------------------------
# 1. contradictions — from the decision graph (deterministic; reuses graph_builder/watchdog wiring)
# --------------------------------------------------------------------------------------------------
# Mutually-exclusive engineering stances. Each concept lists its options as (name, phrases); phrases are
# checked in order so a *negated* / more-specific option wins before its own substring (e.g. "no isolation"
# before "isolation"). If the input picks one option and a stored decision picks a different one for the same
# concept, that's a contradiction. Transparent, tunable procedural memory — never a fabricated conflict.
_CONCEPTS: dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "cell balancing": [
        ("active", ("active balancing", "active cell balancing")),
        ("passive", ("passive balancing", "passive cell balancing")),
    ],
    "overcurrent protection": [
        ("software", ("software protection", "software-based protection", "firmware protection",
                      "protection in software", "software overcurrent")),
        ("hardware", ("hardware protection", "hardware-based protection", "hardware comparator",
                      "hardware overcurrent")),
    ],
    "current sensing": [
        ("hall", ("hall effect", "hall-effect", "hall sensor")),
        ("shunt", ("shunt resistor", "shunt-based", "shunt sense")),
    ],
    "isolation": [
        ("non_isolated", ("no isolation", "non-isolated", "without isolation", "not isolated")),
        ("isolated", ("galvanic isolation", "isolated design", "isolation barrier", "isolated")),
    ],
    "cooling": [
        ("active", ("forced air", "forced-air", "liquid cooling", "active cooling")),
        ("passive", ("passive cooling", "natural convection", "conduction cooling")),
    ],
}


def _pick_option(text: str, options: list[tuple[str, tuple[str, ...]]]) -> str | None:
    """Which option (if any) this text commits to for a concept. First matching option in list order wins;
    returns None if none match or the text is ambiguous (matches two different options)."""
    low = text.lower()
    hit = None
    for name, phrases in options:
        if any(p in low for p in phrases):
            if hit is not None and hit != name:
                return None  # ambiguous — the text discusses both options; don't fabricate a conflict
            hit = name
    return hit


def _stance_contradictions(text: str, session: Session, project_id: str) -> list[Finding]:
    findings: list[Finding] = []
    decisions = decision_store.list_for_project(session, project_id)
    for concept, options in _CONCEPTS.items():
        input_opt = _pick_option(text, options)
        if input_opt is None:
            continue
        for row in decisions:
            body = f"{row.title} {row.rationale}"
            dec_opt = _pick_option(body, options)
            if dec_opt is not None and dec_opt != input_opt:
                findings.append(Finding(
                    category="contradiction", severity="critical",
                    title=f"Conflicts with a past decision on {concept}",
                    detail=(f"The input specifies {input_opt} {concept}, but decision "
                            f"'{row.title}' already committed to {dec_opt} {concept}. This contradicts a "
                            f"stored decision — reconcile before proceeding."),
                    if_ignored=[
                        "Two subsystems built against opposing decisions",
                        "Rework once the conflict surfaces at integration",
                    ],
                    evidence=[f"decision {row.id}: {dec_opt} {concept}", f"input: {input_opt} {concept}"],
                ))
    return findings


def _graph_conflict_findings(session: Session, project_id: str) -> list[Finding]:
    """Surface open `conflicts_with` edges already in the project graph (reuses the graph the watchdog
    reads). One finding per unordered pair."""
    node_ids = set(session.scalars(
        select(ProjectItem.id).where(ProjectItem.project_id == project_id)
    ).all())
    node_ids |= set(session.scalars(
        select(DecisionRecord.id).where(DecisionRecord.project_id == project_id)
    ).all())
    if not node_ids:
        return []
    edges = session.scalars(
        select(GraphEdge).where(
            GraphEdge.relation_type == "conflicts_with", GraphEdge.validity == "active"
        )
    ).all()
    findings: list[Finding] = []
    seen: set[frozenset[str]] = set()
    for e in edges:
        if e.source_id not in node_ids or e.target_id not in node_ids:
            continue
        pair = frozenset({e.source_id, e.target_id})
        if pair in seen:
            continue
        seen.add(pair)
        a, b = sorted(pair)
        findings.append(Finding(
            category="contradiction", severity="high",
            title="Open contradiction in the decision graph",
            detail=(f"'{a}' and '{b}' are in an unresolved conflict in this project's decision graph. "
                    f"Resolve it before relying on either."),
            if_ignored=["Downstream work builds on an unresolved conflict",
                        "The contradiction resurfaces later at higher cost"],
            evidence=[f"conflicts_with: {a} ↔ {b}"],
        ))
    return findings


# --------------------------------------------------------------------------------------------------
# 2. hidden_dependency / best_practice — from the procedural-memory domain rules
# --------------------------------------------------------------------------------------------------
def _rule_findings(text: str) -> list[Finding]:
    rules_by_key = {r.key: r for r in domain.RULES}
    findings: list[Finding] = []
    for flag in domain.apply_rules([text]):
        rule = rules_by_key.get(flag.key)
        category = rule.category if rule else "hidden_dependency"
        title = (rule.title if rule and rule.title else flag.key.replace("-", " ").title())
        consequences = list(rule.consequences) if rule and rule.consequences else [
            "A late redesign to satisfy this dependency"
        ]
        findings.append(Finding(
            category=category, severity=_norm_severity(flag.severity),
            title=title, detail=flag.flag, if_ignored=consequences,
            evidence=[f"procedural-memory rule: {flag.key}", f"matched '{flag.matched}'"],
        ))
    return findings


# --------------------------------------------------------------------------------------------------
# 3. assumption / optimization — the LLM (schema-validated), heuristic fallback (offline / malformed)
# --------------------------------------------------------------------------------------------------
FINDINGS_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "severity": {"type": "string"},
                    "title": {"type": "string"},
                    "detail": {"type": "string"},
                    "if_ignored": {"type": "array", "items": {"type": "string"}},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["category", "severity", "title", "detail"],
            },
        }
    },
    "required": ["findings"],
}

# Spec probes: an under-specified but critical embedded-engineering decision the review INFERS the engineer
# is silently assuming (or could optimize). `any` = at least one trigger present; `absent` = none present.
_PROBES: tuple[dict, ...] = (
    {
        "any": ("bms", "battery", "cell", "pack", "li-ion", "lfp", "lithium"),
        "absent": ("balanc",),
        "category": "assumption", "severity": "high",
        "title": "Cell balancing strategy not specified",
        "detail": ("A battery/BMS design needs a defined cell-balancing strategy (passive vs active) and "
                   "no choice was stated — assuming passive (cost-driven). Flat-curve chemistries (e.g. LFP) "
                   "make balancing accuracy critical."),
        "if_ignored": ["Wrong balancing IC selected (missing or unneeded features)",
                       "Firmware rework when the balancing strategy changes"],
        "evidence": ["no balancing strategy in the input"],
    },
    {
        "any": ("bms", "battery", "cell", "pack", "100a", "current", "charging", "discharging"),
        "absent": ("temperatur", "thermal", "ntc", "thermistor"),
        "category": "assumption", "severity": "high",
        "title": "Temperature sensing strategy missing",
        "detail": ("A high-current battery system needs cell, MOSFET and ambient temperature monitoring; "
                   "none was specified. Minimum a few NTCs, more for production — this drives the MCU/AFE "
                   "channel count."),
        "if_ignored": ["MCU/AFE selected with insufficient ADC/temp inputs",
                       "No thermal protection → safety incident"],
        "evidence": ["no temperature-sensing plan in the input"],
    },
    {
        "any": ("bms", "battery", "ev", "pack", "state of charge", "gauge"),
        "absent": ("soc", "state of charge", "coulomb", "ekf", "kalman", "fuel gauge"),
        "category": "optimization", "severity": "medium",
        "title": "SOC estimation algorithm unspecified",
        "detail": ("No state-of-charge estimation approach is defined. Simple coulomb counting drifts; a "
                   "model-based estimator (e.g. EKF) is more accurate but needs MCU compute (FPU/SRAM)."),
        "if_ignored": ["Inaccurate fuel gauge → customer complaints",
                       "MCU selected without FPU / sufficient SRAM for a good estimator"],
        "evidence": ["no SOC estimation method in the input"],
    },
    {
        "any": ("cost", "cost-optim", "cheap", "low-cost", "low cost", "mass production", "budget"),
        "absent": (),
        "category": "optimization", "severity": "low",
        "title": "Cost optimization has hidden trade-offs",
        "detail": ("Cost optimization is a stated priority. At the component level it trades against accuracy, "
                   "thermal margin and field lifetime — make those trade-offs explicit rather than implicit."),
        "if_ignored": ["Under-spec'd parts fail in the field or at qualification",
                       "A late redesign erases the intended cost saving"],
        "evidence": ["priority: cost optimization"],
    },
)


def _heuristic_findings(text: str) -> list[Finding]:
    """Deterministic offline stand-in for the LLM findings pass. Two sources: explicit assumptions the
    extractor already pulls out of the text, plus the spec-probe table above for silently-assumed decisions."""
    findings: list[Finding] = []
    low = text.lower()

    # explicit "I assume / probably / likely …" statements → assumption findings
    for it in extraction.extract(text):
        if it["type"] != "assumption":
            continue
        findings.append(Finding(
            category="assumption", severity="medium",
            title="Unvalidated assumption in the input",
            detail=(f"You are assuming: \"{it['content']}\". A review treats this as a guess until it is "
                    f"validated — confirm it or it becomes a load-bearing risk."),
            if_ignored=["A decision rests on an unverified premise",
                        "If the premise is wrong, dependent work is rebuilt"],
            evidence=["stated as an assumption in the input"],
        ))

    # spec probes: under-specified but critical decisions
    for probe in _PROBES:
        if not any(t in low for t in probe["any"]):
            continue
        if any(a in low for a in probe["absent"]):
            continue
        findings.append(Finding(
            category=probe["category"], severity=probe["severity"], title=probe["title"],
            detail=probe["detail"], if_ignored=list(probe["if_ignored"]), evidence=list(probe["evidence"]),
        ))
    return findings


def _llm_findings(text: str, router: ModelRouter | None = None) -> list[Finding]:
    """LLM findings (assumption/optimization + anything the rules/graph missed), schema-validated. Offline
    stub or malformed output → deterministic heuristic (same pattern as extraction.extract)."""
    router = router or ModelRouter()
    try:
        out = router.execute(Capability.findings, {"text": text}, schema=FINDINGS_SCHEMA)
        raw = out.get("findings") if isinstance(out, dict) else None
        parsed: list[Finding] = []
        for f in (raw or []):
            if not isinstance(f, dict) or not f.get("title") or not f.get("detail"):
                continue
            cat = (f.get("category") or "").lower().strip()
            if cat not in CATEGORIES:
                continue
            parsed.append(Finding(
                category=cat, severity=_norm_severity(f.get("severity", "")),
                title=f["title"].strip(), detail=f["detail"].strip(),
                if_ignored=[str(x) for x in (f.get("if_ignored") or [])],
                evidence=[str(x) for x in (f.get("evidence") or [])],
            ))
        if parsed:
            return parsed
    except Exception:  # noqa: BLE001, S110 — any LLM/validation failure falls back to the heuristic below
        pass
    return _heuristic_findings(text)


# --------------------------------------------------------------------------------------------------
# merge · de-dupe · sort
# --------------------------------------------------------------------------------------------------
def _dedupe_sort(findings: list[Finding]) -> list[Finding]:
    seen: set[tuple[str, str]] = set()
    unique: list[Finding] = []
    for f in findings:
        key = (f.category, f.title.lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(f)
    unique.sort(key=lambda f: (_SEVERITY_ORDER.get(f.severity, 99), f.category, f.title))
    return unique


def review(session: Session, project_id: str, text: str,
           router: ModelRouter | None = None) -> list[Finding]:
    """Fast, no-question engineering review. Merges graph contradictions + domain-rule dependencies +
    LLM/heuristic assumptions & optimizations into one severity-sorted, de-duped list of findings."""
    text = text or ""
    findings: list[Finding] = []
    findings += _stance_contradictions(text, session, project_id)
    findings += _graph_conflict_findings(session, project_id)
    findings += _rule_findings(text)
    findings += _llm_findings(text, router)
    return _dedupe_sort(findings)
