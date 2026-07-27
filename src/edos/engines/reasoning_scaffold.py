"""Reasoning scaffold assembly (Wave 2 · Step 5).

Composes the project's spine + the per-decision lens weights + the lens reasoning-frames into the single
text block that gets injected into the Deep Dive prompt. This is where the static ERC brain becomes a
**project-conditioned, embedded-native** reasoning prompt: the same question on two different projects
produces a different scaffold, because the spine and weights differ.

Structure of the injected block:
    ## PROJECT DIRECTION (spine)      — the derived fingerprint (and what's still unknown)
    ## REASON WITH THESE LENSES       — DEEP lenses (full frame) then SCAN lenses (one-line blind-spot floor)

Everything here is best-effort: if the project has no context yet, the spine is empty, coverage is 0, and
weights flatten — the scaffold still renders (thin), never errors.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from edos.engines import lens_weighting, lenses, spine


def _project_corpus(session: Session, project_id: str) -> str:
    try:
        from sqlalchemy import select

        from edos.db.models import ProjectItem
        rows = session.scalars(
            select(ProjectItem.content).where(ProjectItem.project_id == project_id)
        ).all()
        return "\n".join(r for r in rows if r)
    except Exception:  # noqa: BLE001
        return ""


def _coverage_fraction(session: Session, project_id: str) -> float:
    try:
        from edos.engines.coverage import coverage_report
        return coverage_report(session, project_id)["overall"] / 100.0
    except Exception:  # noqa: BLE001
        return 1.0  # unknown coverage => don't artificially flatten


def _learned_weights(session: Session, fingerprint) -> dict:
    """Outcome-feedback nudge per lens for this project's direction. Best-effort — {} if nothing learned yet
    (or the feedback table isn't present), so the scaffold never depends on it."""
    try:
        from edos.engines.feedback import lens_learned_weights
        return lens_learned_weights(session, fingerprint)
    except Exception:  # noqa: BLE001
        return {}


def build_scaffold(
    session: Session,
    project_id: str,
    topic: str,
    *,
    overrides: dict[str, float] | None = None,
) -> dict:
    """Return {spine_lines, weights, deep, scan, text}. ``text`` is the block for the prompt; the rest is
    structured so the API/UI can show the fingerprint and let the engineer override weights."""
    corpus = _project_corpus(session, project_id)
    fingerprint = spine.classify(corpus)
    coverage = _coverage_fraction(session, project_id)
    learned = _learned_weights(session, fingerprint)  # F2: self-tuning nudge from past outcomes
    weights = lens_weighting.weigh(
        fingerprint, topic, project_corpus=corpus, coverage=coverage,
        overrides=overrides, learned=learned,
    )

    deep, scan = [], []
    for w in weights:
        lens = lenses.get_lens(w.lens_id)
        if not lens:
            continue
        if w.deep:
            frame = lens.load_frame()
            if frame:
                deep.append({"id": w.lens_id, "title": w.title, "frame": frame, "weight": w.weight})
                continue
        scan.append({"id": w.lens_id, "title": w.title, "scan_line": lens.scan_line, "weight": w.weight})

    text = _render_text(fingerprint.as_prompt_lines(), deep, scan)
    return {
        "spine_lines": fingerprint.as_prompt_lines(),
        "weights": [w.__dict__ for w in weights],
        "deep": deep,
        "scan": scan,
        "text": text,
    }


def _render_text(spine_lines: list[str], deep: list[dict], scan: list[dict]) -> str:
    parts: list[str] = []
    parts.append("## PROJECT DIRECTION (spine — derived from this project's context)")
    parts.append("\n".join(f"- {ln}" for ln in spine_lines) if spine_lines
                 else "- (no project context yet — reason generally and ask what's missing)")
    parts.append("")
    parts.append("## REASON WITH THESE LENSES (weighted for THIS project and THIS decision)")
    if deep:
        parts.append("### Reason through these thoroughly (load-bearing for this decision):")
        for d in deep:
            parts.append(d["frame"])
            parts.append("")
    if scan:
        parts.append("### Also scan these for blind spots — stay brief, but do not skip:")
        for s in scan:
            parts.append(f"- **{s['title']}** — {s['scan_line']}")
    return "\n".join(parts).strip()
