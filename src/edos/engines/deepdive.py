"""Deep Dive → Decision Card (UI-CP-4).

Deep Dive is the **opposite of Engineering Review**: instead of a fast no-question scan, it asks 5-8
*targeted* questions — each with a "WHY AM I ASKING?" rationale — then, once the engineer answers, it
produces a rich **Decision Card**.

Stages (UI-CP-11 makes questioning **context-grounded + adaptive**):

  1. ``plan_questions(session, project_id, topic)`` → ``{questions, skipped, note}`` — retrieve the project's
     graph/knowledge FIRST, generate candidate questions (LLM primary, static probes fallback), then **skip
     any question whose concern is already established in the retrieved context** (semantic match via the
     embedder, lexically grounded so the low-dim stub can't fabricate a skip). ``skipped`` powers the
     "already known" hint; ``note`` is set only when the project already covers everything.
  1b. ``follow_up(session, project_id, topic, answers)`` → ``[{id, q, why}]`` — after the batch answers,
     emit **0–2** targeted follow-ups: ALWAYS a deterministic graph/decision-contradiction check (reuses
     ``findings`` stance logic), PLUS an LLM judgment (live only; stub→heuristic returns none) up to the
     remaining budget. Total capped at 2; empty = ready to decide.
  2. ``decide(session, project_id, topic, answers)`` → ``(Decision, decision_detail)`` where:
       * ``Decision`` is a **contract-valid** ``edos.decision.v1`` (summary / recommendation / confidence /
         status / assumptions / risks / evidence / …) — reasoned over retriever context + the answers;
       * ``decision_detail`` is the rich card block kept in the **persistence envelope**, NOT the locked
         contract: ``{comparison_matrix, recommendation, decision_impact, impacted_components,
         review_conditions, dependencies, related_decisions, missing}``.

Both stages go through the Model Router with a JSON schema and fall back to a deterministic heuristic exactly
like ``extraction.py`` / ``findings.py`` — so the suite is deterministic offline (stub provider) and uses the
real model live. The heuristic never fabricates datasheet numbers: options/criteria are derived from the
topic + answers + retrieved project context, so the card is honest offline and richer live.
"""
from __future__ import annotations

import re
import uuid

from sqlalchemy.orm import Session

from edos.engines import decision_store, findings, ingestion, retrieval
from edos.engines.embeddings import EmbeddingProvider, default_embedder
from edos.engines.model_router import Capability, ModelRouter, Tier
from edos.models.decision import Decision


def _persist_answers(session: Session, project_id: str, answers: list[dict]) -> None:
    """Save the engineer's deep-dive answers as project context (facts/requirements) so they ground this and
    future reasoning — the answers are context, not assumptions.

    We store the QUESTION alongside its answer (``Q: … — A: …``) so that skip-known (which matches on the
    question's wording) recognises an already-answered question next time and never re-asks it (see Q1)."""
    for a in answers or []:
        ans = (a.get("answer") or "").strip()
        if not ans:
            continue
        q = (a.get("q") or "").strip()
        content = f"[deep-dive Q&A] Q: {q} — A: {ans}" if q else f"[deep-dive answer] {ans}"
        try:
            ingestion.ingest_item(session, id=f"dda-{uuid.uuid4().hex[:10]}", project_id=project_id,
                                  item_type="requirement", content=content)
        except Exception:  # noqa: BLE001, S110 — persisting context is best-effort; never blocks a decision
            pass

# ---- the six engineering areas a decision can ripple into (Decision Impact grid) ----
_IMPACT_AREAS = ("Firmware", "Hardware", "Architecture", "Power stage", "Manufacturing", "Certification")

# keyword → impacted component (transparent, tunable; never fabricated part numbers)
_COMPONENT_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("MCU", ("mcu", "microcontroller", "stm32", "soc", "processor")),
    ("AFE", ("afe", "cell monitor", "monitoring ic", "bms ic", "analog front")),
    ("Firmware", ("firmware", "driver", "algorithm", "control loop", "software")),
    ("PCB", ("pcb", "board", "layout", "routing")),
    ("BOM", ("bom", "cost", "budget", "component", "part")),
    ("Power stage", ("mosfet", "fet", "gate driver", "power stage", "shunt", "current sens")),
    ("Thermal", ("thermal", "cooling", "heatsink", "temperature", "heat")),
    ("Comms", ("can", "isospi", "spi", "i2c", "uart", "wireless", "ble", "lora")),
)


# The engineer's *answers* are facts that become project context and reasoning input — they are NOT
# assumptions. Assumptions are what the SYSTEM had to infer/guess to reach the recommendation (the gaps it
# filled), each with a real "risk if wrong". These keyword-driven probes generate honest system assumptions
# from the topic/context — never an echo of the answers.
_ASSUMPTION_PROBES: tuple[dict, ...] = (
    {"any": ("balanc", "cell", "lfp", "pack", "soc", "14s"),
     "statement": "End-of-life cell spread stays within the recommended balancing current's budget",
     "risk": "If the spread exceeds it, passive balancing is insufficient and active balancing (more "
             "cost/EMI/firmware) becomes mandatory."},
    {"any": ("cost", "volume", "bom", "mass production", "cheap", "price"),
     "statement": "Production volume is high enough that the recommended part's unit pricing holds",
     "risk": "At lower volume the cost advantage erodes and a cheaper alternative may win instead."},
    {"any": ("mcu", "soc", "processor", "stm32", "aurix", "controller"),
     "statement": "The chosen MCU/SoC's peripherals and qualification meet the requirement without an add-on",
     "risk": "A missing peripheral or qualification forces an MCU change and a firmware port."},
    {"any": ("afe", "cell monitor", "adc", "sensing", "accuracy", "measurement"),
     "statement": "The chosen front-end's measurement accuracy is sufficient without an external precision AFE",
     "risk": "Insufficient accuracy adds an external AFE — extra BOM and PCB area."},
    {"any": ("thermal", "cool", "power", "current", "mosfet", "enclosure", "100a"),
     "statement": "The assumed thermal/cooling envelope is available in the final enclosure",
     "risk": "A sealed or derated enclosure invalidates the thermal budget and forces a power-stage re-derate."},
    {"any": ("cert", "iso", "asil", "automotive", "standard", "compliance"),
     "statement": "The target certification scope is as stated and won't expand mid-program",
     "risk": "A stricter or added standard reshapes the architecture late, at high cost."},
)


def _system_assumptions(topic: str, answers: list[dict], context: list[str], detail: dict) -> list[dict]:
    """The premises the recommendation *rests on* that the answers did NOT establish — i.e. what the system
    inferred to decide. Never the engineer's answers (those are facts/context)."""
    blob = " ".join([topic, *[a.get("answer", "") for a in answers if a.get("answer")], *context]).lower()
    out: list[dict] = []
    for probe in _ASSUMPTION_PROBES:
        if any(t in blob for t in probe["any"]):
            out.append({"statement": probe["statement"], "confidence": 0.55, "risk_if_wrong": probe["risk"]})
    missing = detail.get("missing")
    if missing:
        out.append({"statement": f"Reasonable engineering defaults were assumed for unspecified: {missing}",
                    "confidence": 0.5,
                    "risk_if_wrong": "If those defaults differ from reality, the recommendation may change."})
    if not out:
        out.append({"statement": "Standard engineering priorities (safety > reliability > cost) apply",
                    "confidence": 0.5,
                    "risk_if_wrong": "A different priority order changes how the options are weighted."})
    return out[:6]


