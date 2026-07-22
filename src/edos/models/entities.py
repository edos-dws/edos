"""Core domain entities and the Decision Graph edge model (roadmap Ch 3).

Engineering knowledge is never free-form text only — every artifact is a typed object with identity,
confidence, and explicit relationships. These are the persisted domain entities (distinct from the LLM
*output* contracts in `decision.py` / `context.py`).
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class RelationType(str, Enum):
    """The 11 Decision Graph relation types (Ch 3). Dependencies, not similarity."""

    depends_on = "depends_on"
    created_by = "created_by"
    influences = "influences"
    supersedes = "supersedes"
    conflicts_with = "conflicts_with"
    mitigates = "mitigates"
    references = "references"
    derived_from = "derived_from"
    validates = "validates"
    invalidates = "invalidates"
    related_to = "related_to"


class _Entity(BaseModel):
    """Common base: identity + provenance shared by every domain object."""

    model_config = ConfigDict(extra="forbid")
    id: str
    project_id: str
    version: int = 1


class Project(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    domain: str | None = None


class Requirement(_Entity):
    statement: str
    kind: str = "functional"  # functional | non_functional
    status: str = "active"
    confidence: float = Field(default=1.0, ge=0, le=1)


class Assumption(_Entity):
    statement: str
    confidence: float = Field(ge=0, le=1)
    risk_if_wrong: str | None = None


class Component(_Entity):
    name: str
    part_number: str | None = None
    role: str | None = None


class Risk(_Entity):
    description: str
    severity: str  # low | medium | high | critical
    likelihood: str  # low | medium | high
    mitigation: str | None = None


class Document(_Entity):
    title: str
    uri: str | None = None


class KnowledgeItem(_Entity):
    """Extracted, reusable knowledge (Ch 7). Temporary items expire unless promoted."""

    content: str
    permanent: bool = False
    confidence: float = Field(default=1.0, ge=0, le=1)


class Alert(_Entity):
    message: str
    severity: str = "info"


class Edge(BaseModel):
    """A directed, typed, confidence-weighted relationship in the Decision Graph."""

    model_config = ConfigDict(extra="forbid")
    source_id: str
    target_id: str
    relation_type: RelationType
    confidence: float = Field(default=1.0, ge=0, le=1)
