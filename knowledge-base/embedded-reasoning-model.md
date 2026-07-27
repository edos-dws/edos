# EDOS Embedded Reasoning Model — Spine + Lens Library

> **Status: IMPLEMENTED.** Spine (`spine.py`), lens library (`lenses.py`), weighting (`lens_weighting.py`)
> and scaffold (`reasoning_scaffold.py`) are built, wired into the deep-dive decide path, and tested. **9 of
> the 18 lenses now carry a full reasoning frame** (`prompts/lenses/*.md`); the rest carry a scan-line
> (blind-spot floor). For the end-to-end working walkthrough see **[`how-edos-reasons.md`](./how-edos-reasons.md)**.
> This doc is the design/taxonomy reference behind that implementation.

> **Purpose.** This is the source of EDOS's *embedded-specific* reasoning. It answers two questions for
> every project and every Deep Dive:
> 1. **Which direction is this project going?** (the SPINE — architecture-defining axes)
> 2. **Given that direction + this decision, what should EDOS reason hardest about?** (the LENS weights)
>
> The library is **static in what it knows, dynamic in what it weights.** We never bake a generic
> platform-wide importance. Importance is *derived per project* from the spine, then refined by the specific
> decision. This file is **living** — new domains (edge-AI, EU-CRA, TSN) get added; it is versioned.

---

## Part A — The SPINE (project "direction fingerprint")

Every embedded project sits on these architecture-defining axes. Fix these first; most downstream lens
weights fall out *causally*. Unknown axes are **asked** in a short framing intake — never guessed.

| # | Spine axis | Values | What it derives downstream |
|---|---|---|---|
| 1 | **Compute tier** | bare-metal MCU · RTOS · MPU+Linux · heterogeneous/AMP · FPGA/SoC-FPGA · DSP-centric | memory model, boot, RT capability, driver ecosystem, security model, power |
| 2 | **Real-time class** | hard · soft · firm · none | scheduling, WCET, ISR design, *whether Linux is even viable* |
| 3 | **Power source** | mains · battery · energy-harvesting | low-power centrality, energy budget, thermal, supervisory |
| 4 | **Connectivity + topology** | none · wired · wireless(which) · single-node/star/mesh · connected/air-gapped | RF, protocol stack, radio cert, attack surface, antenna, OTA model |
| 5 | **Criticality class** | consumer · industrial · medical · automotive · avionics/rail | standards, redundancy, process rigor, documentation burden |
| 6 | **Production volume** | one-off · low · mass | DFM, cost sensitivity, provisioning/test, second-source rigor |
| 7 | **Data character** | control-only · streaming (camera/audio) · sensor-fusion · edge-AI | bandwidth, DMA, memory, accelerators |
| 8 | **Environment** | benign · harsh (temp-grade/vibration/humidity/IP/EMC) | derating, protection, environmental cert |
| 9 | **Target markets / regions** | e.g. US(FCC/UL) · EU(CE/RED/CRA) · global | certification *scope* and cost/schedule |
| 10 | **Form-factor / mechanical constraint** | unconstrained · size/shape-bound · wearable · sealed/rugged | PCB size & layer count, enclosure, connectors, thermal path |

---

## Part B — The LENS LIBRARY (the reasoning frameworks)

Each lens carries the **principal-level checks** for its domain — the non-obvious things that break teams,
not textbook basics. (`reasoning_frame` here is a v0 stub — one line of the sharpest checks; full frames get
written per lens.) Grouped into the two halves of embedded so neither is under-served.

### B1 — Compute & software realization
- **Compute/architecture** — MCU-vs-RTOS-vs-Linux-vs-FPGA fit; heterogeneous partitioning (which core does what, RPMsg); *is the chosen tier over/under-powered for the real workload?*
- **Real-time & concurrency** — hard/soft budget, WCET, ISR & nested-interrupt design, priority inversion/inheritance, scheduling (RMS/EDF), races/reentrancy, DMA-vs-CPU movement.
- **Memory** — flash/SRAM/TCM/DDR sizing, linker/sections, per-task stack, heap fragmentation, **cache coherency with DMA**, MPU/MMU regions, NVM wear-leveling, power-fail-safe writes, fitting-the-footprint.
- **Firmware architecture** — bootloader/boot-flow, **OTA (A/B, delta, rollback, fail-safe)**, HAL/driver layering, superloop-vs-RTOS, state machines, MISRA/CERT-C, static-analysis/coverage, toolchain/CI.
- **Debug & bring-up** — JTAG/SWD, trace (ETM/ITM/SWO/RTT), HardFault/core-dump, watchdog strategy, **DFT/test-points/boundary-scan**, in-field telemetry. *Can this even be brought up and debugged?*