# ==================================================================================================
# stage 1 — question plan (LLM → heuristic)
# ==================================================================================================
QUESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "q": {"type": "string"},
                    "why": {"type": "string"},
                },
                "required": ["q", "why"],
            },
        }
    },
    "required": ["questions"],
}

# Deterministic offline probes: each is a targeted engineering question that applies when a trigger keyword is
# present (or as a general fallback). The "why" is a real rationale — what the answer changes downstream.
_QUESTION_PROBES: tuple[dict, ...] = (
    {"any": ("current", "100a", "power", "mosfet", "charge", "discharge", "load"),
     "q": "Peak current rating? (inrush, regen braking, fault stall)",
     "why": ("Parts sized for continuous current fail under 2-3x peak transients if not derated. The peak "
             "and its duration set the FET/copper count and the protection threshold.")},
    {"any": ("balanc", "cell", "pack", "14s", "lfp", "li-ion", "soc", "battery"),
     "q": "Maximum acceptable cell imbalance at end of life?",
     "why": ("Cells age apart; end-of-life spread decides whether passive balancing current is enough or "
             "active balancing (more cost/EMI/firmware) is required.")},
    {"any": ("cool", "thermal", "heat", "enclosure", "power", "mosfet", "dissipat"),
     "q": "Cooling method and ambient/enclosure conditions?",
     "why": ("Dissipation vs cooling sets the continuous rating, PCB copper, and enclosure design. Sealed "
             "vs forced-air changes the whole thermal budget.")},
    {"any": ("protect", "fault", "safety", "short", "overcurrent", "fuse"),
     "q": "Fault-response time budget and protection layer (hardware vs software)?",
     "why": ("Software-only protection is ~100us+ — too slow for a hard short. Sub-10us needs a hardware "
             "comparator. This decides whether a dedicated protection IC is on the BOM.")},
    {"any": ("cost", "budget", "volume", "mass production", "bom", "cheap"),
     "q": "Target unit cost at volume and the production volume?",
     "why": ("Cost targets trade against accuracy, thermal margin and field life. Volume decides whether "
             "NRE (custom silicon, tooling) amortizes or a catalog part wins.")},
    {"any": ("cert", "standard", "iso", "automotive", "asil", "compliance", "regulat"),
     "q": "Which certification / safety standard must this meet?",
     "why": ("Automotive (ISO 26262 ASIL), medical, or industrial each impose redundancy, traceability and "
             "component-qualification requirements that reshape the architecture — cheaper to design in now.")},
    {"any": ("comm", "can", "isospi", "spi", "interface", "bus", "protocol", "wireless"),
     "q": "Communication interface and its noise/isolation environment?",
     "why": ("The bus (isoSPI/CAN/SPI) and whether it crosses a noisy/high-voltage boundary decide isolation, "
             "shielding and connector count — and the firmware driver work.")},
    {"any": ("expand", "future", "scal", "roadmap", "next", "modular", "platform"),
     "q": "Future expansion / scaling plan for this subsystem?",
     "why": ("Designing only for today's spec forces a redesign when the pack/feature scales. Knowing the "
             "expansion path lets one architecture cover both without over-building now.")},
)

# General-purpose questions used to top up to a minimum of 5 when few probes fire.
_GENERIC_QUESTIONS: tuple[dict, ...] = (
    {"q": "What are the hard constraints (size, weight, cost, power) that cannot move?",
     "why": ("Hard constraints eliminate whole option branches up front — reasoning without them risks "
             "recommending something that was never viable.")},
    {"q": "What is the single most important priority — safety, cost, performance, or time-to-market?",
     "why": ("The ranked priority is the tiebreaker in the comparison matrix; without it the recommendation "
             "is just an opinion.")},
    {"q": "What is the expected operating environment (temperature, vibration, EMI, ingress)?",
     "why": ("Environment sets derating, sealing and component qualification — it often decides the option "
             "more than the nominal spec does.")},
    {"q": "Are there existing decisions or components this must stay compatible with?",
     "why": ("A locally-optimal choice can contradict an earlier decision; surfacing dependencies now avoids "
             "a cross-decision conflict later.")},
)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:24] or "q"


def _heuristic_questions(topic: str) -> list[dict]:
    """Only the probes the topic actually triggers (need-driven), capped at 5. A vague topic that triggers
    nothing still gets a few essentials so the engineer isn't left with zero — but 5 is the ceiling, never a
    forced quota."""
    low = (topic or "").lower()
    picked: list[dict] = [
        {"q": probe["q"], "why": probe["why"]}
        for probe in _QUESTION_PROBES if any(t in low for t in probe["any"])
    ]
    if not picked:  # nothing specific matched → a few generic essentials, not a full five
        picked = [dict(g) for g in _GENERIC_QUESTIONS[:3]]
    picked = picked[:5]
    return [{"id": f"q{i + 1}-{_slug(p['q'])}", "q": p["q"], "why": p["why"]}
            for i, p in enumerate(picked)]


def _candidate_questions(
    topic: str, context: list[str] | None = None, router: ModelRouter | None = None,
) -> tuple[list[dict], str]:
    """Generate the candidate question set. Returns (questions, source) where source is "llm" (topic-specific
    LLM output) or "heuristic" (the static probe fallback — used offline OR when the live LLM errors, e.g. a
    quota/429). The source lets the UI tell the engineer when questions are degraded, not silently static."""
    router = router or ModelRouter()
    try:
        # Question generation is a LIGHT task — route it to the cheap Lite chain so the good model's limited
        # quota is preserved for the heavy decision reasoning (which uses the frontier chain, see `decide`).
        # Pass the project context so the model can skip what the project already establishes (the prompt
        # instructs it to), making the questions project-aware rather than topic-blind.
        out = router.execute(Capability.deepdive,
                             {"mode": "questions", "topic": topic, "context": context or []},
                             schema=QUESTIONS_SCHEMA, tier=Tier.lightweight)
        raw = out.get("questions") if isinstance(out, dict) else None
        if raw is not None:  # the call succeeded and returned the schema — honour the model's count (0-5)
            parsed = [
                {"id": f"q{i + 1}-{_slug(q['q'])}", "q": q["q"].strip(), "why": q["why"].strip()}
                for i, q in enumerate(raw)
                if isinstance(q, dict) and q.get("q") and q.get("why")
            ]
            return parsed[:5], "llm"  # 5 is the hard max; fewer (even zero) is fine when that's enough
    except Exception:  # noqa: BLE001, S110 — any LLM/validation failure falls back to the heuristic
        pass
    return _heuristic_questions(topic), "heuristic"


