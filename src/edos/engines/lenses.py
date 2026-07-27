"""Reasoning Lens library (Wave 2 · Step 2).

A *lens* is a domain reasoning-framework — the principal-level checks EDOS applies when a given embedded
concern is load-bearing for a decision. The library is **static in what it knows, dynamic in what it
weights**: importance is never baked platform-wide, it is derived per project+decision by the weighting
engine (Step 4) from the project's spine (Step 3).

Design (honours the CLAUDE.md invariant "prompts are versioned assets"):
  * the reasoning *frame* (the depth text) lives as a versioned markdown asset under
    ``prompts/lenses/<id>.md`` — loaded on demand, only when a lens is weighted high enough to go deep.
  * the *metadata* (spine affinities, structural triggers, one-line scan) lives here in code.

Every lens carries a ``scan_line`` even without a full frame: that is the **blind-spot floor** — a
low-weight lens is never dropped, it still gets a thin scan pass so weighting sets DEPTH, never gates a
concern off entirely.

Affinity keys are free-form ``"axis:value"`` strings matched against a project's spine dict by the weighting
engine; this module deliberately does not import the spine vocabulary, so the two evolve independently.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_FRAMES_DIR = Path(__file__).resolve().parents[1] / "prompts" / "lenses"


@dataclass(frozen=True)
class Lens:
    id: str
    title: str
    # "axis:value" -> how much that spine position raises this lens (0..~1). Summed by the weighting engine.
    affinities: dict[str, float]
    # substrings whose presence in project facts/BOM structurally raise this lens (the γ signal).
    structural_triggers: tuple[str, ...]
    # the blind-spot floor: one line always injected for a low-weight lens (never dropped).
    scan_line: str
    # baseline salience before any spine/topic signal (some concerns are always at least background).
    base: float = 0.15
    # filename under prompts/lenses/ holding the full reasoning frame; None => only scan_line exists yet.
    frame_file: str | None = None

    def load_frame(self) -> str | None:
        """The full reasoning frame text, or None if this lens has only a scan_line so far."""
        if not self.frame_file:
            return None
        path = _FRAMES_DIR / self.frame_file
        return path.read_text(encoding="utf-8").strip() if path.exists() else None


def _lens(*args, **kwargs) -> Lens:
    lens = Lens(*args, **kwargs)
    _REGISTRY[lens.id] = lens
    return lens


_REGISTRY: dict[str, Lens] = {}

# ----------------------------------------------------------------------------------------------------
# The library. Top-common decision types carry a full frame; all carry a scan_line (blind-spot floor).
# ----------------------------------------------------------------------------------------------------

# --- B1 compute & software realization ---
_lens("compute_tier", "Compute tier (MCU/RTOS/Linux/FPGA)",
      {"compute_tier:linux": 0.5, "compute_tier:hybrid": 0.5, "compute_tier:fpga": 0.4,
       "data_char:edge_ai": 0.3, "data_char:streaming": 0.3, "realtime:hard": 0.3},
      ("mcu", "soc", "processor", "cortex-a", "cortex-m", "risc-v", "linux", "rtos", "fpga", "som"),
      "Is the compute tier justified by the actual workload, or picked from familiarity? Could a lower tier meet it?",
      base=0.35, frame_file="compute_tier.md")

_lens("realtime_concurrency", "Real-time & concurrency",
      {"realtime:hard": 0.6, "realtime:firm": 0.4, "compute_tier:rtos": 0.3, "compute_tier:linux": 0.2,
       "data_char:control": 0.2},
      ("interrupt", "isr", "rtos", "scheduler", "deadline", "latency", "jitter", "dma", "mutex", "priority"),
      "Are the hard deadlines met with margin (WCET/jitter), and is Linux non-determinism kept off the critical loop?",
      frame_file="realtime_concurrency.md")

_lens("memory", "Memory (flash/RAM/DDR, map, NVM)",
      {"compute_tier:mcu": 0.3, "compute_tier:linux": 0.3, "data_char:streaming": 0.3,
       "data_char:edge_ai": 0.3},
      ("flash", "sram", "ram", "ddr", "eeprom", "nand", "emmc", "heap", "stack", "linker", "cache"),
      "Does the footprint fit with margin, and are stack/heap/NVM-wear/cache-coherency-with-DMA accounted for?",
      frame_file="memory.md")

_lens("firmware_arch", "Firmware architecture (boot, OTA, drivers)",
      {"connectivity:wireless": 0.3, "connectivity:wired": 0.2, "criticality:medical": 0.2,
       "criticality:automotive": 0.2, "compute_tier:linux": 0.2},
      ("bootloader", "ota", "firmware update", "a/b", "rollback", "hal", "driver", "state machine", "misra"),
      "Is there a safe update/rollback path and a clean boot/driver architecture, or is field-update an afterthought?",
      frame_file="firmware_arch.md")

_lens("debug_bringup", "Debug & bring-up (JTAG, trace, DFT)",
      {"volume:mass": 0.2, "criticality:medical": 0.2, "criticality:automotive": 0.2},
      ("jtag", "swd", "trace", "test point", "boundary scan", "watchdog", "fault handler", "rtt"),
      "Can this actually be brought up and debugged — test points, trace, fault handling, watchdog strategy?",
      frame_file="debug_bringup.md")

# --- B2 signal & electrical ---
_lens("peripherals_io", "Peripherals & I/O (buses, USB, MIPI, Ethernet)",
      {"data_char:streaming": 0.4, "connectivity:wired": 0.3, "data_char:sensor_fusion": 0.2},
      ("i2c", "spi", "uart", "can", "usb", "ethernet", "mipi", "csi", "dsi", "pcie", "pwm", "adc pin"),
      "Are bus bandwidth, pin-mux conflicts, and high-speed interfaces (USB/Ethernet/MIPI) actually feasible on this part?",
      frame_file="peripherals_io.md")

_lens("clocking_analog", "Clocking & analog/mixed-signal (ADC, sensors)",
      {"data_char:sensor_fusion": 0.4, "data_char:control": 0.2, "environment:harsh": 0.2},
      ("adc", "dac", "sensor", "crystal", "oscillator", "pll", "enob", "reference", "calibration", "amplifier"),
      "Do ADC resolution/ENOB, sampling/aliasing, references, clocking and calibration/drift hold over range?",
      frame_file="clocking_analog.md")

_lens("power", "Power (source, rails, regulation, low-power)",
      {"power_source:battery": 0.6, "power_source:harvesting": 0.7, "power_source:mains": 0.2,
       "environment:harsh": 0.2, "form_factor:wearable": 0.3},
      ("battery", "li-ion", "coin cell", "ldo", "buck", "boost", "pmic", "regulator", "power rail",
       "sleep", "low power", "voltage"),
      "Is there a real worst-case power budget, and do dissipation/thermal, sequencing and sleep residuals add up?",
      base=0.3, frame_file="power.md")

_lens("connectivity_rf", "Connectivity / RF (wireless, wired, antenna)",
      {"connectivity:wireless": 0.7, "connectivity:wired": 0.4, "markets:global": 0.2,
       "power_source:battery": 0.2},
      ("ble", "bluetooth", "wifi", "wi-fi", "zigbee", "thread", "lora", "cellular", "lte", "nb-iot",
       "antenna", "rf", "modem", "ethernet", "modbus", "can bus"),
      "Does the radio match traffic+power+range+region, and are stack/provisioning/antenna/coexistence handled?",
      base=0.2, frame_file="connectivity_rf.md")

# --- B3 physical realization ---
_lens("pcb", "PCB / layout / signal-integrity",
      {"data_char:streaming": 0.3, "compute_tier:linux": 0.3, "compute_tier:hybrid": 0.3,
       "connectivity:wireless": 0.3, "environment:harsh": 0.2, "form_factor:size_bound": 0.3},
      ("pcb", "layout", "stackup", "layer", "impedance", "trace", "via", "ground plane", "routing",
       "rigid-flex", "hdi"),
      "Are stackup, controlled-impedance nets, return paths, decoupling and DFM right — or will a good schematic fail in copper?",
      base=0.2, frame_file="pcb.md")

_lens("mechanical_enclosure", "Mechanical / enclosure / electro-mechanical",
      {"form_factor:sealed": 0.6, "form_factor:wearable": 0.5, "form_factor:size_bound": 0.4,
       "environment:harsh": 0.4},
      ("enclosure", "housing", "ip67", "ip68", "gasket", "seal", "connector", "mounting", "mechanical",
       "material", "waterproof", "drop", "vibration"),
      "Are enclosure fit/tolerances, IP sealing, connector mating, mounting and drop/vibration reasoned with the PCB, not after it?",
      frame_file="mechanical_enclosure.md")

_lens("thermal", "Thermal (dissipation, derating, heat path)",
      {"power_source:mains": 0.3, "environment:harsh": 0.4, "form_factor:sealed": 0.4,
       "data_char:edge_ai": 0.2},
      ("thermal", "heatsink", "temperature", "dissipation", "junction", "derating", "ambient", "cooling"),
      "Does ΔT=P·Rθ stay under junction/ambient limits with derating, and is the heat path real (esp. sealed/harsh)?",
      frame_file="thermal.md")

# --- B4 trust, supply & compliance ---
_lens("reliability_safety", "Reliability & functional safety",
      {"criticality:medical": 0.6, "criticality:automotive": 0.6, "criticality:avionics": 0.7,
       "criticality:industrial": 0.3, "environment:harsh": 0.3},
      ("safety", "fmea", "iso 26262", "iec 61508", "iec 62304", "do-178", "redundancy", "watchdog",
       "ecc", "crc", "esd", "surge", "fault"),
      "Do the safety class's failure-modes, safe-states, redundancy and immunity (ESD/EMC) get first-class treatment?",
      frame_file="reliability_safety.md")

_lens("security", "Security (secure boot, keys, update signing)",
      {"connectivity:wireless": 0.4, "criticality:medical": 0.3, "criticality:industrial": 0.3,
       "markets:eu": 0.2},
      ("secure boot", "encryption", "key", "tpm", "secure element", "crypto", "signing", "rdp",
       "readout protection", "attack", "cve", "certificate"),
      "Is there a root-of-trust, key storage, signed updates and debug-lock — or is the connected device an open target?",
      frame_file="security.md")

_lens("certification", "Certification / compliance",
      {"criticality:medical": 0.5, "criticality:automotive": 0.4, "criticality:industrial": 0.3,
       "connectivity:wireless": 0.4, "markets:eu": 0.3, "markets:us": 0.3, "markets:global": 0.4,
       "power_source:mains": 0.2},
      ("emc", "fcc", "ce", "ul", "rohs", "reach", "certification", "compliance", "red", "ce mark",
       "regulatory", "standard"),
      "Is the cert scope (EMC/radio/safety/environmental) named for the target markets, with test-house lead time as a schedule item?",
      base=0.2, frame_file="certification.md")

_lens("manufacturing", "Manufacturing / production-test (DFM, provisioning)",
      {"volume:mass": 0.6, "volume:low": 0.3, "criticality:automotive": 0.2},
      ("dfm", "assembly", "production", "provisioning", "serialization", "ict", "functional test",
       "yield", "programming", "calibration line"),
      "Are DFM, production programming/provisioning, test coverage and yield designed in for the target volume?",
      frame_file="manufacturing.md")

# --- B5 cross-cutting (weighting engine treats these as CONSTRAINTS applied over the result) ---
_lens("bom_supply", "BOM availability / supply-chain / lifecycle",
      {"volume:mass": 0.4, "volume:low": 0.2, "criticality:automotive": 0.3, "criticality:medical": 0.2},
      ("stock", "lead time", "eol", "nrnd", "allocation", "second source", "obsolete", "availability",
       "shortage", "lifecycle", "moq"),
      "Can every chosen part actually be sourced at volume and over the product's life — or is the 'best' part a supply veto risk?",
      base=0.3, frame_file="bom_supply.md")

_lens("cost", "Cost-at-volume (whole-BOM, NRE vs unit)",
      {"volume:mass": 0.5, "volume:low": 0.2, "criticality:consumer": 0.3},
      ("cost", "bom cost", "unit price", "nre", "budget", "target price", "margin"),
      "Does the whole-BOM cost at the target volume (not the single part) fit, with NRE vs unit-cost traded honestly?",
      base=0.25, frame_file="cost.md")


def get_lens(lens_id: str) -> Lens | None:
    return _REGISTRY.get(lens_id)


def all_lenses() -> list[Lens]:
    return list(_REGISTRY.values())


def lens_ids() -> list[str]:
    return list(_REGISTRY.keys())
