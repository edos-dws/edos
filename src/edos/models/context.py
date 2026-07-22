"""Context Package contract (roadmap Ch 5/15).

The deterministic, pre-assembled evidence package the Context Engine builds and the Decision Engine reasons
over. The LLM never retrieves context itself. Bound to the LOCKED `contracts/context_package.schema.json`.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import jsonschema
from pydantic import BaseModel, ConfigDict, Field

_CONTRACT_PATH = Path(__file__).resolve().parents[3] / "contracts" / "context_package.schema.json"

ItemType = Literal["project", "requirement", "decision", "assumption", "risk", "document", "external"]


def context_package_contract() -> dict:
    with open(_CONTRACT_PATH, encoding="utf-8") as fh:
        return json.load(fh)


class ContextItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: ItemType
    ref_id: str | None = None
    content: str
    score: float = Field(ge=0, le=1)
    confidence: float | None = Field(default=None, ge=0, le=1)


class ContextPackage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["edos.context_package.v1"] = "edos.context_package.v1"
    project_id: str
    intent: str
    entities: list[str] = Field(default_factory=list)
    items: list[ContextItem]
    external_used: bool | None = None
    token_estimate: int | None = Field(default=None, ge=0)

    def ranked_items(self) -> list[ContextItem]:
        """Items highest-score first — the order the Decision Engine should read them in."""
        return sorted(self.items, key=lambda it: it.score, reverse=True)

    def to_contract_dict(self) -> dict:
        return self.model_dump(exclude_none=True)


def validate_against_contract(data: dict) -> None:
    """Raise jsonschema.ValidationError if `data` violates the LOCKED context-package contract."""
    jsonschema.validate(instance=data, schema=context_package_contract())