# --------------------------------------------------------------------------------------------------
# skip-known: drop a candidate question whose concern is already established in the project context.
# --------------------------------------------------------------------------------------------------
# Semantic match via the embedder, but the low-dim stub embedder collides (unrelated 8-d vectors score
# 0.4-0.8), so a lexically-grounded blend is used: 0.7·lexical + 0.3·embedder-cosine. The embedder can only
# add up to 0.3, so it never fabricates a skip on its own (keeps offline honest) — it lifts a genuine
# semantic match over the line (so it is "semantic, not just keywords"). A real embedder live drives the
# same score meaningfully. Threshold tuned so a question and its answer skip while sibling questions don't.
_SKIP_KNOWN_THRESHOLD = 0.5
_SKIP_STOPWORDS: frozenset[str] = frozenset({
    "a", "an", "the", "and", "or", "of", "at", "to", "in", "for", "is", "are", "be", "this", "that",
    "it", "its", "what", "which", "how", "not", "on", "with", "your", "you", "must", "meet", "does", "do",
})
_SKIP_WORD = re.compile(r"[a-z0-9]+")


def _concept_tokens(text: str) -> set[str]:
    return {w for w in _SKIP_WORD.findall((text or "").lower())
            if w not in _SKIP_STOPWORDS and len(w) > 2}


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine of two embedder vectors (already L2-normalized → dot product)."""
    return sum(x * y for x, y in zip(a, b, strict=False))


def _coverage_score(question: str, content: str, embedder: EmbeddingProvider) -> float:
    qt = _concept_tokens(question)
    lex = len(qt & _concept_tokens(content)) / len(qt) if qt else 0.0
    cos = _cosine(embedder.embed(question), embedder.embed(content))
    return 0.7 * lex + 0.3 * cos


def _retrieved_context(session: Session, project_id: str, topic: str) -> list[str]:
    """The project's already-established knowledge for this topic (retriever content strings)."""
    ctx: list[str] = []
    try:
        for c in retrieval.retrieve(session, project_id=project_id, question=topic):
            if c["signals"]["semantic"] >= 0.2 or c["signals"]["graph"] >= 0.2:
                ctx.append(c["content"])
    except Exception:  # noqa: BLE001, S110 — retrieval is best-effort context; never blocks questioning
        pass
    return ctx


def _covered_by(question: str, context: list[str], embedder: EmbeddingProvider) -> str | None:
    """Return the context item that already covers this question's concern (best match ≥ threshold), else
    None."""
    best_content, best_score = None, 0.0
    for content in context:
        score = _coverage_score(question, content, embedder)
        if score >= _SKIP_KNOWN_THRESHOLD and score > best_score:
            best_content, best_score = content, score
    return best_content


def plan_questions(
    session: Session, project_id: str, topic: str, router: ModelRouter | None = None,
) -> dict:
    """Context-grounded deep-dive questions (UI-CP-11).

    Retrieve the project's knowledge for ``topic`` FIRST, generate candidate questions (LLM primary, static
    probes fallback), then **skip any question whose concern is already established in that context**. Returns
    ``{questions:[{id,q,why}], skipped:[{q,reason}], note}`` — ``skipped`` powers the "already known" hint;
    ``note`` is non-empty only when the project already covers every question."""
    embedder = default_embedder()
    context = _retrieved_context(session, project_id, topic)
    candidates, generated_by = _candidate_questions(topic, context, router)

    kept: list[dict] = []
    skipped: list[dict] = []
    for q in candidates:
        match = _covered_by(q["q"], context, embedder) if context else None
        if match is not None:
            reason = f'already established in project context: "{match[:120]}"'
            skipped.append({"q": q["q"], "reason": reason})
        else:
            kept.append(q)
    kept = kept[:5]  # 5 is the hard maximum shown to the engineer

    note = ""
    if not kept:
        note = ("Nothing critical left to ask — I have enough context on this topic. Confirm my understanding "
                "below and I'll go straight to a decision.")
    # `generated_by`: "llm" = topic-specific model questions; "heuristic" = static fallback (LLM offline or
    # quota-limited) — the UI surfaces this so static questions are never mistaken for the model's output.
    return {"questions": kept, "skipped": skipped, "note": note, "generated_by": generated_by,
            "understanding": _understanding(topic, context)}


def plan_frame(session: Session, project_id: str, topic: str) -> dict:
    """Reasoning-first FRAME (Wave 3 · Step 6): what EDOS reflects back *before* deciding, so the card is the
    closing move, not the opening one. Returns the project's direction fingerprint, the lenses it will weigh
    (shown + overridable), and the framing questions for any direction it can't yet establish (ask, never
    guess). Purely advisory — best-effort, never blocks the existing decide path.

    Returns ``{topic, understanding, spine:[lines], framing_questions:[{axis,q}], lenses:[{...}]}``."""
    try:
        from edos.engines import spine as _spine
        from edos.engines.reasoning_scaffold import build_scaffold

        scaffold = build_scaffold(session, project_id, topic)
        fingerprint = _spine.classify_project(session, project_id)
        return {
            "topic": topic,
            "understanding": _understanding(topic, _retrieved_context(session, project_id, topic)),
            "spine": scaffold["spine_lines"],
            "framing_questions": _spine.framing_questions(fingerprint),
            "lenses": [
                {"id": w["lens_id"], "title": w["title"], "weight": w["weight"],
                 "deep": w["deep"], "reason": w["reason"]}
                for w in scaffold["weights"]
            ],
        }
    except Exception:  # noqa: BLE001 — the frame is an enhancement; degrade to a minimal shape, never 500
        return {"topic": topic, "understanding": _understanding(topic, []),
                "spine": [], "framing_questions": [], "lenses": []}


def _understanding(topic: str, context: list[str]) -> str:
    """A one-line restatement of what EDOS takes the decision to be — shown for confirmation when no questions
    are needed (Q2's zero-question path). Honest: it echoes the topic and how much project context grounds it."""
    t = (topic or "").strip() or "this decision"
    if context:
        n = len(context)
        noun = "thing" if n == 1 else "things"
        return f"You're deciding: {t}. I'm grounding this in {n} {noun} this project already knows."
    return f"You're deciding: {t}. I'll reason from standard engineering priorities where specifics aren't given."


# ==================================================================================================
# stage 1b — adaptive follow-up (deterministic contradiction check + LLM judgment; cap 2)
# ==================================================================================================
FOLLOWUP_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"q": {"type": "string"}, "why": {"type": "string"}},
                "required": ["q", "why"],
            },
        }
    },
    "required": ["questions"],
}
_FOLLOWUP_CAP = 2


