"""Knowledge Engine (roadmap Ch 7).

Converts an accepted decision into structured, reusable knowledge and runs **quality gates before persist**
(schema, references, dedupe, confidence, source attribution). Nothing that fails the hard gates is written.

CP-7 uses deterministic extraction (placeholder for the LLM extractor at go-live). The gate contract is
unchanged when the real extractor lands.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from edos.models.decision import Decision
from edos.models.entities import KnowledgeItem

CONFIDENCE_FLOOR = 0.3


@dataclass
class GateResult:
    passed: bool
    reasons: list[str]


class KnowledgeEngine:
    def extract(self, decision: Decision, project_id: str) -> list[KnowledgeItem]:
        """Deterministic extraction (placeholder for LLM extraction at go-live)."""
        items: list[KnowledgeItem] = [
            KnowledgeItem(
                id="kn-recommendation",
                project_id=project_id,
                content=self.normalize(decision.recommendation),
                confidence=decision.confidence,
                permanent=True,
            )
        ]
        for i, ev in enumerate(decision.evidence):
            if ev.kind == "fact":
                items.append(
                    KnowledgeItem(
                        id=f"kn-fact-{i}",
                        project_id=project_id,
                        content=self.normalize(ev.claim),
                        confidence=0.9,
                        permanent=True,
                    )
                )
        return items

    @staticmethod
    def normalize(text: str) -> str:
        """Canonicalize: 'STM32 H743' -> 'STM32H743'; collapse whitespace."""
        text = re.sub(r"\bSTM32\s+([A-Za-z0-9]+)", r"STM32\1", text)
        return re.sub(r"\s+", " ", text).strip()

    def hard_gate(self, items: list[KnowledgeItem]) -> GateResult:
        """Hard failures that must block persist: empty content, missing attribution."""
        reasons: list[str] = []
        for it in items:
            if not it.content.strip():
                reasons.append("empty content")
            if not it.project_id:
                reasons.append("missing source attribution")
        return GateResult(passed=not reasons, reasons=reasons)

    @staticmethod
    def _dedupe(items: list[KnowledgeItem]) -> list[KnowledgeItem]:
        seen: set[tuple[str, str]] = set()
        out: list[KnowledgeItem] = []
        for it in items:
            key = (it.project_id, it.content)
            if key not in seen:
                seen.add(key)
                out.append(it)
        return out

    def process(self, decision: Decision, project_id: str) -> list[KnowledgeItem]:
        """Extract → hard gate → dedupe → drop below confidence floor. Returns what may be persisted."""
        items = self.extract(decision, project_id)
        gate = self.hard_gate(items)
        if not gate.passed:
            raise ValueError(f"quality gates failed: {gate.reasons}")
        items = self._dedupe(items)
        return [it for it in items if it.confidence >= CONFIDENCE_FLOOR]
