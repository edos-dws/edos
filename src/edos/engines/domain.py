"""Domain grounding + procedural memory (CP-20).

Two parts:
1. **Procedural memory** — general embedded-engineering heuristics (rules) that reasoning applies to flag
   things an engineer should not miss. These are general domain knowledge (not copyrighted content).
2. **Domain source grounding** — ingesting authoritative external sources (datasheets, standards, part DBs)
   reuses the CP-12 ingestion pipeline with `item_type="external"`. Shipping specific copyrighted sources is
   **deferred (OD-9, licensing)** — the platform ingests whatever licensed content you provide.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    key: str
    triggers: tuple[str, ...]
    flag: str
    severity: str = "info"
    # Findings mapping (UI-CP-3): which finding category this rule produces, a short human title, and the
    # concrete consequences that populate a finding's "IF YOU IGNORE THIS" box. `category` is one of
    # hidden_dependency|best_practice (rules only ever produce those two — the LLM owns assumption/optimization).
    category: str = "hidden_dependency"
    title: str = ""
    consequences: tuple[str, ...] = ()


# General engineering heuristics (procedural memory). Extend freely.
RULES: tuple[Rule, ...] = (
    Rule("automotive-grade", ("automotive", "-40", "125c", "105c", "under-hood"),
         "Automotive temp range implies an AEC-Q100 qualified part — confirm grade.", "high",
         category="hidden_dependency", title="Automotive-grade part qualification",
         consequences=("Non-qualified silicon fails automotive AEC-Q100 review",
                       "Late re-selection to a qualified part · added cost + schedule slip")),
    Rule("high-impedance-afe", ("ph", "high-impedance", "glass electrode", "na-level", "nanoamp", "picoamp"),
         "High-impedance / nA-level sensing needs a precision AFE (low input-bias buffer / TIA), not raw MCU ADC.",
         "high", category="hidden_dependency", title="Precision analog front-end required",
         consequences=("Raw MCU ADC gives noisy, unusable readings",
                       "PCB re-spin to add a precision AFE (buffer / TIA)")),
    Rule("ac-excitation", ("tds", "conductivity", "ec sensor"),
         "Conductivity/TDS needs AC excitation to avoid DC electrode polarization.", "medium",
         category="hidden_dependency", title="AC excitation for conductivity sensing",
         consequences=("DC electrode polarization corrupts the measurement",
                       "Sensor front-end redesign mid-program")),
    Rule("power-budget", ("battery", "mah", "18650", "coin cell", "always-on"),
         "Battery + duty cycle: run a power budget (sleep vs active current) against the runtime target.",
         "medium", category="best_practice", title="Power budget vs runtime target",
         consequences=("Runtime target missed once units are in the field",
                       "Battery / enclosure resize late in the program")),
    Rule("radio-mcu", ("lorawan", "lora", "ble", "zigbee", "can 2.0", "wifi"),
         "Connectivity requirement gates MCU/SoC choice (integrated radio vs external transceiver).", "info",
         category="hidden_dependency", title="Connectivity gates MCU/SoC choice",
         consequences=("MCU chosen without the required radio → re-selection",
                       "Firmware / protocol-stack rework for the new part")),
)


@dataclass
class RuleFlag:
    key: str
    flag: str
    severity: str
    matched: str


def apply_rules(contents: Iterable[str]) -> list[RuleFlag]:
    """Scan item contents against the procedural-memory rules; return flags for matches."""
    flags: list[RuleFlag] = []
    seen: set[str] = set()
    for content in contents:
        low = content.lower()
        for rule in RULES:
            if rule.key in seen:
                continue
            hit = next((t for t in rule.triggers if t in low), None)
            if hit:
                flags.append(RuleFlag(key=rule.key, flag=rule.flag, severity=rule.severity, matched=hit))
                seen.add(rule.key)
    return flags