def _deterministic_followups(session: Session, project_id: str, answers: list[dict]) -> list[dict]:
    """ALWAYS-run check: does any answer contradict a stored decision / the project graph? Reuses the
    ``findings`` stance-contradiction logic (answer text vs stored decisions). Each conflict → a follow-up
    that names it."""
    blob = " ".join(a.get("answer", "") for a in (answers or []) if a.get("answer")).strip()
    if not blob:
        return []
    out: list[dict] = []
    for f in findings._stance_contradictions(blob, session, project_id):
        out.append({
            "id": f"fu-{_slug(f.title)}",
            "q": (f"{f.title} — your answer takes a different stance than a stored decision. Which one "
                  "governs going forward, and how do you reconcile the conflict?"),
            "why": f.detail,
        })
    return out


def _heuristic_followups(topic: str, answers: list[dict]) -> list[dict]:
    """Offline stand-in for the LLM follow-up pass. A follow-up must be *warranted* by a real signal; the
    deterministic contradiction check supplies those, so offline this fabricates nothing → no follow-ups."""
    return []


def _llm_followups(
    session: Session, project_id: str, topic: str, answers: list[dict], limit: int,
    router: ModelRouter | None = None,
) -> list[dict]:
    """LLM judgment (live): up to ``limit`` follow-ups a principal engineer would ask given the answers.
    Stub / malformed output → heuristic (which returns none offline)."""
    if limit <= 0:
        return []
    router = router or ModelRouter()
    context = _retrieved_context(session, project_id, topic)
    try:
        out = router.execute(
            Capability.deepdive,
            {"mode": "followup", "topic": topic, "answers": answers, "context": context},
            schema=FOLLOWUP_SCHEMA,
            tier=Tier.lightweight,  # follow-up generation is light → cheap chain
        )
        raw = out.get("questions") if isinstance(out, dict) else None
        parsed = [
            {"id": f"fu-{_slug(q['q'])}", "q": q["q"].strip(), "why": q["why"].strip()}
            for q in (raw or [])
            if isinstance(q, dict) and q.get("q") and q.get("why")
        ]
        if parsed:
            return parsed[:limit]
    except Exception:  # noqa: BLE001, S110 — any LLM/validation failure falls back to the heuristic
        pass
    return _heuristic_followups(topic, answers)[:limit]


def follow_up(
    session: Session, project_id: str, topic: str, answers: list[dict],
    router: ModelRouter | None = None,
) -> list[dict]:
    """0–2 targeted follow-ups AFTER the batch answers. Deterministic contradiction check ALWAYS runs; the
    LLM judgment fills the remaining budget (live only; offline returns nothing). Total capped at 2 — empty
    means the engineer is ready to decide."""
    answers = answers or []
    det = _deterministic_followups(session, project_id, answers)[:_FOLLOWUP_CAP]
    llm = _llm_followups(session, project_id, topic, answers, _FOLLOWUP_CAP - len(det), router)
    out: list[dict] = []
    seen: set[str] = set()
    for f in det + llm:
        if f["id"] in seen:
            continue
        seen.add(f["id"])
        out.append(f)
    return out[:_FOLLOWUP_CAP]


# ==================================================================================================
# stage 2 — the Decision Card (LLM → heuristic)
# ==================================================================================================
def _related_decisions_context(session: Session, project_id: str, topic: str, limit: int = 3) -> list[str]:
    """GraphRAG: pull the project's PRIOR DECISIONS (graph nodes) most related to this topic and feed them —
    with the premises they rest on — INTO the decision context (before reasoning, not attached after). This is
    EDOS's edge over vector-only RAG: the new decision is reasoned for **consistency with past decisions**, so
    a contradiction surfaces instead of being made silently. Prior decisions live in the decision store, not
    in ProjectItem retrieval, so they'd otherwise never reach the model."""
    try:
        rows = decision_store.list_for_project(session, project_id)[:10]  # bound the embed calls
    except Exception:  # noqa: BLE001
        return []
    if not rows:
        return []
    embedder = default_embedder()
    tvec = embedder.embed(topic)
    scored: list[tuple[float, object]] = []
    for row in rows:
        # Full-body relevance (Feature 4): rank on title + rationale, not the title alone — a decision whose
        # title is generic ("power supply") but whose rationale is on-topic should still be pulled in.
        body = f"{row.title or ''} {row.rationale or ''}".strip()
        sim = _cosine(tvec, embedder.embed(body)) if body else 0.0
        scored.append((sim, row))
    scored.sort(key=lambda x: -x[0])
    out: list[str] = []
    for sim, row in scored[:limit]:
        if sim < 0.35:  # only genuinely-related prior decisions (avoid noise from unrelated ones)
            continue
        try:
            dec = decision_store.to_decision(row)
        except Exception:  # noqa: BLE001, S112 — a malformed stored row is skipped, not fatal
            continue
        premises = "; ".join(a.statement for a in (dec.assumptions or [])[:2]) or "n/a"
        out.append(f"[PRIOR DECISION {row.id}] {dec.summary} — assumes: {premises}")
    return out


def _gather_context(
    session: Session, project_id: str, topic: str, answers: list[dict],
) -> tuple[list[str], list[str]]:
    """The assembled context package for the decision: rank → rerank → top-K → labeled-with-provenance →
    capped (via the Context Engine), PLUS related prior decisions (GraphRAG) and the engineer's answers.

    Returns `(context_strings, used_item_ids)` — the item ids feed the #7 feedback loop (a decision's outcome
    later boosts/penalises exactly the items that fed it)."""
    ctx: list[str] = []
    item_ids: list[str] = []
    try:
        for c in retrieval.select_context(session, project_id=project_id, query=topic):
            ctx.append(f"[{retrieval.label_for(c['type'])}] {c['content'].strip()}")
            item_ids.append(c["ref_id"])
    except Exception:  # noqa: BLE001, S110 — retrieval is best-effort context; never blocks a decision
        pass
    try:
        ctx += _related_decisions_context(session, project_id, topic)  # GraphRAG: prior decisions
    except Exception:  # noqa: BLE001, S110 — best-effort; never blocks a decision
        pass
    ctx += [f"[ANSWER] {a['answer']}" for a in answers if a.get("answer")]
    return ctx, item_ids


def _reasoning_scaffold(session: Session, project_id: str, topic: str) -> dict:
    """The project-conditioned reasoning scaffold (spine + weighted lenses) for a decision. Returns
    ``{"text","spine","lenses"}`` — ``text`` goes into the prompt; ``spine``/``lenses`` are attached to the
    decision detail so the UI can show (and later override) what EDOS weighted. Best-effort: any failure
    returns an empty scaffold so the decision still runs on the ERC brain + retrieved context alone."""
    try:
        from edos.engines.reasoning_scaffold import build_scaffold
        s = build_scaffold(session, project_id, topic)
        return {"text": s["text"], "spine": s["spine_lines"], "lenses": s["weights"]}
    except Exception:  # noqa: BLE001 — scaffold is an enhancement; never blocks a decision
        return {"text": "", "spine": [], "lenses": []}


