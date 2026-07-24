"""Proactive watchdog (CP-20) — surface what the engineer would miss.

Reactive Q&A answers what you ask; the watchdog scans the project and flags what you didn't: open conflicts,
items gone stale/superseded, and decisions that depend on now-invalid items. This is the "trust now" payoff
of temporal validity (CP-12): when new knowledge invalidates old, the affected decisions get an alert.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from edos.db.models import GraphEdge, ProjectItem
from edos.models.entities import RelationType


@dataclass
class Alert:
    type: str
    subject: str
    message: str
    severity: str


def scan(session: Session, project_id: str) -> list[Alert]:
    items = list(session.scalars(select(ProjectItem).where(ProjectItem.project_id == project_id)))
    by_id = {it.id: it for it in items}
    alerts: list[Alert] = []

    # 1. open conflicts (validity flagged)
    for it in items:
        if it.validity == "conflicted":
            alerts.append(Alert("open_conflict", it.id,
                                f"'{it.id}' is in an unresolved conflict — resolve before relying on it.", "high"))
        elif it.validity in ("stale", "superseded"):
            alerts.append(Alert("stale_item", it.id,
                                f"'{it.id}' is {it.validity}; retrieval will down-rank it.", "medium"))

    # 2. edges pointing at now-invalid nodes (a decision depending on a superseded item)
    edges = session.scalars(
        select(GraphEdge).where(
            GraphEdge.relation_type.in_([RelationType.depends_on.value, RelationType.references.value]),
            GraphEdge.validity == "active",
        )
    ).all()
    for e in edges:
        src, tgt = by_id.get(e.source_id), by_id.get(e.target_id)
        if src is None or tgt is None:
            continue
        if tgt.validity in ("superseded", "stale", "conflicted"):
            alerts.append(Alert("invalidated_dependency", e.source_id,
                                f"'{e.source_id}' {e.relation_type} '{e.target_id}', which is now "
                                f"{tgt.validity} — re-check this decision.", "high"))
    return alerts
