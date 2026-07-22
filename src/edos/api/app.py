"""FastAPI surface (roadmap Ch 14).

Endpoints wire the engines together. CP-6 runs on the stub Model Router (no live LLM). `/v1/analyze`
supplies context candidates in the request for now; the real Context Engine will pull them from the DB/graph
at go-live.
"""
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from edos.engines.context import ContextEngine
from edos.engines.decision import ClarificationNeeded, DecisionEngine
from edos.engines.model_router import Capability, ModelRouter
from edos.engines.verification import VerificationEngine
from edos.models.decision import Decision

app = FastAPI(title="EDOS", version="0.0.1")


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


@app.post("/v1/ask")
def ask(req: AskRequest) -> dict:
    intent = ModelRouter().execute(Capability.intent, {"question": req.question})
    return {"project_id": req.project_id, "question": req.question, "intent": intent}


@app.post("/v1/analyze")
def analyze(req: AnalyzeRequest) -> dict:
    package = ContextEngine().build(
        project_id=req.project_id,
        intent=req.question,
        entities=[],
        candidates=req.context_items,
    )
    result = DecisionEngine().analyze(package)
    if isinstance(result, ClarificationNeeded):
        return {"status": "needs_clarification", "reason": result.reason, "questions": result.questions}
    return result.to_contract_dict()


@app.post("/v1/verify")
def verify(req: VerifyRequest) -> dict:
    decision = Decision(**req.decision)
    engine = VerificationEngine()
    verdict = engine.verify(decision)
    promoted = engine.promote(decision, verdict)
    return {
        "verdict": {
            "agreement": verdict.agreement,
            "adjusted_confidence": verdict.adjusted_confidence,
            "issues": verdict.issues,
        },
        "decision": promoted.to_contract_dict(),
    }