def _verify_computations(computations: object) -> list:
    """#8: recompute the model's own arithmetic deterministically so a computed number carries a real ✓ (and a
    wrong one is caught). Best-effort — any failure returns [] and never blocks the decision."""
    try:
        from edos.engines.checks import verify_computations
        return verify_computations(computations)
    except Exception:  # noqa: BLE001
        return []


def _auto_compute(context: list[str]) -> list:
    """#8 (auto-compute half): EDOS computes a budget ITSELF from quantities stated in the project context —
    thermal ΔT and battery life, only when the inputs are unambiguous. Best-effort → [] on any failure."""
    try:
        from edos.engines.checks import auto_compute
        return auto_compute(context)
    except Exception:  # noqa: BLE001
        return []


_STOP_EDGE = {"a", "an", "the", "for", "of", "to", "in", "on", "with", "and", "using", "based", "its"}


def _short_phrase(text: str, *, tail: bool) -> str:
    """A concise 1-3 word option name from the side of a comparison nearest the separator. Focuses on the
    clause closest to the "vs": after the last dash/colon on the left ("… strategy — passive" → "Passive"),
    before the first comma on the right ("Hall-effect sensing, cheap" → "Hall-effect Sensing")."""
    seg = text or ""
    seg = re.split(r"[—–:]", seg)[-1] if tail else re.split(r"[,—–:]", seg)[0]
    words = [w.strip(".,;:()") for w in seg.split() if w.strip(".,;:()")]
    if not words:
        return ""
    # Walk inward from the separator, collecting up to 3 words, and STOP at the first interior filler word
    # ("… bare-metal for safety-critical" → "Bare-metal", not "Bare-metal For Safety-critical").
    ordered = list(reversed(words)) if tail else words
    picked: list[str] = []
    for w in ordered:
        if w.lower() in _STOP_EDGE:
            if picked:
                break
            continue  # skip leading filler
        picked.append(w)
        if len(picked) >= 3:
            break
    if tail:
        picked.reverse()
    return " ".join(picked).strip().title()


def _options_from_topic(topic: str) -> list[str]:
    """Real candidate option names from an explicit "A vs B" / "A or B" topic. Returns ``[]`` when the topic
    is NOT an explicit comparison — we never fabricate generic "Baseline/Alternative" options, and never a
    fake "Hybrid" third column. No options → the card simply shows no comparison matrix (honest over padded)."""
    raw = (topic or "").strip()
    low = raw.lower()
    for sep in (" vs. ", " vs ", " versus ", " or "):
        idx = low.find(sep)
        if idx != -1:
            a = _short_phrase(raw[:idx], tail=True)
            b = _short_phrase(raw[idx + len(sep):], tail=False)
            if a and b and a.lower() != b.lower():
                return [a, b]
    return []


def _impacted_components(text: str) -> list[str]:
    low = text.lower()
    hits = [name for name, kws in _COMPONENT_KEYWORDS if any(k in low for k in kws)]
    # stable de-dupe, sensible default
    seen: list[str] = []
    for h in hits:
        if h not in seen:
            seen.append(h)
    return seen or ["Firmware", "Hardware", "BOM"]


# What actually changes downstream for each impacted area (so Decision Impact reads specific, not a fixed list).
_IMPACT_CHANGE: dict[str, str] = {
    "Firmware": "Drivers and control-loop work track the chosen option",
    "Hardware": "Component selection and PCB layout depend on this choice",
    "BOM": "Bill-of-materials cost and sourcing shift with this option",
    "Power stage": "Thermal and protection budget is derived from this decision",
    "Architecture": "Sets an interface other subsystems build against",
    "Mechanical": "Enclosure and thermal path are constrained by this choice",
    "Testing": "The validation / bench-test plan must cover the chosen option",
    "Certification": "Applicable standards and the certification path follow from this",
}


def _impact_change(name: str) -> str:
    return _IMPACT_CHANGE.get(name, f"{name} design decisions follow from this choice")


# Context-triggered risk rules — only the ones whose keywords actually appear are raised, so the risk list is
# specific to THIS decision and varies in count/content (never a fixed three-row template).
_RISK_RULES: list[tuple[tuple[str, ...], str, str, str]] = [
    (("safety", "asil", "iso 26262", "sil", "functional safety", "hazard"),
     ("The functional-safety evidence for this choice isn't established yet — a wrong pick propagates into "
      "the whole safety case"), "high",
     "Confirm the safety requirement and the diagnostic coverage it needs before committing"),
    (("thermal", "temperature", "junction", "dissipation", "cooling", "ambient", "heat"),
     ("Thermal headroom at worst-case ambient isn't proven — it can pass on the bench and fail in a sealed "
      "enclosure"), "high",
     "Validate with thermal measurements at the real worst-case ambient"),
    (("emc", "emi", "noise", "interference", "snr", "cispr"),
     "EMC / noise behaviour of the chosen option isn't characterised", "medium",
     "Run a pre-compliance scan before the layout freeze"),
    (("cost", "bom", "volume", "price", "unit", "usd", "$"),
     "Unit cost at the target volume assumes pricing that may not hold — the BOM math can move the decision",
     "medium", "Re-check pricing at the actual production volume and MOQ"),
    (("supply", "availability", "lead time", "sourcing", "stock", "second source"),
     "Part availability / lead-time risk on the chosen option", "medium",
     "Confirm sourcing and qualify a second source"),
    (("accuracy", "drift", "calibration", "resolution", "tolerance", "precision"),
     "Long-term drift and accuracy over temperature and aging aren't established", "medium",
     "Characterise drift across the full operating range"),
    (("latency", "real-time", "real time", "deadline", "isr", "jitter", "khz"),
     "Worst-case timing / latency margin under full load isn't proven", "high",
     "Measure worst-case latency with all interrupts and tasks active"),
]


def _derive_risks(topic: str, answers: list[dict], context: list[str], chosen: str) -> list[dict]:
    """Risks specific to THIS decision — matched from what the engineer described. Variable count, never a
    fixed template. Only rules whose keywords appear are raised; a peak/fault-envelope risk is added only
    when the engineer hasn't already pinned worst-case down."""
    blob = " ".join([topic, *[a.get("answer", "") for a in answers if a.get("answer")], *context]).lower()
    risks: list[dict] = []
    for kws, desc, sev, mit in _RISK_RULES:
        if any(k in blob for k in kws):
            risks.append({"description": desc, "severity": sev, "likelihood": "medium", "mitigation": mit})
    if not any(k in blob for k in ("worst-case", "worst case", "peak", "surge", "inrush", "fault", "margin")):
        risks.append({
            "description": "Worst-case / peak operating conditions are under-specified, so the recommendation "
                           "may not hold at the extremes",
            "severity": "high", "likelihood": "medium",
            "mitigation": "Confirm the peak / fault envelope with measurements"})
    if not risks:
        who = chosen or "the recommended option"
        risks.append({
            "description": f"The core operating assumptions behind {who} aren't yet validated against real data",
            "severity": "medium", "likelihood": "medium",
            "mitigation": "Validate the core assumptions before committing"})
    return risks[:4]


