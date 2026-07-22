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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from edos.engines.context import ContextEngine
from edos.engines.decision import ClarificationNeeded, DecisionEngine
from edos.engines.model_router import Capability, ModelRouter
from edos.engines.verification import VerificationEngine
from edos.models.decision import Decision
from edos.pipeline.hub import hub

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


class VerifyRequest(BaseModel):
    decision: dict


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


def _build_decision(req: AnalyzeRequest):
    package = ContextEngine().build(
        project_id=req.project_id, intent=req.question, entities=[], candidates=req.context_items
    )
    return DecisionEngine().analyze(package)


@app.post("/v1/analyze")
async def analyze(req: AnalyzeRequest) -> dict:
    result = _build_decision(req)
    if isinstance(result, ClarificationNeeded):
        return {"status": "needs_clarification", "reason": result.reason, "questions": result.questions}
    body = result.to_contract_dict()
    # push a live event to any project-event subscribers
    await hub.publish(req.project_id, {"type": "decision.ready", "summary": result.summary,
                                       "confidence": result.confidence})
    return body


@app.post("/v1/verify")
def verify(req: VerifyRequest) -> dict:
    decision = Decision(**req.decision)
    engine = VerificationEngine()
    verdict = engine.verify(decision)
    promoted = engine.promote(decision, verdict)
    return {
        "verdict": {"agreement": verdict.agreement, "adjusted_confidence": verdict.adjusted_confidence,
                    "issues": verdict.issues},
        "decision": promoted.to_contract_dict(),
    }


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
        result = _build_decision(req)
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
