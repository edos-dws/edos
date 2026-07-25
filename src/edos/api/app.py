"""FastAPI surface (roadmap Ch 14) — REST + WebSocket.

REST for request/response (`/v1/ask`, `/v1/analyze`, `/v1/verify`) and WebSocket for **live connectivity**
the frontend needs push for:
- `/v1/ws/analyze` streams an analysis (context → reasoning → verify → decision) as it happens;
- `/v1/ws/projects/{id}/events` streams project events (decision ready, knowledge added, alerts, job
  progress) pushed via the EventHub.

CP-6+ runs on the stub Model Router (no live LLM). CORS is open for local frontend development — restrict
`allow_origins` in production.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from edos.api.deps import get_session, session_factory
from edos.db.models import CoverageAnswer, GraphEdge, ProjectItem, new_decision_version
from edos.engines import (
    auth,
    coverage,
    decision_store,
    deepdive,
    domain,
    extraction,
    faithfulness,
    feedback,
    ingestion,
    resolution,
    retrieval,
    watchdog,
    writeback,
)
from edos.engines import (
    challenge as challenge_engine,
)
from edos.engines import (
    findings as findings_engine,
)
from edos.engines.context import ContextEngine
from edos.engines.decision import ClarificationNeeded, DecisionEngine
from edos.engines.freeze import FreezeGate
from edos.engines.model_router import Capability, ModelRouter
from edos.engines.verification import VerificationEngine
from edos.models.decision import Decision
from edos.pipeline.hub import hub
from edos.store import projects as store


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def current_user(authorization: str | None = Header(default=None),
                 session: Session = Depends(get_session)):
    """Optional bearer-token auth (CP-19). Returns the user or None; enforcement is opt-in (OD-8)."""
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    return auth.user_for_token(session, token)

app = FastAPI(title="EDOS", version="0.0.1")

# Open for local frontend dev. In production, set allow_origins to the frontend origin(s).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- request models ----------
class AskRequest(BaseModel):
    project_id: str
    question: str


class AnalyzeRequest(BaseModel):
    project_id: str
    question: str
    context_items: list[dict] = Field(default_factory=list)
    use_external_intelligence: bool = False
    conversation_id: str | None = None  # when set, the analyze turn is recorded on that conversation


class VerifyRequest(BaseModel):
    decision: dict
    context_refs: list[str] | None = None  # when given, verify runs the faithfulness pass (CP-16)


class ProjectCreate(BaseModel):
    name: str
    domain: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    domain: str | None = None


class ConversationCreate(BaseModel):
    title: str = ""


_FRONTEND = Path(__file__).resolve().parents[3] / "frontend" / "index.html"


@app.get("/app")
def frontend() -> FileResponse:
    """Serve the default single-file UI (CP-18). Stack is vanilla JS by default (OD-7) — swappable."""
    return FileResponse(_FRONTEND)


# ---------- health ----------
@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "edos", "version": "0.0.1", "mode": "stub"}


@app.get("/v1/health")
def health_v1() -> dict:
    return {"status": "ok"}


# ---------- REST ----------
@app.post("/v1/ask")
def ask(req: AskRequest) -> dict:
    intent = ModelRouter().execute(Capability.intent, {"question": req.question})
    return {"project_id": req.project_id, "question": req.question, "intent": intent}


def _candidates(req: AnalyzeRequest, session: Session | None) -> list[dict]:
    """Explicit `context_items` override the retriever; otherwise the Retriever (CP-13) assembles context
    from the project. `session=None` (no DB) yields no candidates → clarification."""
    if req.context_items:
        return req.context_items
    if session is None:
        return []
    return retrieval.retrieve(session, project_id=req.project_id, question=req.question)


def _build_decision(req: AnalyzeRequest, candidates: list[dict]):
    package = ContextEngine().build(
        project_id=req.project_id, intent=req.question, entities=[], candidates=candidates
    )
    return DecisionEngine().analyze(package)


def _record_turn(conversation_id: str, prompt: str, body: dict) -> None:
    """Persist an analyze exchange as a conversation turn (CP-10). Uses its own short-lived session so the
    stateless reasoning path is unaffected when no conversation is linked."""
    session = session_factory()()
    try:
        store.add_turn(session, conversation_id=conversation_id, prompt=prompt,
                       response_json=json.dumps(body))
        session.commit()
    finally:
        session.close()


@app.post("/v1/analyze")
async def analyze(req: AnalyzeRequest, session: Session = Depends(get_session)) -> dict:
    candidates = _candidates(req, session)
    if candidates and not retrieval.coverage_ok(candidates):
        # missing-context guard: relevant coverage too thin → clarify, don't reason blind
        body = {"status": "needs_clarification", "reason": "insufficient relevant context",
                "questions": [("Retrieved project context isn't relevant enough to reason confidently. "
                               "Add or link the relevant requirements/decisions, or refine the question.")]}
    else:
        result = _build_decision(req, candidates)
        if isinstance(result, ClarificationNeeded):
            body = {"status": "needs_clarification", "reason": result.reason,
                    "questions": result.questions}
        else:
            # faithfulness / grounding gate (CP-14): trace claims to retrieved context; ungrounded →
            # lower confidence + record as freeze_blockers (kept contract-valid).
            fr = faithfulness.check(result, [c.get("ref_id") for c in candidates])
            result = faithfulness.apply_gate(result, fr)
            body = result.to_contract_dict()
            await hub.publish(req.project_id, {"type": "decision.ready", "summary": result.summary,
                                               "confidence": result.confidence})
    if req.conversation_id:
        _record_turn(req.conversation_id, req.question, body)
    return body


@app.post("/v1/verify")
def verify(req: VerifyRequest) -> dict:
    decision = Decision(**req.decision)
    engine = VerificationEngine()
    verdict = engine.verify(decision, context_refs=req.context_refs)
    promoted = engine.promote(decision, verdict)
    return {
        "verdict": {"agreement": verdict.agreement, "adjusted_confidence": verdict.adjusted_confidence,
                    "issues": verdict.issues, "faithfulness": verdict.faithfulness},
        "decision": promoted.to_contract_dict(),
    }


@app.post("/v1/decisions/{decision_id}/freeze")
def freeze_decision(decision_id: str, session: Session = Depends(get_session)) -> dict:
    """Freeze gate (CP-16): freezes ONLY if the gate passes. Threshold T is unset (data-derived), so the
    gate is disabled and refuses — no autonomous freeze. Returns the blocking reasons."""
    row = decision_store.get_latest(session, decision_id)
    if row is None:
        raise HTTPException(status_code=404, detail="decision not found")
    decision = decision_store.to_decision(row)
    open_contradictions = session.scalar(
        select(func.count()).select_from(GraphEdge).where(
            GraphEdge.relation_type == "conflicts_with", GraphEdge.validity == "active",
            or_(GraphEdge.source_id == decision_id, GraphEdge.target_id == decision_id),
        )
    ) or 0
    gate = FreezeGate()  # threshold=None → disabled (fail-safe)
    result = gate.evaluate(decision, open_contradictions=open_contradictions)
    if not result.frozen:
        return {"frozen": False, "reasons": result.reasons}
    frozen = gate.apply(decision, open_contradictions)
    new_row = new_decision_version(session, row, status="frozen",
                                   body_json=json.dumps(frozen.to_contract_dict()))
    return {"frozen": True, "decision": _decision_envelope(new_row)}


# ---------- projects (CP-10) ----------
def _project_dict(row) -> dict:
    return {"id": row.id, "name": row.name, "domain": row.domain, "owner_id": row.owner_id}


class SignupRequest(BaseModel):
    email: str


@app.post("/v1/auth/signup", status_code=201)
def signup_ep(body: SignupRequest, session: Session = Depends(get_session)) -> dict:
    user = auth.signup(session, email=body.email)
    return {"user_id": user.id, "email": user.email, "token": user.token}


def _conversation_dict(row) -> dict:
    return {"id": row.id, "project_id": row.project_id, "title": row.title,
            "created_at": row.created_at.isoformat() if row.created_at else None}


@app.post("/v1/projects", status_code=201)
def create_project(body: ProjectCreate, session: Session = Depends(get_session),
                   user=Depends(current_user)) -> dict:
    row = store.create_project(session, id=_new_id(), name=body.name, domain=body.domain)
    if user is not None:
        row.owner_id = user.id  # scope to the authenticated owner (CP-19)
        session.flush()
    return _project_dict(row)


@app.get("/v1/projects")
def list_projects(session: Session = Depends(get_session), user=Depends(current_user)) -> list[dict]:
    # authenticated: show your projects + shared (unowned). unauthenticated: all (auth is opt-in, OD-8).
    return [_project_dict(r) for r in store.list_projects(session) if auth.can_access_project(r, user)]


@app.get("/v1/projects/{project_id}")
def get_project(project_id: str, session: Session = Depends(get_session)) -> dict:
    row = store.get_project(session, project_id)
    if row is None:
        raise HTTPException(status_code=404, detail="project not found")
    return _project_dict(row)


@app.patch("/v1/projects/{project_id}")
def update_project(project_id: str, body: ProjectUpdate, session: Session = Depends(get_session)) -> dict:
    row = store.update_project(session, project_id, name=body.name, domain=body.domain)
    if row is None:
        raise HTTPException(status_code=404, detail="project not found")
    return _project_dict(row)


@app.delete("/v1/projects/{project_id}")
def delete_project(project_id: str, session: Session = Depends(get_session)) -> dict:
    if not store.delete_project(session, project_id):
        raise HTTPException(status_code=404, detail="project not found")
    return {"deleted": project_id}


# ---------- conversations (CP-10) ----------
@app.post("/v1/projects/{project_id}/conversations", status_code=201)
def create_conversation(
    project_id: str, body: ConversationCreate, session: Session = Depends(get_session)
) -> dict:
    if store.get_project(session, project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    row = store.create_conversation(session, id=_new_id(), project_id=project_id, title=body.title)
    return _conversation_dict(row)


@app.get("/v1/projects/{project_id}/conversations")
def list_conversations(project_id: str, session: Session = Depends(get_session)) -> list[dict]:
    if store.get_project(session, project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    return [_conversation_dict(c) for c in store.list_conversations(session, project_id)]


@app.get("/v1/conversations/{conversation_id}")
def get_conversation(conversation_id: str, session: Session = Depends(get_session)) -> dict:
    conv = store.get_conversation(session, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    turns = [
        {"prompt": t.prompt, "response": json.loads(t.response_json) if t.response_json else None,
         "decision_id": t.decision_id,
         "created_at": t.created_at.isoformat() if t.created_at else None}
        for t in store.list_turns(session, conversation_id)
    ]
    return {**_conversation_dict(conv), "turns": turns}


# ---------- decisions (CP-11) ----------
class DecisionPersist(BaseModel):
    project_id: str
    decision: dict
    status: str | None = None


class DecisionAccept(BaseModel):
    edited: dict | None = None


def _decision_envelope(row) -> dict:
    return {
        "id": row.id, "project_id": row.project_id, "version": row.version,
        "parent_version": row.parent_version, "status": row.status, "confidence": row.confidence,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "decision": json.loads(row.body_json) if row.body_json else None,
        # Rich Decision-Card detail (UI-CP-4) — persistence ENVELOPE, not the locked decision contract.
        "decision_detail": json.loads(row.decision_detail) if row.decision_detail else None,
    }


@app.post("/v1/decisions", status_code=201)
def persist_decision(body: DecisionPersist, session: Session = Depends(get_session)) -> dict:
    decision = Decision(**body.decision)
    row = decision_store.save_new(
        session, id=_new_id(), project_id=body.project_id, decision=decision, status=body.status
    )
    return _decision_envelope(row)


@app.get("/v1/decisions/{decision_id}")
def get_decision(decision_id: str, session: Session = Depends(get_session)) -> dict:
    row = decision_store.get_latest(session, decision_id)
    if row is None:
        raise HTTPException(status_code=404, detail="decision not found")
    return _decision_envelope(row)


@app.get("/v1/decisions/{decision_id}/history")
def decision_history(decision_id: str, session: Session = Depends(get_session)) -> list[dict]:
    rows = decision_store.history(session, decision_id)
    if not rows:
        raise HTTPException(status_code=404, detail="decision not found")
    return [_decision_envelope(r) for r in rows]


@app.post("/v1/decisions/{decision_id}/accept")
def accept_decision(
    decision_id: str, body: DecisionAccept, session: Session = Depends(get_session)
) -> dict:
    edited = Decision(**body.edited) if body.edited else None
    row = decision_store.accept(session, decision_id, edited=edited)
    if row is None:
        raise HTTPException(status_code=404, detail="decision not found")
    # write-back (CP-15): fold the accepted decision's knowledge into the project graph + embeddings
    writeback.process_accepted(session, decision_id=row.id, project_id=row.project_id,
                               decision=decision_store.to_decision(row))
    return _decision_envelope(row)


# ---------- Challenge My Decision (UI-CP-5) ----------
class ChallengeAccept(BaseModel):
    statement: str
    note: str | None = None
    challenged_by: str | None = None


@app.post("/v1/decisions/{decision_id}/challenge")
def challenge_decision(decision_id: str, session: Session = Depends(get_session)) -> dict:
    """The iconic interaction (PDF p11): EDOS argues AGAINST its own recommendation. Loads the latest
    decision, picks the single load-bearing assumption (lowest-confidence, biased by risk_if_wrong severity),
    and returns the counter-case: what that assumption is costing you vs what the alternative offers, plus a
    cost callout. Stub→heuristic like extraction.py — never fabricates dollar figures offline."""
    row = decision_store.get_latest(session, decision_id)
    if row is None:
        raise HTTPException(status_code=404, detail="decision not found")
    result = challenge_engine.challenge(decision_store.to_decision(row))
    if result is None:
        raise HTTPException(status_code=422,
                            detail="decision states no assumptions — nothing load-bearing to challenge")
    return {"decision_id": decision_id, **result}


@app.post("/v1/decisions/{decision_id}/challenge/accept")
def accept_challenge(
    decision_id: str, body: ChallengeAccept, session: Session = Depends(get_session)
) -> dict:
    """Mark the load-bearing assumption CHALLENGED — it flips from a silent assumption to a monitored risk
    (reuses resolution semantics). Returns the updated decision envelope."""
    row = resolution.challenge_assumption(
        session, decision_id=decision_id, statement=body.statement,
        note=body.note, challenged_by=body.challenged_by,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="decision not found")
    return _decision_envelope(row)


# ---------- interactive resolution (CP-15) ----------
class AssumptionResolve(BaseModel):
    statement: str
    resolution: str
    resolved_by: str | None = None


class ConflictResolve(BaseModel):
    node_a: str
    node_b: str


class ClarifyAnswer(BaseModel):
    project_id: str
    question: str
    answers: list[str]
    conversation_id: str | None = None


@app.post("/v1/decisions/{decision_id}/assumptions/resolve")
def resolve_assumption_ep(
    decision_id: str, body: AssumptionResolve, session: Session = Depends(get_session)
) -> dict:
    row = resolution.resolve_assumption(
        session, decision_id=decision_id, statement=body.statement,
        resolution=body.resolution, resolved_by=body.resolved_by,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="decision not found")
    return _decision_envelope(row)


@app.post("/v1/conflicts/resolve")
def resolve_conflict_ep(body: ConflictResolve, session: Session = Depends(get_session)) -> dict:
    closed = resolution.resolve_conflict(session, node_a=body.node_a, node_b=body.node_b)
    return {"resolved_edges": closed, "node_a": body.node_a, "node_b": body.node_b}


class OutcomeRecord(BaseModel):
    outcome: str  # accepted | challenged | reversed


@app.post("/v1/decisions/{decision_id}/outcome")
def record_outcome_ep(
    decision_id: str, body: OutcomeRecord, session: Session = Depends(get_session)
) -> dict:
    try:
        row = feedback.record_outcome(session, decision_id=decision_id, outcome=body.outcome)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="decision not found")
    return {"decision_id": decision_id, "outcome": row.outcome,
            "confidence_at_outcome": row.confidence_at_outcome}


@app.get("/v1/calibration")
def calibration_ep(session: Session = Depends(get_session)) -> dict:
    report = feedback.calibration_report(session)
    report["ranking_suggestion"] = feedback.suggest_ranking_adjustment(report)
    return report


@app.post("/v1/analyze/answer")
async def answer_clarification(body: ClarifyAnswer, session: Session = Depends(get_session)) -> dict:
    """Clarification loop: fold the engineer's answers in as context and re-run the analysis."""
    extra = [
        {"type": "assumption", "ref_id": f"ans-{i}", "content": a,
         "signals": {"graph": 0.5, "semantic": 0.8, "recency": 1.0, "confidence": 0.8, "focus": 1.0}}
        for i, a in enumerate(body.answers)
    ]
    req = AnalyzeRequest(project_id=body.project_id, question=body.question, context_items=extra,
                         conversation_id=body.conversation_id)
    return await analyze(req, session)


