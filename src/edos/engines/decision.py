"""Decision Engine (roadmap Ch 6).

Turns an assembled context package into a structured decision. It **never retrieves context itself** — it
reasons only over the package. It routes reasoning through the Model Router (a stub provider for now; real
LLM at go-live) and returns a contract-valid `Decision`.

Safety invariants:
- **Status caps at `recommended`.** Only the Verification Engine (CP-5) may promote to `verified`, and only
  the freeze gate (CP-9) may reach `frozen`. The Decision Engine never emits verified/frozen.
- **No guessing.** If essential context is missing, it asks for clarification instead of fabricating a
  decision (Ch 6 clarification policy).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from edos.engines.model_router import Capability, ModelRouter
from edos.models.context import ContextPackage
from edos.models.decision import Decision, decision_contract


@dataclass
class ClarificationNeeded:
    """Returned instead of a Decision when the context is too thin to reason responsibly."""

    reason: str
    questions: list[str] = field(default_factory=list)


class DecisionEngine:
    def __init__(self, router: ModelRouter | None = None) -> None:
        self.router = router or ModelRouter()

    def analyze(self, context: ContextPackage) -> Decision | ClarificationNeeded:
        missing = self._missing_essentials(context)
        if missing:
            return ClarificationNeeded(reason="insufficient context to reason", questions=missing)

        raw = self.router.execute(
            Capability.decision,
            context=context.to_contract_dict(),
            schema=decision_contract(),
        )
        return self._cap_status(Decision(**raw))

    @staticmethod
    def _missing_essentials(context: ContextPackage) -> list[str]:
        """Essential-info check (Ch 6). Empty context => clarification, not a guess."""
        questions: list[str] = []
        if not context.items:
            questions.append(
                "No project context (requirements/decisions/constraints) was available to reason over. "
                "Provide the relevant project state before requesting a decision."
            )
        return questions

    @staticmethod
    def _cap_status(decision: Decision) -> Decision:
        """The Decision Engine may never emit verified/frozen — downgrade to recommended if a provider does."""
        if decision.status in ("verified", "frozen"):
            return decision.model_copy(update={"status": "recommended"})
        return decision
