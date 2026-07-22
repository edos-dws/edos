"""Prompt Registry (roadmap Ch 9/16).

Prompts are versioned software assets, not inline strings. Each entry declares its purpose, compatible
models, output schema, and token budget. CP-2 seeds the metadata; prompt *content* is authored/tuned at CP-4.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_CONTRACTS_DIR = Path(__file__).resolve().parents[3] / "contracts"


def known_schema_ids() -> set[str]:
    """Valid `output_schema` values: the locked contract $ids, plus 'none' for non-JSON prompts."""
    ids = {"none"}
    for f in _CONTRACTS_DIR.glob("*.schema.json"):
        with open(f, encoding="utf-8") as fh:
            ids.add(json.load(fh)["$id"])
    return ids


@dataclass(frozen=True)
class PromptSpec:
    id: str
    version: str
    purpose: str
    compatible_models: tuple[str, ...]
    output_schema: str  # a contract $id or "none"
    token_budget: int

    @property
    def ref(self) -> str:
        return f"{self.id}:{self.version}"


_REGISTRY: dict[str, PromptSpec] = {}


def register(spec: PromptSpec) -> PromptSpec:
    if spec.output_schema not in known_schema_ids():
        raise ValueError(f"{spec.ref}: unknown output_schema {spec.output_schema!r}")
    _REGISTRY[spec.ref] = spec
    return spec


def get(ref: str) -> PromptSpec:
    return _REGISTRY[ref]


def all_specs() -> list[PromptSpec]:
    return list(_REGISTRY.values())


# --- Seeded prompt registry (metadata only; content tuned at CP-4) ---
register(PromptSpec("planner_prompt", "v0.1", "Detect intent/complexity/needs",
                    ("claude-haiku-4-5", "gpt-5-nano"), "none", 800))
register(PromptSpec("decision_prompt", "v0.1", "Engineering decision analysis over a context package",
                    ("claude-opus-4-8", "gpt-5"), "edos.decision.v1", 6000))
register(PromptSpec("verification_prompt", "v0.1", "Critique a decision; never regenerate",
                    ("claude-opus-4-8", "claude-sonnet-5"), "edos.decision.v1", 3000))
register(PromptSpec("knowledge_extraction_prompt", "v0.1", "Extract structured knowledge from a decision",
                    ("claude-sonnet-5", "gpt-5-mini"), "none", 2000))
