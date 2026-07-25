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
from edos.engines.model_router import Capability, ModelRouter
from edos.models.decision import Decision


def _persist_answers(session: Session, project_id: str, answers: list[dict]) -> None:
    """Save the engineer's deep-dive answers as project context (facts/requirements) so they ground this and
    future reasoning — the answers are context, not assumptions."""
    for a in answers or []:
        ans = (a.get("answer") or "").strip()
        if not ans:
            continue
        content = f"[deep-dive answer · {a.get('id', 'q')}] {ans}"
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
    low = (topic or "").lower()
    picked: list[dict] = []
    for probe in _QUESTION_PROBES:
        if any(t in low for t in probe["any"]):
            picked.append({"q": probe["q"], "why": probe["why"]})
    # top up to >= 5 targeted questions, cap at 8 (backlog: 5-8)
    for g in _GENERIC_QUESTIONS:
        if len(picked) >= 5:
            break
        if all(g["q"] != p["q"] for p in picked):
            picked.append(g)
    picked = picked[:8]
    return [{"id": f"q{i + 1}-{_slug(p['q'])}", "q": p["q"], "why": p["why"]}
            for i, p in enumerate(picked)]


def _candidate_questions(topic: str, router: ModelRouter | None = None) -> tuple[list[dict], str]:
    """Generate the candidate question set. Returns (questions, source) where source is "llm" (topic-specific
    LLM output) or "heuristic" (the static probe fallback — used offline OR when the live LLM errors, e.g. a
    quota/429). The source lets the UI tell the engineer when questions are degraded, not silently static."""
    router = router or ModelRouter()
    try:
        out = router.execute(Capability.deepdive, {"mode": "questions", "topic": topic},
                             schema=QUESTIONS_SCHEMA)
        raw = out.get("questions") if isinstance(out, dict) else None
        parsed = [
            {"id": f"q{i + 1}-{_slug(q['q'])}", "q": q["q"].strip(), "why": q["why"].strip()}
            for i, q in enumerate(raw or [])
            if isinstance(q, dict) and q.get("q") and q.get("why")
        ]
        if len(parsed) >= 5:
            return parsed[:8], "llm"
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
    candidates, generated_by = _candidate_questions(topic, router)

    kept: list[dict] = []
    skipped: list[dict] = []
    for q in candidates:
        match = _covered_by(q["q"], context, embedder) if context else None
        if match is not None:
            reason = f'already established in project context: "{match[:120]}"'
            skipped.append({"q": q["q"], "reason": reason})
        else:
            kept.append(q)

    note = ""
    if candidates and not kept:
        note = ("The project already has enough context on this topic — every question I would ask is "
                "already answered. You can go straight to a decision.")
    # `generated_by`: "llm" = topic-specific model questions; "heuristic" = static fallback (LLM offline or
    # quota-limited) — the UI surfaces this so static questions are never mistaken for the model's output.
    return {"questions": kept, "skipped": skipped, "note": note, "generated_by": generated_by}


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
def _gather_context(session: Session, project_id: str, topic: str, answers: list[dict]) -> list[str]:
    """Retriever context (grounding) + the engineer's answers, as plain content strings."""
    ctx: list[str] = []
    try:
        for c in retrieval.retrieve(session, project_id=project_id, question=topic):
            if c["signals"]["semantic"] >= 0.2 or c["signals"]["graph"] >= 0.2:
                ctx.append(c["content"])
    except Exception:  # noqa: BLE001, S110 — retrieval is best-effort context; never blocks a decision
        pass
    ctx += [a["answer"] for a in answers if a.get("answer")]
    return ctx


def _options_from_topic(topic: str) -> list[str]:
    """Derive candidate option names from an "A vs B" / "A or B" topic; else two generic named options."""
    low = (topic or "").lower()
    for sep in (" vs ", " vs. ", " versus ", " or "):
        if sep in low:
            head = low.split(sep)
            left = head[0].split()[-1] if head[0].split() else "Option A"
            right = head[1].split()[0] if head[1].split() else "Option B"
            a, b = left.strip(".,").title(), right.strip(".,").title()
            if a and b and a != b:
                return [a, b, "Hybrid"]
    return ["Baseline approach", "Alternative approach"]


def _impacted_components(text: str) -> list[str]:
    low = text.lower()
    hits = [name for name, kws in _COMPONENT_KEYWORDS if any(k in low for k in kws)]
    # stable de-dupe, sensible default
    seen: list[str] = []
    for h in hits:
        if h not in seen:
            seen.append(h)
    return seen or ["Firmware", "Hardware", "BOM"]


