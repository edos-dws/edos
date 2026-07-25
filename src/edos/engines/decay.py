"""Assumption Decay Alert — the background re-check (UI-CP-8, PDF p21).

"The moment a prompt could never reach." A reactive Q&A only answers what you ask *now*; nothing re-opens a
decision you made weeks ago. This pass does: some time after a decision, a background scan re-checks its
still-active assumptions against the *current* decision graph and surfaces two things a human would otherwise
miss —

  (a) **aged assumptions** still unvalidated past ``age_days`` → they need re-validation; and
  (b) a **cross-decision contradiction caught in the background** — e.g. an "A12 forced-air cooling"
      assumption vs a later "IP67 sealed enclosure" requirement. EDOS catches it automatically because both
      decisions live in the *same* graph, so a ``conflicts_with`` edge between them (already surfaced by the
      watchdog / ``graph_view.contradictions``) becomes a high-severity decay alert that also names the
      participating assumption ("A12 → invalidate").

This engine holds no reasoning and never touches a live LLM — it *composes* the first-class assumption ledger
(:mod:`edos.engines.assumptions`) with :func:`edos.engines.graph_view.contradictions` and reuses the
watchdog's :class:`~edos.engines.watchdog.Alert` shape. ``now`` is an **injectable** parameter so the
``age_days`` aging trigger is fully deterministic in tests (back-date ``created_at`` + pass ``now`` — never
the real wall-clock). Nothing here is fabricated: an alert exists only because a row is genuinely old or a
``conflicts_with`` edge genuinely exists.
"""
from __future__ import annotations

import datetime as dt
import os

from sqlalchemy.orm import Session

from edos.engines import assumptions as assumptions_engine
from edos.engines import graph_view
from edos.engines.watchdog import Alert

# lifecycle statuses that still need a verdict — an assumption already validated/challenged/invalidated has
# been looked at, so it does not decay silently and is not re-flagged for age.
_UNVALIDATED: frozenset[str] = frozenset({"created"})

DEFAULT_AGE_DAYS = 30
NTFY_TOPIC = "edos-dws-build-notify"


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _aware(t: dt.datetime | None) -> dt.datetime | None:
    """Normalise a datetime to timezone-aware UTC so comparisons never mix naive/aware."""
    if t is None:
        return None
    return t if t.tzinfo is not None else t.replace(tzinfo=dt.UTC)


def decay_scan(
    session: Session, project_id: str, *, now: dt.datetime | None = None, age_days: int = DEFAULT_AGE_DAYS
) -> list[Alert]:
    """Run the background decay pass for a project.

    ``now`` is injectable (defaults to real UTC only outside tests) so the ``age_days`` window is
    deterministic; ``age_days`` is the re-validation horizon (30 in the PDF). Returns a list of
    :class:`~edos.engines.watchdog.Alert` — ``assumption_decay`` (aged, medium) and
    ``cross_decision_contradiction`` (high, or **critical** when a first-class assumption participates)."""
    now = _aware(now) or _utcnow()
    cutoff = now - dt.timedelta(days=age_days)

    rows = assumptions_engine.list_for_project(session, project_id)
    # map a decision id → the assumptions sourced from it, so a decision-vs-decision conflict can name the
    # assumption that now becomes invalid ("A12 forced-air cooling" participating via its source decision).
    by_source: dict[str, list] = {}
    for a in rows:
        if a.source_decision_id:
            by_source.setdefault(a.source_decision_id, []).append(a)

    alerts: list[Alert] = []

    # (a) aged, still-unvalidated assumptions → need re-validation
    for a in rows:
        if a.status not in _UNVALIDATED:
            continue
        created = _aware(a.created_at)
        if created is None or created > cutoff:
            continue  # younger than the horizon — not yet due
        age = (now - created).days
        alerts.append(Alert(
            "assumption_decay", a.id,
            f"assumption {a.id} needs re-validation (age {age} days) — “{a.statement}” has been "
            f"unvalidated for over {age_days} days; re-confirm it against the current design.",
            "medium",
        ))

    # (b) cross-decision contradictions caught in the background
    for c in graph_view.contradictions(session, project_id):
        # an assumption "participates" if it IS one endpoint, or if it is sourced from one of the two
        # conflicting decisions (its ground has now been contradicted elsewhere in the graph).
        participants: list[str] = []
        for end_id, end_type in ((c["a"], c["a_type"]), (c["b"], c["b_type"])):
            if end_type == "assumption":
                participants.append(end_id)
            for a in by_source.get(end_id, []):
                if a.id not in participants:
                    participants.append(a.id)
        if participants:
            tail = (f" — assumption {', '.join(participants)} is grounded in one side and should be "
                    f"re-validated / invalidated.")
            severity = "critical"
        else:
            tail = ""
            severity = "high"
        alerts.append(Alert(
            "cross_decision_contradiction", f"{c['a']}↔{c['b']}",
            f"Background review caught a cross-decision contradiction: “{c['a_label']}” "
            f"({c['a_type']} {c['a']}) conflicts with “{c['b_label']}” ({c['b_type']} {c['b']}) — both "
            f"live in the same decision graph and cannot both hold.{tail}",
            severity,
        ))
    return alerts


def notify_critical_contradiction(alerts: list[Alert], *, enabled: bool | None = None) -> bool:
    """Best-effort phone push (ntfy) when a decay scan surfaces a **critical** cross-decision contradiction.

    Wrapped so failure is non-fatal and it **never runs in tests**: it is a no-op unless explicitly opted in
    via ``EDOS_DECAY_NOTIFY=1`` (a deployed background worker would set it) and always short-circuits under
    pytest. Returns whether a push was attempted. Network errors are swallowed — the build never blocks on it.
    """
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False  # never fire during the test suite
    if enabled is None:
        enabled = os.environ.get("EDOS_DECAY_NOTIFY") == "1"
    if not enabled:
        return False  # TODO: enable in the scheduled background worker once a channel is provisioned
    crit = [a for a in alerts if a.severity == "critical" and a.type == "cross_decision_contradiction"]
    if not crit:
        return False
    try:  # pragma: no cover — network side-effect, exercised only by the live worker
        import urllib.request

        body = (f"{len(crit)} critical cross-decision contradiction(s) caught in background review "
                f"(assumption decay).").encode()
        req = urllib.request.Request(
            f"https://ntfy.sh/{NTFY_TOPIC}", data=body,
            headers={"Title": "EDOS Decay Alert", "Tags": "warning"},
        )
        urllib.request.urlopen(req, timeout=3)
        return True
    except Exception:  # noqa: BLE001 — best-effort; a failed push must never break the scan
        return False
