"""Prompt Registry (roadmap Ch 9/16).

Prompts are versioned software assets, not inline strings. Each entry declares its purpose, compatible
models, output schema, token budget, and the template file that holds its text. Reasoning templates share a
single `erc_core.md` block (substituted for `{{ERC_CORE}}`) so the engineering principles stay in one place.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_TEMPLATES = _HERE / "templates"
_CONTRACTS_DIR = _HERE.parents[2] / "contracts"
_ERC_MARKER = "{{ERC_CORE}}"


def known_schema_ids() -> set[str]:
    """Valid `output_schema` values: the locked contract $ids, plus 'none' for non-contract prompts."""
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
    template: str       # filename under prompts/templates/

    @property
    def ref(self) -> str:
        return f"{self.id}:{self.version}"


_REGISTRY: dict[str, PromptSpec] = {}


def register(spec: PromptSpec) -> PromptSpec:
    if spec.output_schema not in known_schema_ids():
        raise ValueError(f"{spec.ref}: unknown output_schema {spec.output_schema!r}")
    if not (_TEMPLATES / spec.template).exists():
        raise ValueError(f"{spec.ref}: template file not found: {spec.template}")
    _REGISTRY[spec.ref] = spec
    return spec


def get(ref: str) -> PromptSpec:
    return _REGISTRY[ref]


def all_specs() -> list[PromptSpec]:
    return list(_REGISTRY.values())


def load_template(ref: str) -> str:
    """Return the fully-composed prompt text (with ERC core substituted where used)."""
    spec = get(ref)
    text = (_TEMPLATES / spec.template).read_text(encoding="utf-8")
    if _ERC_MARKER in text:
        core = (_TEMPLATES / "erc_core.md").read_text(encoding="utf-8")
        text = text.replace(_ERC_MARKER, core.strip())
    return text


# --- Registered production prompts (v1) ---
register(PromptSpec("planner_prompt", "v1", "Detect intent/complexity/needs (lightweight routing)",
                    ("claude-haiku-4-5", "gpt-5-nano"), "none", 800, "planner_prompt.v1.md"))
register(PromptSpec("decision_prompt", "v1", "Engineering decision analysis over a context package",
                    ("claude-opus-4-8", "gpt-5"), "edos.decision.v1", 6000, "decision_prompt.v1.md"))
register(PromptSpec("verification_prompt", "v1", "Critique a decision; never regenerate",
                    ("claude-opus-4-8", "claude-sonnet-5"), "none", 3000, "verification_prompt.v1.md"))
register(PromptSpec("knowledge_extraction_prompt", "v1", "Extract structured knowledge from a decision",
                    ("claude-sonnet-5", "gpt-5-mini"), "none", 2000, "knowledge_extraction_prompt.v1.md"))
