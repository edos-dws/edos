"""Deterministic rule expansion (roadmap Ch 5/15).

Applies fixed engineering rules to expand entities into related concerns — WITHOUT another LLM call.
E.g. an MCU change implies drivers, bootloader, clock tree, power profile, RTOS config.
"""
from __future__ import annotations

from collections.abc import Iterable

EXPANSION_RULES: dict[str, list[str]] = {
    "mcu": ["drivers", "bootloader", "clock_tree", "power_profile", "rtos_config"],
    "battery": ["power_budget"],
    "protocol": ["certification"],
}


def expand(entities: Iterable[str]) -> list[str]:
    """Related concerns triggered by the given entities (deduped, order-preserving)."""
    out: list[str] = []
    for entity in entities:
        key = str(entity).lower()
        for trigger, items in EXPANSION_RULES.items():
            if trigger in key:
                for item in items:
                    if item not in out:
                        out.append(item)
    return out
