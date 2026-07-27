"""Project SPINE classifier (Wave 2 · Step 3).

The spine is a project's **direction fingerprint** — its position on the ~10 architecture-defining axes.
Fix the spine first and most downstream lens weights fall out causally (a battery + wireless + medical
project weights power, RF-cert and safety-process high before any per-lens scoring).

Discipline (CLAUDE.md truth rule): we **derive** axis values from real project signal, and where there is no
signal the axis stays **unknown and is asked** — never guessed. Classification is a pure function of the
project's text corpus, so answered framing questions (which land back in the context as items/answers)
feed the next classification automatically — no separate storage.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache


@lru_cache(maxsize=4096)
def _term_pattern(term: str) -> re.Pattern:
    # Whole-term match on a letter/digit boundary. Trigger substrings are meant as words/phrases, so a bare
    # ``in`` test produced false hits — "rf" inside "surface", "ecu" inside "secure", "npu" inside "input",
    # "pid" inside "rapid" — which silently corrupted the classification. Boundaries fix that while still
    # allowing punctuation/space-adjacent forms ("wi-fi", "-40", "iso 26262", "car ").
    return re.compile(r"(?<![a-z0-9])" + re.escape(term.strip()) + r"(?![a-z0-9])")


def count_term(text: str, term: str) -> int:
    """Number of whole-term occurrences of ``term`` in ``text`` (both already lowercased)."""
    return len(_term_pattern(term).findall(text))


def contains_term(text: str, term: str) -> bool:
    """Whether ``term`` occurs as a whole term in ``text`` (both already lowercased)."""
    return _term_pattern(term).search(text) is not None


# ----------------------------------------------------------------------------------------------------
# The spine vocabulary. Each axis: its allowed values, a framing question (asked only when unknown), and
# how direction-defining it is (importance) — used to order which unknowns are worth asking first.
# ----------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Axis:
    key: str
    values: tuple[str, ...]
    question: str
    importance: float


SPINE_AXES: tuple[Axis, ...] = (
    Axis("compute_tier", ("mcu", "rtos", "linux", "hybrid", "fpga", "dsp"),
         "What is the compute tier — a bare-metal MCU, an RTOS, an MPU running Linux, a heterogeneous mix, or an FPGA?",
         1.0),
    Axis("realtime", ("hard", "soft", "firm", "none"),
         "Does the system have hard real-time deadlines (missing one fails), soft, or none?", 0.9),
    Axis("power_source", ("mains", "battery", "harvesting"),
         "Is it mains-powered, battery-powered, or energy-harvesting?", 0.9),
    Axis("connectivity", ("none", "wired", "wireless"),
         "How does it communicate — none, wired, or wireless (and which radio)?", 0.9),
    Axis("criticality", ("consumer", "industrial", "medical", "automotive", "avionics"),
         "What is the criticality class — consumer, industrial, medical, automotive, or avionics/rail?", 0.9),
    Axis("volume", ("one_off", "low", "mass"),
         "What is the production volume — one-off/prototype, low, or mass?", 0.7),
    Axis("data_char", ("control", "streaming", "sensor_fusion", "edge_ai"),
         "What is the data character — control-only, streaming (camera/audio), sensor-fusion, or edge-AI?", 0.7),
    Axis("environment", ("benign", "harsh"),
         "Is the operating environment benign or harsh (wide temperature, vibration, moisture/IP, high EMC)?", 0.6),
    Axis("markets", ("us", "eu", "global"),
         "Which markets/regions are targeted (drives certification scope) — US, EU, or global?", 0.6),
    Axis("form_factor", ("unconstrained", "size_bound", "wearable", "sealed"),
         "Is the form-factor unconstrained, size/shape-bound, wearable, or sealed/rugged?", 0.6),
)

# "axis:value" -> substrings that signal that value in the project corpus. Absence => the axis stays unknown.
_VALUE_TRIGGERS: dict[str, tuple[str, ...]] = {
    "compute_tier:linux": ("linux", "yocto", "buildroot", "u-boot", "device tree", "cortex-a", "imx", "rootfs"),
    "compute_tier:rtos": ("freertos", "zephyr", "threadx", "rt-thread", "rtos", "ucos"),
    "compute_tier:fpga": ("fpga", "zynq", "verilog", "vhdl", "soft-core"),
    "compute_tier:dsp": ("dsp", "sharc", "c6000", "audio dsp"),
    "compute_tier:hybrid": ("heterogeneous", "rpmsg", "remoteproc", "amp core", "cortex-a + cortex-m"),
    "compute_tier:mcu": ("cortex-m", "stm32", "atmega", "avr", "msp430", "pic", "bare-metal", "bare metal"),
    "realtime:hard": ("hard real-time", "hard real time", "deterministic", "motor control", "safety loop",
                      "wcet", "control loop"),
    "realtime:soft": ("soft real-time", "soft real time", "best effort latency"),
    "realtime:none": ("no real-time", "not real-time", "batch"),
    "power_source:battery": ("battery", "li-ion", "lipo", "coin cell", "cr2032", "rechargeable", "mah"),
    "power_source:harvesting": ("energy harvesting", "solar", "harvest", "thermoelectric", "piezo"),
    "power_source:mains": ("mains", "wall power", "ac-dc", "230v", "120v", "plugged", "line-powered"),
    "connectivity:wireless": ("ble", "bluetooth", "wifi", "wi-fi", "zigbee", "thread", "lora", "cellular",
                              "lte", "nb-iot", "sub-ghz", "wireless", "rf", "antenna"),
    "connectivity:wired": ("ethernet", "rs-485", "rs485", "modbus", "can bus", "canbus", "usb", "wired",
                           "profinet", "ethercat"),
    "connectivity:none": ("no connectivity", "standalone", "air-gapped", "offline device"),
    "criticality:medical": ("medical", "iec 62304", "iso 13485", "patient", "fda", "clinical"),
    "criticality:automotive": ("automotive", "iso 26262", "asil", "vehicle", "car ", "ecu"),
    "criticality:avionics": ("avionics", "do-178", "aerospace", "rail ", "en 50128", "sil 4"),
    "criticality:industrial": ("industrial", "iec 61508", "factory", "plc", "scada", "din rail"),
    "criticality:consumer": ("consumer", "wearable", "toy", "smart home", "gadget"),
    "volume:mass": ("mass production", "high volume", "millions", "100k", "1m units", "consumer volume"),
    "volume:low": ("low volume", "small batch", "hundreds", "1k units"),
    "volume:one_off": ("prototype", "one-off", "one off", "proof of concept", "single unit"),
    "data_char:streaming": ("camera", "video", "audio stream", "mipi", "csi", "streaming", "image sensor"),
    "data_char:sensor_fusion": ("sensor fusion", "imu", "multiple sensors", "kalman"),
    "data_char:edge_ai": ("edge ai", "tinyml", "inference", "neural", "npu", "ml model", "tflite"),
    "data_char:control": ("control loop", "actuator", "pid", "motor"),
    "environment:harsh": ("ip67", "ip68", "waterproof", "outdoor", "automotive grade", "industrial temp",
                          "vibration", "-40", "harsh", "rugged", "submersible"),
    "environment:benign": ("indoor", "office", "benign", "controlled environment"),
    "markets:global": ("global", "worldwide", "multi-region", "international"),
    "markets:eu": ("europe", "eu ", "ce mark", "ce marking", "red directive", "cra "),
    "markets:us": ("usa", "united states", "fcc", "ul listing", "north america"),
    "form_factor:sealed": ("ip67", "ip68", "sealed", "waterproof", "potted", "rugged enclosure"),
    "form_factor:wearable": ("wearable", "wrist", "on-body", "watch", "band"),
    "form_factor:size_bound": ("tiny", "compact", "space-constrained", "small pcb", "size constraint", "fit in"),
    "form_factor:unconstrained": ("no size constraint", "desktop", "rack", "large enclosure"),
}

@dataclass
class SpineResult:
    values: dict[str, str]          # axis -> derived value (only confident axes present)
    unknown: list[str]              # axes with no signal — to be asked, never guessed
    signals: dict[str, int]         # "axis:value" -> hit count (audit trail; non-fabricated basis)

    def as_prompt_lines(self) -> list[str]:
        """Human/LLM-readable fingerprint lines for the prompt (only what we actually derived)."""
        lines = [f"{axis}: {self.values[axis]}" for axis in (a.key for a in SPINE_AXES) if axis in self.values]
        if self.unknown:
            lines.append("unknown (not yet established): " + ", ".join(self.unknown))
        return lines


def classify(corpus: str) -> SpineResult:
    """Derive the spine from a project's text corpus. Pure + deterministic — no LLM, no fabrication.

    For each axis, count trigger hits per candidate value; the value with the most hits wins that axis. An
    axis with zero hits stays **unknown** (to be asked). Ties or thin signal still resolve to the top hit but
    the raw counts are returned so callers can see how thin the basis was.
    """
    text = corpus.lower()
    signals: dict[str, int] = {}
    for key, triggers in _VALUE_TRIGGERS.items():
        hits = sum(count_term(text, t) for t in triggers)
        if hits:
            signals[key] = hits

    values: dict[str, str] = {}
    unknown: list[str] = []
    for axis in SPINE_AXES:
        best_val, best_hits = None, 0
        for val in axis.values:
            h = signals.get(f"{axis.key}:{val}", 0)
            if h > best_hits:
                best_val, best_hits = val, h
        if best_val is not None:
            values[axis.key] = best_val
        else:
            unknown.append(axis.key)
    return SpineResult(values=values, unknown=unknown, signals=signals)


def framing_questions(result: SpineResult, max_q: int = 3) -> list[dict[str, str]]:
    """The short framing intake for the most direction-defining UNKNOWN axes — ask, don't guess.

    Returns at most ``max_q`` `{axis, q}` items, ordered by axis importance. Known axes are never re-asked.
    """
    unknown_axes = sorted(
        (a for a in SPINE_AXES if a.key in result.unknown),
        key=lambda a: a.importance, reverse=True,
    )
    return [{"axis": a.key, "q": a.question} for a in unknown_axes[:max_q]]


def classify_project(session, project_id: str) -> SpineResult:
    """Convenience: gather the project's item corpus and classify. Best-effort — any failure => empty spine
    (all axes unknown), which simply means the framing intake will ask everything."""
    try:
        from sqlalchemy import select

        from edos.db.models import ProjectItem
        rows = session.scalars(
            select(ProjectItem.content).where(ProjectItem.project_id == project_id)
        ).all()
        corpus = "\n".join(r for r in rows if r)
    except Exception:  # noqa: BLE001 — classification is advisory; never break a decision on it
        corpus = ""
    return classify(corpus)