def _heuristic_detail(topic: str, answers: list[dict], context: list[str]) -> dict:
    """Deterministic Decision-Card detail from topic + answers + context. No fabricated datasheet values —
    options/criteria are structural, the specifics come from what the engineer actually said."""
    options = _options_from_topic(topic)
    chosen = options[0]
    answer_texts = [a.get("answer", "") for a in answers if a.get("answer")]
    blob = " ".join([topic, *answer_texts, *context])

    # criteria: a standard engineering axis set (rows of the comparison matrix)
    criteria = ["Cost", "Complexity", "Performance / accuracy", "Risk", "Time to integrate"]
    # per-option qualitative values (structural, not fabricated numbers)
    profiles = {
        0: ["Lower", "Lower", "Meets spec", "Lower", "Faster"],
        1: ["Higher", "Higher", "Higher headroom", "Higher", "Slower"],
        2: ["Medium", "Medium", "Balanced", "Medium", "Medium"],
    }
    matrix_options = []
    for i, name in enumerate(options):
        matrix_options.append({
            "name": name,
            "values": profiles.get(i, ["Medium"] * len(criteria))[:len(criteria)],
            "recommended": (i == 0),
        })

    recommendation = {
        "chosen": chosen,
        "reasons": [
            f"Satisfies the stated constraints for '{topic.strip() or 'this decision'}' at the lowest risk",
            "Lower cost and complexity than the alternatives for the current spec",
            "Fastest path to integration without foreclosing the expansion path",
        ] + ([f"Directly reflects the engineer's answer: \"{answer_texts[0][:90]}\""] if answer_texts else []),
        "eliminated": [
            {"option": o["name"],
             "reason": "Adds cost/complexity that the current requirements do not justify"}
            for o in matrix_options[1:]
        ],
    }

    decision_impact = [
        {"area": "Firmware", "change": "Driver / control-loop work follows the chosen option"},
        {"area": "Hardware", "change": "Component selection and PCB layout depend on this choice"},
        {"area": "Architecture", "change": "Sets an interface other subsystems build against"},
        {"area": "Power stage", "change": "Thermal and protection budget is derived from this decision"},
    ]

    review_conditions = [
        f"Revisit if the priority stated for '{topic.strip() or 'this'}' changes",
        "Revisit if peak/worst-case operating conditions exceed the assumed envelope",
        "Revisit if the production volume or cost target moves materially",
    ]

    missing = _missing_context(blob, answers)

    return {
        "comparison_matrix": {"criteria": criteria, "options": matrix_options},
        "recommendation": recommendation,
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

    risks = [
        {"description": f"{chosen} adds integration work in {c}",
         "severity": "medium", "likelihood": "medium",
         "mitigation": f"Scope the {c} change before committing"}
        for c in detail["impacted_components"][:2]
    ]
    risks.append({
        "description": ("Under-specified worst-case operating conditions could invalidate the recommendation"),
        "severity": "high", "likelihood": "medium",
        "mitigation": "Confirm peak/fault envelope with bench data",
    })

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

    return Decision(
        summary=f"{topic.strip() or 'Deep dive'} — recommend {chosen}",
        recommendation=f"Recommend {chosen}. " + "; ".join(rec["reasons"][:3]),
        confidence=confidence,
        status="recommended",
        assumptions=assumptions,
        risks=risks,
        tradeoffs=tradeoffs,
        evidence=evidence,
        next_actions=[f"Proceed with {chosen}", "Close the missing context: " + (detail.get("missing") or "n/a")],
    )


DECISION_CARD_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "recommendation": {"type": "string"},
        "confidence": {"type": "number"},
        "assumptions": {"type": "array"},
        "risks": {"type": "array"},
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
    context = _gather_context(session, project_id, topic, answers)

    try:
        out = router.execute(
            Capability.deepdive,
            {"mode": "decide", "topic": topic, "answers": answers, "context": context},
            schema=DECISION_CARD_SCHEMA,
        )
        if isinstance(out, dict) and out.get("detail") and out.get("recommendation"):
            detail = dict(out["detail"])
            detail.setdefault("recommendation", {"chosen": "", "reasons": [], "eliminated": []})
            detail.setdefault("dependencies", context[:4])
            detail.setdefault("related_decisions", [])
            detail.setdefault("missing", "")
            decision = Decision(
                summary=str(out["summary"]),
                recommendation=str(out["recommendation"]),
                confidence=float(out.get("confidence", 0.6)),
                status="recommended",
                assumptions=out.get("assumptions", []),
                risks=out.get("risks", []),
                evidence=out.get("evidence") or [
                    {"claim": "deep-dive reasoning", "source": "deep-dive", "kind": "inference"}],
            )
            _link_related(session, project_id, detail)
            return decision, detail
    except Exception:  # noqa: BLE001, S110 — any LLM/validation failure falls back to the heuristic below
        pass

    detail = _heuristic_detail(topic, answers, context)
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