### B2 — Signal & electrical
- **Peripherals & I/O** — I2C/SPI/QSPI/UART/**CAN-FD**/LIN/RS-485/I3C, USB device-host-OTG, Ethernet MAC/PHY, **MIPI CSI/DSI**, PCIe, timers/PWM/encoder, pin-mux conflicts.
- **Clocking & analog/mixed-signal** — crystal/PLL/clock-domains/jitter, ADC/DAC (ENOB, sample-rate, aliasing, oversampling, reference), sensor conditioning, calibration/drift/temp-comp, signal integrity/grounding.
- **Power** — rails/domains/sequencing, LDO-vs-SMPS, low-power modes + wake sources, energy/battery-life budget, brown-out/supervisory, DVFS.
- **Connectivity / RF** — BLE/Wi-Fi/Thread/Zigbee/LoRa/UWB/cellular, TCP-IP/MQTT/CoAP, industrial (Modbus/EtherCAT/PROFINET/TSN), antenna/RF-match, coexistence.

### B3 — Physical realization  *(the half I had under-weighted — added from your correction)*
- **PCB / layout / signal-integrity** — layer count & stackup, controlled impedance (USB/Ethernet/MIPI), length-matching/diff-pairs, **return paths & ground planes**, power-plane decoupling, thermal copper, board size/form-factor, DFM (trace/space/via/annular-ring), flex/rigid-flex/HDI, crystal & antenna keep-outs.
- **Mechanical / enclosure / electro-mechanical** — enclosure & material, **IP sealing/gaskets**, connector selection & mating cycles, mounting/standoffs, **PCB↔enclosure fit & tolerances**, thermal-mechanical (heatsink/pad), drop/vibration, buttons/membrane, display bonding, cable/harness.
- **Thermal** *(spans electrical+mechanical)* — ΔT = P·Rθ vs junction/ambient limits, derating, airflow/conduction path, hot-spot vs enclosure.