@app.get("/v1/projects/{project_id}/decisions")
def list_project_decisions(project_id: str, session: Session = Depends(get_session)) -> list[dict]:
    if store.get_project(session, project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    return [_decision_envelope(r) for r in decision_store.list_for_project(session, project_id)]


# ---------- project items / graph ingestion (CP-12) ----------
class ItemIngest(BaseModel):
    item_type: str
    content: str
    id: str | None = None
    domain: str | None = None  # optional engineering-domain tag (UI-CP-2 coverage)


def _item_dict(item) -> dict:
    return {"id": item.id, "project_id": item.project_id, "item_type": item.item_type,
            "content": item.content, "validity": item.validity, "needs_linking": item.needs_linking,
            "domain": item.domain}


@app.post("/v1/projects/{project_id}/items", status_code=201)
def ingest_item(project_id: str, body: ItemIngest, session: Session = Depends(get_session)) -> dict:
    if store.get_project(session, project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    item = ingestion.ingest_item(
        session, id=body.id or _new_id(), project_id=project_id,
        item_type=body.item_type, content=body.content, domain=body.domain,
    )
    return _item_dict(item)


class SmartAsk(BaseModel):
    question: str
    conversation_id: str | None = None
    auto_extract: bool = True


@app.post("/v1/projects/{project_id}/ask")
async def smart_ask(
    project_id: str, body: SmartAsk, session: Session = Depends(get_session)
) -> dict:
    """Auto-context ask: pull requirements/assumptions out of the question, fold them into the project as
    context, then reason. Returns the extracted context (so the engineer sees what was captured) + decision."""
    if store.get_project(session, project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    extracted: list[dict] = []
    if body.auto_extract:
        for it in extraction.extract(body.question):
            row = ingestion.ingest_item(session, id=_new_id(), project_id=project_id,
                                        item_type=it["type"], content=it["content"])
            extracted.append({"id": row.id, "item_type": row.item_type, "content": row.content})
    req = AnalyzeRequest(project_id=project_id, question=body.question,
                         conversation_id=body.conversation_id)
    decision = await analyze(req, session)
    return {"extracted": extracted, "decision": decision}


@app.get("/v1/projects/{project_id}/items")
def list_items(project_id: str, session: Session = Depends(get_session)) -> list[dict]:
    if store.get_project(session, project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    rows = session.scalars(
        select(ProjectItem).where(ProjectItem.project_id == project_id).order_by(ProjectItem.created_at)
    ).all()
    return [_item_dict(r) for r in rows]


# ---------- domain grounding + proactive watchdog (CP-20) ----------
@app.get("/v1/projects/{project_id}/alerts")
def project_alerts(project_id: str, session: Session = Depends(get_session)) -> list[dict]:
    """Proactive watchdog: open conflicts, stale/superseded items, invalidated dependencies."""
    if store.get_project(session, project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    return [{"type": a.type, "subject": a.subject, "message": a.message, "severity": a.severity}
            for a in watchdog.scan(session, project_id)]


@app.get("/v1/projects/{project_id}/rule-flags")
def project_rule_flags(project_id: str, session: Session = Depends(get_session)) -> list[dict]:
    """Procedural-memory domain rules applied to the project's items."""
    if store.get_project(session, project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    contents = session.scalars(
        select(ProjectItem.content).where(ProjectItem.project_id == project_id)
    ).all()
    return [{"key": f.key, "flag": f.flag, "severity": f.severity, "matched": f.matched}
            for f in domain.apply_rules(contents)]


# ---------- Engineering Review → Findings (UI-CP-3) ----------
class ReviewRequest(BaseModel):
    text: str
    save: bool = False  # optionally ingest the input as project context ("Save to Project Brain")


@app.post("/v1/projects/{project_id}/review")
def review_project(project_id: str, body: ReviewRequest, session: Session = Depends(get_session)) -> dict:
    """Fast, no-question Engineering Review. Returns categorized findings (contradiction /
    hidden_dependency / assumption / optimization / best_practice), each with severity, an
    "IF YOU IGNORE THIS" list, and evidence. `save=true` also folds the input in as project context (so a
    review grows the Project Brain) — findings stay the primary return."""
    if store.get_project(session, project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    result = [f.to_dict() for f in findings_engine.review(session, project_id, body.text)]
    saved: list[dict] = []
    if body.save and body.text.strip():
        for it in extraction.extract(body.text):
            row = ingestion.ingest_item(session, id=_new_id(), project_id=project_id,
                                        item_type=it["type"], content=it["content"])
            saved.append({"id": row.id, "item_type": row.item_type, "content": row.content})
    return {"findings": result, "count": len(result), "saved": saved}


# ---------- Deep Dive → Decision Card (UI-CP-4) ----------
class DeepDiveRequest(BaseModel):
    topic: str


class DeepDiveAnswer(BaseModel):
    id: str
    answer: str


class DeepDiveDecideRequest(BaseModel):
    topic: str
    answers: list[DeepDiveAnswer] = Field(default_factory=list)


@app.post("/v1/projects/{project_id}/deepdive")
def deepdive_questions(
    project_id: str, body: DeepDiveRequest, session: Session = Depends(get_session)
) -> dict:
    """Deep Dive stage 1: 5-8 targeted questions, each with a "WHY AM I ASKING?" rationale (opposite of the
    no-question Engineering Review). Planner LLM with stub→heuristic fallback."""
    if store.get_project(session, project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    return {"topic": body.topic, "questions": deepdive.plan_questions(body.topic)}


@app.post("/v1/projects/{project_id}/deepdive/decide", status_code=201)
def deepdive_decide(
    project_id: str, body: DeepDiveDecideRequest, session: Session = Depends(get_session)
) -> dict:
    """Deep Dive stage 2: reason over (retriever context + the engineer's answers) → a contract-valid
    Decision PLUS a rich `decision_detail` (comparison_matrix / recommendation / decision_impact /
    impacted_components / review_conditions / …). The decision is persisted with the detail in the
    persistence envelope (NOT the locked contract) and the full envelope is returned."""
    if store.get_project(session, project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    answers = [a.model_dump() for a in body.answers]
    decision, detail = deepdive.decide(session, project_id, body.topic, answers)
    row = decision_store.save_new(
        session, id=_new_id(), project_id=project_id, decision=decision,
        status="recommended", detail=detail,
    )
    return _decision_envelope(row)


# ---------- Project Brain + Coverage (UI-CP-1 / UI-CP-2) ----------
@app.get("/v1/projects/{project_id}/brain")
def project_brain(project_id: str, session: Session = Depends(get_session)) -> dict:
    """Project Brain dashboard payload: live coverage + the four headline counts.

    coverage/coverage_by_domain come from the coverage engine (transparent, never fabricated).
    counts: decisions from the decision store; contradictions = open-conflict watchdog alerts;
    open_risks = all watchdog alerts; assumptions = 0 until first-class assumptions land (UI-CP-6)."""
    if store.get_project(session, project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    report = coverage.coverage_report(session, project_id)
    alerts = watchdog.scan(session, project_id)
    decisions = len(decision_store.list_for_project(session, project_id))
    contradictions = sum(1 for a in alerts if a.type == "open_conflict")
    return {
        "coverage": report["overall"],
        "coverage_by_domain": report["by_domain"],
        "counts": {
            "decisions": decisions,
            "assumptions": 0,  # TODO(UI-CP-6): first-class assumptions become countable here
            "contradictions": contradictions,
            "open_risks": len(alerts),
        },
    }


@app.get("/v1/projects/{project_id}/coverage")
def project_coverage(project_id: str, session: Session = Depends(get_session)) -> dict:
    """Per-domain coverage breakdown + each domain's unanswered question-set (the "raise coverage" nudges)."""
    if store.get_project(session, project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    report = coverage.coverage_report(session, project_id)
    return {"overall": report["overall"], "domains": report["detail"]}


class CoverageAnswerBody(BaseModel):
    domain: str
    question_id: str
    answer: str


@app.post("/v1/projects/{project_id}/coverage/answer", status_code=201)
def answer_coverage_question(
    project_id: str, body: CoverageAnswerBody, session: Session = Depends(get_session)
) -> dict:
    """Answer a domain question-set question. The answer is ingested as a domain-tagged context item (so it
    feeds retrieval as a graph node + embedding) AND recorded as answered, so that domain's coverage rises."""
    if store.get_project(session, project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    if body.domain not in coverage.DOMAINS:
        raise HTTPException(status_code=422, detail=f"unknown domain: {body.domain}")
    question = next((q for q in coverage.question_set(body.domain) if q["id"] == body.question_id), None)
    if question is None:
        raise HTTPException(status_code=422, detail=f"unknown question_id: {body.question_id}")

    item = ingestion.ingest_item(
        session, id=_new_id(), project_id=project_id, item_type="requirement",
        content=f"Q: {question['q']}\nA: {body.answer}", domain=body.domain,
    )
    # record (or refresh) the answered question so coverage is deterministic and persisted
    existing = session.scalars(
        select(CoverageAnswer).where(
            CoverageAnswer.project_id == project_id, CoverageAnswer.domain == body.domain,
            CoverageAnswer.question_id == body.question_id,
        )
    ).first()
    if existing is None:
        session.add(CoverageAnswer(project_id=project_id, domain=body.domain,
                                   question_id=body.question_id, item_id=item.id))
    else:
        existing.item_id = item.id
    session.flush()
    report = coverage.coverage_report(session, project_id)
    return {"item": _item_dict(item), "coverage": report["overall"],
            "domain_coverage": report["by_domain"][body.domain]}


@app.post("/v1/projects/{project_id}/events")
async def publish_event(project_id: str, event: dict) -> dict:
    """Publish an event to a project's live stream (used by the passive pipeline, alerts, and tooling)."""
    delivered = await hub.publish(project_id, event)
    return {"project_id": project_id, "delivered": delivered}


# ---------- WebSocket ----------
@app.websocket("/v1/ws/analyze")
async def ws_analyze(ws: WebSocket) -> None:
    """Stream an analysis. Client sends an AnalyzeRequest-shaped JSON; server streams stages + result."""
    await ws.accept()
    try:
        req = AnalyzeRequest(**await ws.receive_json())
        await ws.send_json({"type": "stage", "stage": "assembling_context"})
        if req.context_items:
            candidates = req.context_items
        else:
            _s = session_factory()()
            try:
                candidates = _candidates(req, _s)
            finally:
                _s.close()
        result = _build_decision(req, candidates)
        await ws.send_json({"type": "stage", "stage": "reasoning"})
        if isinstance(result, ClarificationNeeded):
            await ws.send_json({"type": "clarification", "reason": result.reason,
                                "questions": result.questions})
        else:
            await ws.send_json({"type": "stage", "stage": "verifying"})
            await ws.send_json({"type": "decision", "decision": result.to_contract_dict()})
            await hub.publish(req.project_id, {"type": "decision.ready", "summary": result.summary})
        await ws.send_json({"type": "done"})
        await ws.close()
    except WebSocketDisconnect:
        return


@app.websocket("/v1/ws/projects/{project_id}/events")
async def ws_events(ws: WebSocket, project_id: str) -> None:
    """Subscribe to a project's live event stream."""
    await ws.accept()
    q = hub.subscribe(project_id)
    try:
        await ws.send_json({"type": "connected", "project_id": project_id})
        while True:
            event = await q.get()
            await ws.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        hub.unsubscribe(project_id, q)
