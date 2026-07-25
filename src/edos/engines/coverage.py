"""Coverage engine (UI-CP-2) — *how complete the project's engineering context is*, 0-100%.

Coverage replaces the old "confidence" number. It is **not a fabricated score**: it is a transparent,
tunable function of what is actually in the project. An empty project is 0% coverage and still fully usable;
the number just tells the engineer "add these to get a more grounded result."

Each of the 6 engineering domains earns coverage from three inputs (backlog "Coverage model" spec):

    domain_coverage = clamp01( W_ITEMS * min(items / TARGET_ITEMS, 1)
                             + W_DOCS  * min(docs  / TARGET_DOCS,  1)
                             + W_QUESTIONS * (answered / total_questions) )

  * items     = # domain-tagged context items (requirements/decisions/constraints), excluding documents
  * docs      = # domain-tagged documents/datasheets (item_type == "document")
  * answered  = # of that domain's question-set questions the engineer has answered

Overall coverage = weighted mean of the 6 domain coverages (weights default to equal, tunable).

All weights and targets are module constants — the single place to tune the model. They are deliberately not
persisted config yet (that is a later ticket); documenting them here keeps the formula auditable.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from edos.db.models import CoverageAnswer, ProjectItem

# The 6 engineering domains (order == PDF Project-Brain grid order).
DOMAINS: list[str] = [
    "Architecture", "Hardware", "Firmware", "Manufacturing", "Testing", "Certification",
]

# ---- tunable model constants (the only place to change the formula) ----
W_ITEMS = 0.40       # weight of tagged context items
W_DOCS = 0.20        # weight of attached documents/datasheets
W_QUESTIONS = 0.40   # weight of answered question-set questions  (W_ITEMS + W_DOCS + W_QUESTIONS == 1.0)
TARGET_ITEMS = 5     # # of tagged items that saturates the items term
TARGET_DOCS = 2      # # of documents that saturates the docs term

# Per-domain weight in the overall mean (equal by default; tunable per domain).
DOMAIN_WEIGHTS: dict[str, float] = {d: 1.0 for d in DOMAINS}

# ---- domain question-set: ~3-5 general engineering questions per domain ----
QUESTION_SETS: dict[str, list[dict[str, str]]] = {
    "Architecture": [
        {"id": "arch-blocks", "q": "What are the top-level functional blocks and their responsibilities?"},
        {"id": "arch-interfaces", "q": "What are the key interfaces/protocols between the major blocks?"},
        {"id": "arch-constraints", "q": "What are the hard system constraints (power, size, cost, latency)?"},
        {"id": "arch-tradeoffs", "q": "What is the primary architectural trade-off being made and why?"},
    ],
    "Hardware": [
        {"id": "hw-power", "q": "What is the power budget and supply/regulation topology?"},
        {"id": "hw-components", "q": "What are the critical components and their key datasheet ratings?"},
        {"id": "hw-thermal", "q": "What are the thermal/environmental limits the hardware must survive?"},
        {"id": "hw-connectors", "q": "What are the external connectors, pinouts and signal levels?"},
    ],
    "Firmware": [
        {"id": "fw-mcu", "q": "What is the target MCU/SoC and its clocking/memory constraints?"},
        {"id": "fw-rtos", "q": "Is there an RTOS/scheduler, and what are the real-time deadlines?"},
        {"id": "fw-comms", "q": "What communication stacks/protocols does the firmware implement?"},
        {"id": "fw-update", "q": "How are firmware updates and recovery/bootloader handled?"},
    ],
    "Manufacturing": [
        {"id": "mfg-volume", "q": "What is the target production volume and cost-per-unit ceiling?"},
        {"id": "mfg-process", "q": "What assembly/process steps and tooling are required?"},
        {"id": "mfg-supply", "q": "What are the supply-chain/long-lead or single-source risks?"},
        {"id": "mfg-yield", "q": "What are the expected yield and rework assumptions?"},
    ],
    "Testing": [
        {"id": "test-accept", "q": "What are the acceptance criteria and pass/fail thresholds?"},
        {"id": "test-coverage", "q": "What test types (unit, HIL, environmental) cover the design?"},
        {"id": "test-equipment", "q": "What test equipment/fixtures are needed?"},
        {"id": "test-fault", "q": "What fault-injection / failure-mode tests are planned?"},
    ],
    "Certification": [
        {"id": "cert-standards", "q": "Which standards/regulations apply (EMC, safety, regional)?"},
        {"id": "cert-regions", "q": "What target markets/regions drive certification scope?"},
        {"id": "cert-evidence", "q": "What test evidence/documentation must be produced for each standard?"},
        {"id": "cert-timeline", "q": "What is the certification lead time and its schedule impact?"},
    ],
}


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def question_set(domain: str) -> list[dict[str, str]]:
    return QUESTION_SETS.get(domain, [])


def answered_ids(session: Session, project_id: str, domain: str) -> set[str]:
    rows = session.scalars(
        select(CoverageAnswer.question_id).where(
            CoverageAnswer.project_id == project_id, CoverageAnswer.domain == domain
        )
    ).all()
    return set(rows)


def _domain_counts(session: Session, project_id: str) -> dict[str, dict[str, int]]:
    """Per-domain (items, docs) counts from the project's tagged items."""
    rows = session.execute(
        select(ProjectItem.domain, ProjectItem.item_type).where(
            ProjectItem.project_id == project_id, ProjectItem.domain.is_not(None)
        )
    ).all()
    counts = {d: {"items": 0, "docs": 0} for d in DOMAINS}
    for domain, item_type in rows:
        if domain not in counts:
            continue
        if item_type == "document":
            counts[domain]["docs"] += 1
        else:
            counts[domain]["items"] += 1
    return counts


def _domain_coverage(items: int, docs: int, answered: int, total_questions: int) -> float:
    q_term = (answered / total_questions) if total_questions else 0.0
    raw = (
        W_ITEMS * min(items / TARGET_ITEMS, 1.0)
        + W_DOCS * min(docs / TARGET_DOCS, 1.0)
        + W_QUESTIONS * q_term
    )
    return _clamp01(raw)


def coverage_report(session: Session, project_id: str) -> dict:
    """Compute overall + per-domain coverage (0-100, rounded) plus the raw inputs/unanswered questions.

    Returns:
        {
          "overall": int,
          "by_domain": {Domain: int, ...},
          "detail": {Domain: {"coverage": int, "items": n, "docs": n,
                              "answered": [ids], "unanswered": [{id,q}, ...], "total_questions": n}}
        }
    """
    counts = _domain_counts(session, project_id)
    by_domain: dict[str, int] = {}
    detail: dict[str, dict] = {}
    weighted_sum = 0.0
    weight_total = 0.0

    for d in DOMAINS:
        qs = question_set(d)
        answered = answered_ids(session, project_id, d)
        items, docs = counts[d]["items"], counts[d]["docs"]
        cov = _domain_coverage(items, docs, len(answered), len(qs))
        pct = round(cov * 100)
        by_domain[d] = pct
        detail[d] = {
            "coverage": pct,
            "items": items,
            "docs": docs,
            "answered": sorted(answered),
            "unanswered": [q for q in qs if q["id"] not in answered],
            "total_questions": len(qs),
        }
        w = DOMAIN_WEIGHTS.get(d, 1.0)
        weighted_sum += cov * w
        weight_total += w

    overall = round((weighted_sum / weight_total) * 100) if weight_total else 0
    return {"overall": overall, "by_domain": by_domain, "detail": detail}