### B4 — Trust, supply & compliance
- **Reliability & functional safety** — IEC 61508 / ISO 26262 / IEC 62304 / DO-178C / EN 50128, FMEA/FMEDA, safe-states/redundancy/lockstep, ECC/CRC, EMC-immunity/ESD/surge/latch-up, temp-grade.
- **Security** — secure boot/root-of-trust, SE/TPM/HSM, key-storage/TRNG/crypto-accel, signed FW update, **RDP/debug-lock/lifecycle states**, side-channel/fault-injection, IEC 62443 / EU-CRA / ETSI EN 303 645.
- **Certification / compliance** *(elevated to first-class)* — EMC (FCC-15/CISPR/CE), radio (FCC/IC/RED, regional), safety (UL/IEC), environmental (RoHS/REACH), industry-specific. **Reason about it as a schedule, not just a checklist**: test-house lead time is often the real critical path; design-for-cert (pre-scan) beats fail-at-cert.
- **Manufacturing / production-test** — DFM/DFA/DFT, production programming/provisioning/serialization/**key-injection**, ICT/functional-test/calibration, yield/traceability.

### B5 — Cross-cutting constraints  *(NOT lenses — they OVERRIDE)*
- **BOM availability / supply-chain / lifecycle** — stock, lead-time, NRND/EOL, allocation, second-source. **This can VETO the technically-best part.** Treated as a hard constraint over the decision, not a soft factor.
- **Cost-at-volume** — whole-BOM view at the target volume, NRE vs unit cost, the cost the *volume axis* implies.

### B6 — Specialized sub-domains (pulled in only when the spine calls them)
Motor control / power-electronics (FOC, gate drivers, current sense) · edge-AI / TinyML (quantization, NPU, inference budget) · display/HMI (LVGL, framebuffer, touch) · audio (I2S, codec, DSP) · time-sync (PTP/1588).

---

## Part C — Physical-realization coupling  *(principal insight)*

These do **not** get weighted independently — they co-vary as one cluster:

```
form-factor ─┬─ PCB (size, layers, connectors) ─┬─ thermal path ─┬─ enclosure & IP ─┬─ EMC/radio cert
             └──────────── change one, the others move ───────────────────────────┘
```
A decision touching any node must reason about the ripple into the rest of the cluster.

---

## Part D — Weighting model (how importance is derived, NOT baked)

```
weight(lens) = f_spine(lens, project_spine)          # Layer 1: causal derivation from direction
             + β · topic_relevance(lens, decision)   # Layer 2: this specific decision
             + γ · structural_hits(lens, project_bom_facts)   # actual components present
             + δ · learned(lens, similar_spine)       # feedback loop: what mattered before
   subject to:
     • BOM-availability & cost are CONSTRAINTS applied over the result, not summed in.
     • coverage% low  ⇒ weights flatter (don't over-commit on thin context).
     • BLIND-SPOT FLOOR: every lens keeps a thin scan pass — weighting sets DEPTH, never gates a lens off.
     • weights are SHOWN to the engineer and OVERRIDABLE.
```

Prompt assembly per Deep Dive:
```
prompt = ERC_CORE (4-archetype brain + method + break-the-loop)
       + spine fingerprint
       + top-weighted lenses  → full reasoning_frame   (DEPTH)
       + remaining lenses     → one-line scan prompt    (BLIND-SPOT FLOOR)
       + applied constraints (BOM/cost) + shown weights (overridable)
```

---

## Build status (living)
- **Wave 1 — ERC brain:** DONE. `erc_core.md` upgraded to the 4-archetype composite (senior-embedded /
  embedded-Linux-systems / principal / solution-architect) + reasoning method (constraints-before-options,
  show-the-line + runner-up, second-order ripple, diagnosticity) + break-the-loop mandate.
- **Wave 2 — dynamic reasoning:** DONE. `engines/lenses.py` (17 families, `scan_line` floor on all, full
  frames for compute-tier/power/pcb/connectivity-rf/certification) · `engines/spine.py` (10-axis classifier,
  derive-or-ask) · `engines/lens_weighting.py` (spine→causal + topic + structural + constraints + blind-spot
  floor + coverage-flatten + overrides) · `engines/reasoning_scaffold.py` wired into Deep Dive `decide`.
- **Wave 3 — reasoning-first + card:** DONE (backend + frontend, live-verified).
  - Step 6: `/deepdive/frame` reflects back spine + weighted lenses + framing questions BEFORE the card;
    frontend frame panel ("HOW I'M FRAMING THIS") verified in-browser.
  - Step 7: card renders runner-up (gap + tipped-by), blind-spots (distinct from risks), tripwire
    review_conditions, and provenance tags (`computed:`/`datasheet`/`inferred`) — verified in-browser.
  - Step 8: `engines/checks.py` deterministically re-evaluates the model's own arithmetic
    (`verify_computations`) so a computed figure carries a real ✓ and a wrong one is caught; canonical
    formula helpers (LDO/thermal/battery/power-budget). Live-verified: a real LDO-vs-buck decision emitted 7
    computations, all re-verified. Cross-decision consistency is already carried by GraphRAG
    (`_related_decisions_context`) + the ERC contradiction mandate.
- **Test hygiene:** the DB test suite now isolates to a dedicated `*_test` database (auto-created) and can
  never touch the dev DB (a full run once wiped it); the whole suite is hermetic (stub model/embedder). 357
  tests green.

## Still open for correction
- Spine axes right? (#4 connectivity: split topology single/mesh & update-model connected/air-gapped?)
- Any lens family still thin or miscategorized?
- **Wave 2.5 (surfaced by testing):** high-salience lenses without frames (mechanical/enclosure,
  reliability-safety, peripherals-io, memory, security) currently scan-only — writing their full frames is
  the next depth win.