# Comparison-matrix axes, keyed by what the engineer actually described. Each entry is
# (label, trigger-keywords, (recommended_value, alternative_value, hybrid_value)). We select the axes whose
# keywords appear in the topic/answers/context so the matrix ROWS are specific to THIS decision — not a fixed
# five-row template that reads identically across every report. Values stay qualitative (never a fabricated
# datasheet number), but the axis set is derived, so no two unrelated decisions get the same matrix.
_CRITERIA_AXES: list[tuple[str, tuple[str, ...], tuple[str, str, str]]] = [
    ("Accuracy / precision", ("accuracy", "precision", "resolution", "drift", "tolerance", "error", "% soc",
                              "measurement"), ("Meets spec", "Higher headroom", "Balanced")),
    ("Timing / latency", ("latency", "deadline", "real-time", "real time", "response time", "khz", "hz",
                          "sampling", "throughput", "jitter", "isr", "loop"), ("Meets deadline",
                          "More margin", "Balanced")),
    ("Cost / BOM", ("cost", "bom", "price", "budget", "cheap", "usd", "$", "volume", "unit"),
                   ("Lower", "Higher", "Medium")),
    ("Power / efficiency", ("power", "efficiency", "consumption", "battery", "watt", "draw", "quiescent"),
                           ("Lower draw", "Higher draw", "Medium")),
    ("Thermal", ("thermal", "temperature", "heat", "dissipation", "cooling", "junction"),
                ("Lower rise", "Higher rise", "Medium")),
    ("Safety / compliance", ("safety", "asil", "iso 26262", "iec", "sil", "certification", "functional safety",
                             "ul ", "ce ", "compliance"), ("Meets standard", "Exceeds", "Meets standard")),
    ("Size / footprint", ("size", "footprint", "area", "space", "compact", "form factor", "pcb"),
                         ("Smaller", "Larger", "Medium")),
    ("EMC / noise", ("emc", "emi", "noise", "interference", "snr", "shielding"),
                    ("Lower noise", "Higher noise", "Medium")),
    ("Reliability / lifetime", ("reliability", "mtbf", "lifetime", "cycle", "durability", "robust", "wear"),
                               ("Adequate", "Higher", "Balanced")),
    ("Supply / availability", ("supply", "availability", "lead time", "sourcing", "stock", "second source"),
                              ("Better", "Constrained", "Medium")),
]
# Fallback axes used ONLY to top a sparse comparison up to a usable minimum. Deliberately no "Cost" here —
# cost/performance axes appear only when the decision actually mentions them (via _CRITERIA_AXES), so we never
# show a cost row for a decision that isn't about cost.
_DEFAULT_AXES: list[tuple[str, tuple[str, str, str]]] = [
    ("Complexity / integration", ("Lower", "Higher", "Medium")),
    ("Risk", ("Lower", "Higher", "Medium")),
    ("Time to integrate", ("Faster", "Slower", "Medium")),
]


def _derive_criteria(blob: str) -> list[tuple[str, tuple[str, str, str]]]:
    """Pick the comparison axes THIS decision is actually about (keyword match), else sensible defaults.
    Returns 3-5 `(label, (rec_val, alt_val, hybrid_val))` axes, deterministic and topic-specific."""
    low = blob.lower()
    picked: list[tuple[str, tuple[str, str, str]]] = [
        (label, vals) for label, kws, vals in _CRITERIA_AXES if any(k in low for k in kws)
    ]
    # Only top up when the decision gave us too few axes to compare on (<3) — never pad a rich set with
    # generic rows, and never force a cost row onto a decision that isn't about cost.
    i = 0
    while len(picked) < 3 and i < len(_DEFAULT_AXES):
        label, vals = _DEFAULT_AXES[i]
        i += 1
        if all(label.split(" /")[0].lower() not in p[0].lower() for p in picked):
            picked.append((label, vals))
    return picked[:5]


def _heuristic_detail(topic: str, answers: list[dict], context: list[str]) -> dict:
    """Deterministic Decision-Card detail from topic + answers + context. No fabricated datasheet values —
    options are derived from the topic and the matrix axes from what the engineer actually described."""
    options = _options_from_topic(topic)
    answer_texts = [a.get("answer", "") for a in answers if a.get("answer")]
    blob = " ".join([topic, *answer_texts, *context])

    # criteria: derived from what THIS decision is about (topic + answers), not a fixed template set
    axes = _derive_criteria(blob)
    criteria = [label for label, _ in axes]
    # A comparison matrix is built ONLY when the topic is an explicit A-vs-B — otherwise we do not fabricate
    # options/values, and the card simply carries no matrix (the frontend hides it).
    matrix_options: list[dict] = []
    if len(options) >= 2:
        for i, name in enumerate(options):
            matrix_options.append({
                "name": name,
                "values": [triple[min(i, 2)] for _, triple in axes],
                "recommended": (i == 0),
            })
    chosen = options[0] if options else ""

    reasons: list[str] = []
    if chosen:
        reasons.append(f"Best fits the constraints stated for '{topic.strip() or 'this decision'}'")
    if matrix_options:
        reasons.append(f"Leads on {', '.join(criteria[:3]).lower()} versus {options[1]}")
    if answer_texts:
        reasons.append(f"Grounded in the engineer's answer: \"{answer_texts[0][:90]}\"")
    if not reasons:
        reasons = [f"Reasoned from the available context for '{topic.strip() or 'this decision'}'"]
    recommendation = {
        "chosen": chosen,
        "reasons": reasons,
        "eliminated": [
            {"option": o["name"],
             "reason": f"Weaker on {criteria[0].lower() if criteria else 'the stated priorities'} "
                       f"for the current spec"}
            for o in matrix_options[1:]
        ],
    }

    # decision impact — derived from the components this decision ACTUALLY touches (not a fixed four rows)
    impacted = _impacted_components(blob)
    decision_impact = [{"area": c, "change": _impact_change(c)} for c in impacted[:4]]

    # review conditions — only the ones whose trigger isn't already pinned down by the context
    review_conditions = []
    if not any(k in blob.lower() for k in ("priority", "priorit")):
        review_conditions.append(f"Revisit if the priority for '{topic.strip() or 'this'}' changes")
    if not any(k in blob.lower() for k in ("worst-case", "worst case", "peak", "fault", "margin")):
        review_conditions.append("Revisit if peak/worst-case operating conditions exceed the assumed envelope")
    if any(k in blob.lower() for k in ("cost", "bom", "volume", "price")):
        review_conditions.append("Revisit if the production volume or cost target moves materially")
    if not review_conditions:
        review_conditions.append("Revisit if the core requirements behind this decision change")

    missing = _missing_context(blob, answers)

    # runner-up (Step 7 parity in the degraded path): when there is a real A-vs-B matrix, name the #2 option
    # it beat and why — derived from the matrix the heuristic already built, so no value is fabricated. This
    # keeps a degraded (LLM-offline) card structurally complete rather than silently poorer than the contract.
    # blind_spots stay the LLM's job — the heuristic must not invent specific, quantified failure modes.
    runner_up = None
    if len(matrix_options) >= 2:
        runner_up = {
            "option": matrix_options[1]["name"],
            "gap": "moderate",  # honest default — the heuristic can't gauge the margin precisely
            "tipped_by": [
                f"Recommended option leads on {criteria[0].lower()}" if criteria
                else "Better fit to the stated constraints",
            ],
        }

    return {
        "topic": topic,
        "comparison_matrix": {"criteria": criteria, "options": matrix_options},
        "recommendation": recommendation,
        "runner_up": runner_up,
        "decision_impact": decision_impact,
        "impacted_components": _impacted_components(blob),
        "review_conditions": review_conditions,
        "dependencies": context[:4],
        "related_decisions": [],
        "missing": missing,
    }


