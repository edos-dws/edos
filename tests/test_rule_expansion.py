"""Ticket 4.3 — deterministic rule expansion (no LLM)."""
from edos.engines.rules import expand


def test_mcu_expands_to_required_related_items():
    result = expand(["STM32 MCU change"])
    assert {"drivers", "bootloader", "clock_tree", "power_profile", "rtos_config"}.issubset(set(result))


def test_battery_expands_to_power_budget():
    assert "power_budget" in expand(["battery pack sizing"])


def test_no_trigger_returns_empty():
    assert expand(["paint colour"]) == []


def test_deduplicated():
    result = expand(["mcu", "the main mcu"])
    assert result.count("drivers") == 1
