"""Decision output contract (roadmap Ch 6).

The canonical shape the Decision Engine emits and the Verification Engine / DB consume. Bound to the LOCKED
`contracts/decision.schema.json`. If this and the JSON Schema ever disagree, that is a bug — keep them in
sync via a contract-change ticket (see `CLAUDE.md`).
"""
from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Literal

import jsonschema
from pydantic import BaseModel, ConfigDict, Field

_CONTRACT_PATH = Path(__file__).resolve().parents[3] / "contracts" / "decision.schema.json"


def decision_contract() -> dict:
    """The locked JSON Schema, loaded fresh (source of truth)."""
    with open(_CONTRACT_PATH, encoding="utf-8") as fh:
        return json.load(fh)


class DecisionStatus(str, Enum):
    proposed = "proposed"
    recommended = "recommended"
    verified = "verified"
    frozen = "frozen"


class Assumption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    statement: str
    confidence: float = Field(ge=0, le=1)
    risk_if_wrong: str | None = None


class Risk(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str
    severity: Literal["low", "medium", "high", "critical"]
    likelihood: Literal["low", "medium", "high"]
    mitigation: str | None = None


class Tradeoff(BaseModel):
    model_config = ConfigDict(extra="forbid")
    option: str
    benefit: str
    drawback: str


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim: str
    source: str
    kind: Literal["fact", "assumption", "inference", "external"] | None = None


class Decision(BaseModel):
    """A single decision output. `extra="forbid"` mirrors the contract's additionalProperties:false."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    schema_version: Literal["edos.decision.v1"] = "edos.decision.v1"
    decision_id: str | None = None
    summary: str = Field(min_length=1)
    recommendation: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    status: DecisionStatus
    assumptions: list[Assumption] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    tradeoffs: list[Tradeoff] = Field(default_factory=list)
    affected_decisions: list[str] = Field(default_factory=list)
    evidence: list[Evidence]
    next_actions: list[str] = Field(default_factory=list)
    freeze_blockers: list[str] = Field(default_factory=list)

    def to_contract_dict(self) -> dict:
        """Serialize to a dict that satisfies the locked JSON Schema (drops None optionals)."""
        return self.model_dump(exclude_none=True)


def validate_against_contract(data: dict) -> None:
    """Raise jsonschema.ValidationError if `data` violates the LOCKED decision contract."""
    jsonschema.validate(instance=data, schema=decision_contract())