def _missing_context(blob: str, answers: list[dict]) -> str:
    low = blob.lower()
    gaps = []
    if not any(k in low for k in ("cycle", "lifetime", "life", "hours")):
        gaps.append("field lifetime / cycle target")
    if not any(k in low for k in ("test", "measured", "validated", "prototype")):
        gaps.append("bench/thermal test data")
    if not answers:
        gaps.append("answers to the deep-dive questions")
    return ", ".join(gaps[:2]) if gaps else ""


def _heuristic_decision(topic: str, answers: list[dict], context: list[str], detail: dict) -> Decision:
    """Build a contract-valid `Decision` from the derived detail. Status caps at `recommended`."""
    rec = detail["recommendation"]
    chosen = rec["chosen"]
    answer_texts = [a.get("answer", "") for a in answers if a.get("answer")]

    # Assumptions = what the SYSTEM inferred to decide (gaps), NOT the engineer's answers.
    assumptions = _system_assumptions(topic, answers, context, detail)

    # Risks specific to THIS decision (variable count/content), not a fixed three-row template.
    risks = _derive_risks(topic, answers, context, chosen)

    tradeoffs = [
        {"option": o["name"],
         "benefit": "Recommended: best fit for the stated constraints" if o["recommended"]
                    else "Higher headroom",
         "drawback": "Meets-spec, not over-provisioned" if o["recommended"]
                     else "More cost / complexity than the spec justifies"}
        for o in detail["comparison_matrix"]["options"]
    ]

    evidence = [{"claim": f"Recommendation weighs {len(context)} project-context item(s) plus "
                          f"{len(answer_texts)} deep-dive answer(s)",
                 "source": "deep-dive", "kind": "inference"}]
    # The engineer's answers are FACTS the reasoning is grounded in (evidence), not assumptions.
    for t in answer_texts[:3]:
        evidence.append({"claim": t[:180], "source": "engineer-answer", "kind": "fact"})

    confidence = round(min(0.9, 0.55 + 0.05 * len(answer_texts) + 0.03 * len(context)), 2)

    topic_clean = topic.strip() or "Deep dive"
    summary = f"{topic_clean} — recommend {chosen}" if chosen else topic_clean
    recommendation = (f"Recommend {chosen}. " + "; ".join(rec["reasons"][:3])) if chosen \
        else "; ".join(rec["reasons"][:3])

    return Decision(
        summary=summary,
        recommendation=recommendation,
        confidence=confidence,
        status="recommended",
        assumptions=assumptions,
        risks=risks,
        tradeoffs=tradeoffs,
        evidence=evidence,
        next_actions=[(f"Proceed with {chosen}" if chosen else "Proceed with the recommendation"),
                      "Close the missing context: " + (detail.get("missing") or "n/a")],
    )


DECISION_CARD_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "recommendation": {"type": "string"},
        "confidence": {"type": "number"},
        "assumptions": {"type": "array"},
        "risks": {"type": "array"},
        # Kept intentionally loose (items not constrained): the LLM sometimes labels fields its own way, and
        # `_card_from_llm` coerces them onto the strict contract. A tight schema here would reject that output
        # at validation time and silently drop the rich card to the heuristic — the opposite of what we want.
        "tradeoffs": {"type": "array"},
        "next_actions": {"type": "array"},
        "detail": {
            "type": "object",
            "properties": {
                "comparison_matrix": {"type": "object"},
                "decision_impact": {"type": "array"},
                "impacted_components": {"type": "array"},
                "review_conditions": {"type": "array"},
            },
            "required": ["comparison_matrix", "decision_impact", "impacted_components", "review_conditions"],
        },
    },
    "required": ["summary", "recommendation", "confidence", "detail"],
}


def decide(
    session: Session, project_id: str, topic: str, answers: list[dict],
    router: ModelRouter | None = None,
) -> tuple[Decision, dict]:
    """Run reasoning over (retriever context + answers) → (contract-valid Decision, decision_detail).

    LLM first (schema-validated), deterministic heuristic fallback offline / on malformed output."""
    router = router or ModelRouter()
    answers = answers or []
    _persist_answers(session, project_id, answers)  # answers → project context (not assumptions)
    context, context_item_ids = _gather_context(session, project_id, topic, answers)
    scaffold = _reasoning_scaffold(session, project_id, topic)  # spine + project-weighted lenses
    reasoning_frame = {"spine": scaffold["spine"], "lenses": scaffold["lenses"]}  # for the UI (overridable)
    # #8 auto-compute: give the model EDOS's own deterministically-computed budgets so it reasons WITH verified
    # numbers, not estimates. Same facts are re-verified and shown on the card (below). Best-effort.
    _auto_facts = _auto_compute(context)
    if _auto_facts:
        context = context + ["[COMPUTED BY EDOS — trust over any estimate] " + "; ".join(
            f"{c['quantity']} = {c['result']} (= {c['expression']})" for c in _auto_facts)]

    try:
        out = router.execute(
            Capability.deepdive,
            {"mode": "decide", "topic": topic, "answers": answers, "context": context,
             "reasoning_scaffold": scaffold["text"]},
            schema=DECISION_CARD_SCHEMA,
            tier=Tier.frontier,  # decision reasoning is the HEAVY task → route to the best (frontier) chain
        )
        built = _card_from_llm(session, project_id, topic, context, out)
        if built is not None:
            built[1]["context_item_ids"] = context_item_ids  # #7: remember which items fed this decision
            built[1]["reasoning_frame"] = reasoning_frame     # spine + weighted lenses used (audit/UI)
            # #8: verify the model's arithmetic AND fold in EDOS's own auto-computed budgets (thermal/battery)
            _comps = (built[1].get("computations") or []) + _auto_compute(context)
            built[1]["computations"] = _verify_computations(_comps)
            return built
    except Exception:  # noqa: BLE001, S110 — any LLM/validation failure falls back to the heuristic below
        pass

    detail = _heuristic_detail(topic, answers, context)
    detail["context_item_ids"] = context_item_ids  # #7: remember which items fed this decision
    detail["reasoning_frame"] = reasoning_frame     # spine + weighted lenses used (audit/UI)
    decision = _heuristic_decision(topic, answers, context, detail)
    _link_related(session, project_id, detail)
    return decision, detail


