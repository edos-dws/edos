"""Project Timeline / Replay (UI-CP-10, PDF p23).

A day-by-day rail of what actually happened in the project, assembled **deterministically** (no LLM) from the
persisted, timestamped rows:

  * decision versions (``DecisionRecord``) — v1 = "decision created", v>1 = "decision updated";
  * first-class assumptions (``Assumption``) — a "created" event, plus (when the status has advanced past
    ``created``) a status-change event at ``updated_at`` carrying the *current* status;
  * project items (``ProjectItem``) — documents/datasheets, coverage answers, and other saved context;
  * decision outcomes (``DecisionOutcome``) — accepted / challenged / reversed.

Events are ordered by ``created_at``. Each event is ``{when, kind, label, coverage?}``.

**Coverage on the rail — honestly reconstructed, never fabricated.** Coverage is a pure, monotone function of
append-only, timestamped rows (domain-tagged items + answered questions), with static formula constants and no
in-place mutation of items. That makes ``coverage_report(as_of=when)`` an *exact* reconstruction of the
coverage as it stood at each event — not a guess. We attach that snapshot to events (and it grows
monotonically, matching the PDF's "coverage climbs as context is added"). The **latest** event always carries
the current overall coverage. Where a timestamp is missing we omit ``coverage`` rather than invent one.

This engine holds no reasoning — it only projects persisted state onto a rail (one responsibility, CLAUDE.md).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from edos.db.models import Assumption, DecisionOutcome, DecisionRecord, ProjectItem
from edos.engines import coverage

# item_type → the timeline kind + a human verb for the label
_DOC_TYPES: frozenset[str] = frozenset({"document"})


def _iso(when: dt.datetime | None) -> str | None:
    return when.isoformat() if when else None


def _item_event(it: ProjectItem) -> dict:
    """Classify a project item into a timeline event (document / coverage answer / saved context)."""
    content = (it.content or "").strip()
    snippet = content.replace("\n", " ")
    if len(snippet) > 90:
        snippet = snippet[:89] + "…"
    if it.item_type in _DOC_TYPES:
        tag = f" [{it.domain}]" if it.domain else ""
        return {"kind": "document", "label": f"Source/datasheet added{tag}: {snippet}"}
    if it.domain and content.startswith("Q:"):
        return {"kind": "coverage", "label": f"Coverage answer [{it.domain}]: {snippet}"}
    return {"kind": "context", "label": f"Context saved ({it.item_type}): {snippet}"}


def build(session: Session, project_id: str) -> dict:
    """Assemble the ordered timeline for a project. Deterministic; coverage per-event is reconstructed
    honestly via ``coverage_report(as_of=...)``. Returns ``{project_id, events:[...], coverage_now}``."""
    events: list[dict] = []

    # ---- decisions (every version is an event) ----
    for row in session.scalars(
        select(DecisionRecord).where(DecisionRecord.project_id == project_id)
    ):
        verb = "created" if row.version == 1 else f"updated → v{row.version}"
        events.append({
            "when": row.created_at, "kind": "decision",
            "label": f"Decision {verb} [{row.id}]: {row.title} ({row.status})",
            "ref": row.id,
        })

    # ---- first-class assumptions (created + last status change) ----
    for a in session.scalars(select(Assumption).where(Assumption.project_id == project_id)):
        events.append({
            "when": a.created_at, "kind": "assumption",
            "label": f"Assumption {a.id} created: {a.statement}", "ref": a.id,
        })
        if a.status != "created" and a.updated_at and a.updated_at != a.created_at:
            events.append({
                "when": a.updated_at, "kind": "assumption_status",
                "label": f"Assumption {a.id} → {a.status}: {a.statement}", "ref": a.id,
            })

    # ---- project items (documents / coverage answers / saved context) ----
    for it in session.scalars(select(ProjectItem).where(ProjectItem.project_id == project_id)):
        ev = _item_event(it)
        events.append({"when": it.created_at, **ev, "ref": it.id})

    # ---- decision outcomes (accepted / challenged / reversed) ----
    outcome_ids = {
        r.id for r in session.scalars(
            select(DecisionRecord).where(DecisionRecord.project_id == project_id)
        )
    }
    for o in session.scalars(select(DecisionOutcome)):
        if o.decision_id not in outcome_ids:
            continue
        events.append({
            "when": o.created_at, "kind": "outcome",
            "label": f"Decision {o.decision_id} outcome: {o.outcome}", "ref": o.decision_id,
        })

    # ---- order by time (stable on kind for same-instant ties) ----
    events.sort(key=lambda e: (e["when"] or dt.datetime.min.replace(tzinfo=dt.UTC), e["kind"]))

    # ---- honest per-event coverage snapshot (monotone; exact reconstruction) ----
    for e in events:
        when = e.pop("when")
        e["when"] = _iso(when)
        if when is not None:
            e["coverage"] = coverage.coverage_report(session, project_id, as_of=when)["overall"]
    # the latest event always carries the CURRENT overall coverage (per UI-CP-10 spec). Snapshots are taken
    # at each event's exact instant, so a coverage answer whose bookkeeping row lands microseconds after its
    # context item can leave the last as_of snapshot a hair behind "now" — pin the latest event to current.
    coverage_now = coverage.coverage_report(session, project_id)["overall"]
    if events and "coverage" in events[-1]:
        events[-1]["coverage"] = coverage_now
    return {"project_id": project_id, "events": events, "coverage_now": coverage_now}
