"""Lens weighting engine (Wave 2 · Step 4).

Turns a project's spine + the specific decision topic into a **per-lens weight** that sets how deeply EDOS
reasons in each domain. This is where "importance is derived per project, not baked platform-wide" actually
happens.

    weight(lens) = base
                 + Σ spine-affinity contributions   (Layer 1: causal, from the direction fingerprint)
                 + β · topic relevance               (Layer 2: this specific decision)
                 + γ · project structural hits        (actual components/facts present)
                 + δ · learned                        (feedback — bounded ±DELTA_LEARNED, from the
                                                        `lens_feedback` store via `feedback.lens_learned_weights`)

then, applied over the raw score:
  * ENGINEER OVERRIDES win (a lens the engineer pins to a weight).
  * COVERAGE FLATTENING — with thin project context, pull weights toward the mean (don't over-commit).
  * CONSTRAINTS — BOM-availability & cost are always surfaced (a floor), never weighted away.
  * BLIND-SPOT FLOOR — every lens keeps a minimum weight; weighting sets DEPTH, never gates a concern off.

The result splits lenses into **deep** (load the full reasoning frame) vs **scan** (one-line floor), which
Step 5 assembles into the prompt. Weights are returned in full so the UI can show and let the engineer
override them.
"""
from __future__ import annotations

from dataclasses import dataclass

from edos.engines import lenses
from edos.engines.spine import SpineResult, contains_term

# --- tunable model constants (the single place to change the weighting) ---
BETA_TOPIC = 0.5          # weight of decision-topic relevance
GAMMA_STRUCTURAL = 0.3    # weight of structural component/fact presence in the project
DELTA_LEARNED = 0.10      # max contribution of the learned (outcome-feedback) term — bounded so it nudges,
#                           never dominates the principled spine/topic signal
DEEP_TOP_N = 5            # at most this many lenses go deep (full frame) — keeps the prompt bounded
DEEP_THRESHOLD = 0.55     # a lens must also clear this weight to earn a full frame
BLIND_SPOT_FLOOR = 0.08   # no lens ever drops below this — always at least a scan pass
CONSTRAINT_MIN = 0.5      # BOM/cost constraints are always at least this salient
_CONSTRAINT_LENSES = frozenset({"bom_supply", "cost"})


@dataclass
class LensWeight:
    lens_id: str
    title: str
    weight: float
    deep: bool                 # True => load the full reasoning frame; False => scan_line only
    reason: str                # why this weight (audit / UI tooltip)


def _topic_relevance(lens: lenses.Lens, topic: str) -> tuple[float, int]:
    t = topic.lower()
    hits = sum(1 for trig in lens.structural_triggers if contains_term(t, trig))
    # also credit a title-word appearing in the topic (e.g. "power", "certification")
    title_words = {w for w in lens.title.lower().replace("/", " ").split() if len(w) > 3}
    hits += sum(1 for w in title_words if contains_term(t, w))
    return min(hits / 2.0, 1.0), hits


def _structural_presence(lens: lenses.Lens, corpus: str) -> float:
    if not corpus:
        return 0.0
    c = corpus.lower()
    hits = sum(1 for trig in lens.structural_triggers if contains_term(c, trig))
    return min(hits / 3.0, 1.0)


def _spine_contrib(lens: lenses.Lens, spine: SpineResult) -> tuple[float, list[str]]:
    total, why = 0.0, []
    for axis, val in spine.values.items():
        key = f"{axis}:{val}"
        if key in lens.affinities:
            total += lens.affinities[key]
            why.append(key)
    return total, why


def weigh(
    spine: SpineResult,
    topic: str,
    *,
    project_corpus: str = "",
    coverage: float = 1.0,
    overrides: dict[str, float] | None = None,
    learned: dict[str, float] | None = None,
) -> list[LensWeight]:
    """Compute and rank lens weights for one decision. ``coverage`` is 0..1 (fraction of project context
    established); low coverage flattens the weights toward the mean. ``overrides`` maps lens_id -> a pinned
    absolute weight set by the engineer. ``learned`` maps lens_id -> an accumulated outcome-feedback score
    (from `feedback.lens_learned_weights`); it adds a bounded ±DELTA_LEARNED nudge so the emphasis self-tunes
    from what actually produced good decisions on similar-direction projects."""
    overrides = overrides or {}
    learned = learned or {}
    raw: dict[str, float] = {}
    reasons: dict[str, str] = {}

    for lens in lenses.all_lenses():
        spine_add, spine_why = _spine_contrib(lens, spine)
        topic_rel, topic_hits = _topic_relevance(lens, topic)
        struct = _structural_presence(lens, project_corpus)
        # learned term: bounded to ±DELTA_LEARNED (the raw score is clamped ±3 per key upstream).
        learn_raw = learned.get(lens.id, 0.0)
        learn_add = DELTA_LEARNED * max(-1.0, min(1.0, learn_raw / 3.0))
        score = lens.base + spine_add + BETA_TOPIC * topic_rel + GAMMA_STRUCTURAL * struct + learn_add
        raw[lens.id] = score
        bits = []
        if spine_why:
            bits.append("spine: " + ", ".join(spine_why))
        if topic_hits:
            bits.append(f"topic match ({topic_hits})")
        if struct > 0:
            bits.append("present in project")
        if abs(learn_add) >= 0.005:
            bits.append(f"learned {'+' if learn_add > 0 else ''}{learn_add:.2f}")
        reasons[lens.id] = "; ".join(bits) or "baseline"

    # Flatten toward the mean when the DIRECTION is weak — so we don't over-commit on a vague project (and the
    # framing intake asks instead). The right confidence signal is how established the SPINE is, NOT coverage%:
    # a project can have a crystal-clear direction (most axes known) at low coverage%, and its spine — derived
    # from real project text — is reliable regardless. Keying flattening on coverage alone washed out the
    # project-conditioning exactly when the spine was confident (the observed bug). Use the stronger of the two.
    total_axes = len(spine.values) + len(spine.unknown)
    spine_conf = (len(spine.values) / total_axes) if total_axes else 0.0
    confidence = max(coverage, spine_conf)
    mean = sum(raw.values()) / len(raw)
    for lid, val in list(raw.items()):
        raw[lid] = mean + confidence * (val - mean)

    # engineer overrides win outright.
    for lid, w in overrides.items():
        if lid in raw:
            raw[lid] = w
            reasons[lid] = "engineer override"

    # constraints are always at least CONSTRAINT_MIN; blind-spot floor applies to everything.
    for lid, val in list(raw.items()):
        if lid in _CONSTRAINT_LENSES:
            val = max(val, CONSTRAINT_MIN)
        raw[lid] = max(val, BLIND_SPOT_FLOOR)

    ranked = sorted(raw.items(), key=lambda kv: kv[1], reverse=True)

    # depth selection: top-N that also clear the threshold AND actually have a frame to go deep with.
    deep_ids: set[str] = set()
    for lid, w in ranked:
        if len(deep_ids) >= DEEP_TOP_N:
            break
        lens = lenses.get_lens(lid)
        if w >= DEEP_THRESHOLD and lens and lens.frame_file:
            deep_ids.add(lid)

    out: list[LensWeight] = []
    for lid, w in ranked:
        lens = lenses.get_lens(lid)
        out.append(LensWeight(
            lens_id=lid, title=lens.title if lens else lid,
            weight=round(w, 3), deep=lid in deep_ids, reason=reasons[lid],
        ))
    return out