# The LLM often labels fields its own way (assumptions as {value, risk_if_wrong}; risks as {name, severity,
# description}). The Decision contract is strict (extra="forbid", required confidence/likelihood), so an
# un-coerced payload raises ValidationError and the rich card is silently lost to the heuristic. These
# coercers map the common shapes onto the contract so the model's real output actually reaches the user.
_SEVERITIES = {"low", "medium", "high", "critical"}
_LIKELIHOODS = {"low", "medium", "high"}


def _coerce_assumptions(raw: object) -> list[dict]:
    out: list[dict] = []
    for a in raw or []:
        if isinstance(a, str):
            out.append({"statement": a, "confidence": 0.5})
            continue
        if not isinstance(a, dict):
            continue
        stmt = a.get("statement") or a.get("value") or a.get("assumption")
        if not stmt:
            continue
        try:
            conf = min(1.0, max(0.0, float(a.get("confidence"))))
        except (TypeError, ValueError):
            conf = 0.5
        item = {"statement": str(stmt), "confidence": conf}
        if a.get("risk_if_wrong"):
            item["risk_if_wrong"] = str(a["risk_if_wrong"])
        out.append(item)
    return out


def _coerce_risks(raw: object) -> list[dict]:
    out: list[dict] = []
    for r in raw or []:
        if isinstance(r, str):
            out.append({"description": r, "severity": "medium", "likelihood": "medium"})
            continue
        if not isinstance(r, dict):
            continue
        desc = r.get("description") or r.get("risk") or r.get("name")
        if not desc:
            continue
        sev = str(r.get("severity", "medium")).lower()
        lik = str(r.get("likelihood", "medium")).lower()
        item = {"description": str(desc),
                "severity": sev if sev in _SEVERITIES else "medium",
                "likelihood": lik if lik in _LIKELIHOODS else "medium"}
        if r.get("mitigation"):
            item["mitigation"] = str(r["mitigation"])
        out.append(item)
    return out


def _coerce_tradeoffs(raw: object) -> list[dict]:
    out: list[dict] = []
    for t in raw or []:
        if isinstance(t, dict) and t.get("option"):
            out.append({"option": str(t["option"]), "benefit": str(t.get("benefit", "")),
                        "drawback": str(t.get("drawback", ""))})
    return out


def _coerce_evidence(raw: object) -> list[dict]:
    out: list[dict] = []
    for e in raw or []:
        if isinstance(e, dict) and e.get("claim") and e.get("source"):
            item = {"claim": str(e["claim"]), "source": str(e["source"])}
            if e.get("kind") in {"fact", "assumption", "inference", "external"}:
                item["kind"] = e["kind"]
            out.append(item)
    return out


def _card_from_llm(
    session: Session, project_id: str, topic: str, context: list[str], out: object,
) -> tuple[Decision, dict] | None:
    """Turn a schema-valid LLM decision payload into `(Decision, detail)`, or `None` if it's unusable.
    Shared by `decide()` and `revise()` so both honour the LLM's own comparison_matrix / criteria."""
    if not (isinstance(out, dict) and out.get("detail") and out.get("recommendation")):
        return None
    detail = dict(out["detail"])
    detail.setdefault("topic", topic)
    detail.setdefault("recommendation", {"chosen": "", "reasons": [], "eliminated": []})
    detail.setdefault("dependencies", context[:4])
    detail.setdefault("related_decisions", [])
    detail.setdefault("missing", "")
    decision = Decision(
        summary=str(out["summary"]),
        recommendation=str(out["recommendation"]),
        confidence=float(out.get("confidence", 0.6)),
        status="recommended",
        assumptions=_coerce_assumptions(out.get("assumptions")),
        risks=_coerce_risks(out.get("risks")),
        tradeoffs=_coerce_tradeoffs(out.get("tradeoffs")),
        next_actions=[str(x) for x in (out.get("next_actions") or []) if x][:6],
        evidence=_coerce_evidence(out.get("evidence")) or [
            {"claim": "deep-dive reasoning", "source": "deep-dive", "kind": "inference"}],
    )
    _link_related(session, project_id, detail)
    return decision, detail


def revise(
    session: Session, project_id: str, prior: Decision, prior_detail: dict, instruction: str,
    router: ModelRouter | None = None,
) -> tuple[Decision, dict]:
    """Re-evaluate an existing decision given the engineer's revision `instruction`, producing an improved
    (Decision, detail). The instruction is folded into the project context (it's new information), and the
    prior decision is handed to the model as the baseline to sharpen — LLM first, heuristic fallback.

    The caller persists the result as a NEW immutable version of the same decision lineage."""
    router = router or ModelRouter()
    instruction = (instruction or "").strip()
    topic = (prior_detail or {}).get("topic") or prior.summary
    # the revision instruction is new project knowledge — persist it like an answer
    _persist_answers(session, project_id, [{"id": "revision", "answer": instruction}])
    context, context_item_ids = _gather_context(
        session, project_id, topic, [{"id": "revision", "answer": instruction}])

    prior_card = {
        "summary": prior.summary,
        "recommendation": prior.recommendation,
        "assumptions": [a.model_dump() if hasattr(a, "model_dump") else a for a in (prior.assumptions or [])],
        "risks": [r.model_dump() if hasattr(r, "model_dump") else r for r in (prior.risks or [])],
        "comparison_matrix": (prior_detail or {}).get("comparison_matrix"),
    }
    try:
        out = router.execute(
            Capability.deepdive,
            {"mode": "revise", "topic": topic, "instruction": instruction,
             "prior": prior_card, "context": context},
            schema=DECISION_CARD_SCHEMA,
            tier=Tier.frontier,  # a revision is a fresh heavy reasoning pass → best chain
        )
        built = _card_from_llm(session, project_id, topic, context, out)
        if built is not None:
            built[1]["context_item_ids"] = context_item_ids  # #7
            return built
    except Exception:  # noqa: BLE001, S110 — fall back to the heuristic below on any LLM/validation failure
        pass

    # heuristic fallback: fold the instruction in as an answer so criteria/context reflect it
    answers = [{"id": "revision", "answer": instruction}] if instruction else []
    detail = _heuristic_detail(topic, answers, context)
    detail["context_item_ids"] = context_item_ids  # #7
    decision = _heuristic_decision(topic, answers, context, detail)
    _link_related(session, project_id, detail)
    return decision, detail


def _link_related(session: Session, project_id: str, detail: dict) -> None:
    """Populate `related_decisions` from other latest decisions in the project (grounds the Decision Explorer)."""
    try:
        related = [
            {"id": r.id, "title": r.title, "status": r.status}
            for r in decision_store.list_for_project(session, project_id)
        ]
        detail["related_decisions"] = related
    except Exception:  # noqa: BLE001 — non-fatal enrichment
        detail.setdefault("related_decisions", [])
