"""Context extraction (auto-bootstrap) — pull structured context out of what the engineer said.

The engineer shouldn't have to fill forms. When they ask a question or describe the problem, the LLM extracts
the **requirements / assumptions / constraints / components** implied by that text; those become project
items (graph nodes + embeddings) that the Retriever then reasons over. The engineer can still add more by hand.

Live: uses the Model Router (real LLM). Offline/stub or on malformed output: a deterministic keyword
heuristic so the flow always produces *something* usable and tests stay green.
"""
from __future__ import annotations

import re

from edos.engines.model_router import Capability, ModelRouter

EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"type": {"type": "string"}, "content": {"type": "string"}},
                "required": ["type", "content"],
            },
        }
    },
    "required": ["items"],
}

_VALID = {"requirement", "decision", "assumption", "document"}
_REQ_KW = (
    "must", "shall", "need", "require", "support", "measure", "read", "target", "under", "below",
    "at least", "at most", "min ", "max ", "battery", "sensor", "mcu", "soc", "ble", "can ", "lora",
    "wifi", "cost", "bom", "temp", "accuracy", "runtime", "voltage", "current", "adc", "mah", "power",
)
_ASSUM_KW = ("assume", "assumed", "assuming", "probably", "likely", "expected", "should be", "presumably")


def _norm_type(t: str) -> str:
    t = (t or "").lower().strip()
    if t in _VALID:
        return t
    if t in ("constraint", "spec", "requirement"):
        return "requirement"
    if t in ("assumption",):
        return "assumption"
    return "requirement"


def _heuristic(text: str) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for clause in re.split(r"[;.\n?]|,| and ", text):
        c = clause.strip(" -\t")
        low = c.lower()
        if len(c) < 6:
            continue
        if any(k in low for k in _ASSUM_KW):
            kind = "assumption"
        elif any(k in low for k in _REQ_KW):
            kind = "requirement"
        else:
            continue
        if low not in seen:
            seen.add(low)
            items.append({"type": kind, "content": c})
    return items


def extract(text: str, router: ModelRouter | None = None) -> list[dict]:
    """Return [{type, content}] extracted from free-text. LLM first, heuristic fallback."""
    router = router or ModelRouter()
    try:
        out = router.execute(Capability.knowledge_extraction, {"text": text}, schema=EXTRACTION_SCHEMA)
        raw = out.get("items") if isinstance(out, dict) else None
        items = [
            {"type": _norm_type(i.get("type", "")), "content": i["content"].strip()}
            for i in (raw or []) if isinstance(i, dict) and i.get("content")
        ]
        if items:
            return items
    except Exception:  # noqa: BLE001, S110 — any LLM/validation failure falls back to the heuristic below
        pass
    return _heuristic(text)
