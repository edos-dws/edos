"""Prompt Engine — output validation + repair loop (roadmap Ch 9).

All production LLM outputs are JSON validated against a contract. Malformed output is repaired or rejected,
**never persisted**.
"""
from __future__ import annotations

from collections.abc import Callable

import jsonschema


class MalformedOutputError(Exception):
    """No schema-valid output survived generate → repair → fallback. The caller MUST NOT persist anything."""


def produce_valid(schema: dict, attempts: list[Callable[[], dict]]) -> dict:
    """Return the first attempt whose output satisfies `schema`.

    `attempts` is ordered: typically [generate, repair-retry, fallback-model] (Ch 9). If none validate,
    raise `MalformedOutputError` — the caller must not write anything to storage.
    """
    last: Exception | None = None
    for produce in attempts:
        candidate = produce()
        try:
            jsonschema.validate(instance=candidate, schema=schema)
            return candidate
        except jsonschema.ValidationError as exc:
            last = exc
    raise MalformedOutputError("no schema-valid output after repair + fallback") from last
