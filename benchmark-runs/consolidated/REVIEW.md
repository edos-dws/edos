# EDOS — Live Benchmark Run Review (consolidated)

**Provider:** GeminiProvider · **Model:** `gemini-3.6-flash` (Google AI Studio free tier) · **Harness:** `edos.eval.harness.score_run` (CP-8)

Per scenario: **intake brief → live LLM decision (`edos.decision.v1`) → independent LLM-judge (0–2 per rubric criterion, guided by the traps) → deterministic harness pass/fail.** The decision model never sees the traps or the evaluation key.

## Results

| # | Scenario | Domain | Score | Pass | Traps caught |
|---|----------|--------|:-----:|:----:|:------------:|
| 02 | Solar LoRaWAN Agri Node | agri-iot | **20/20** | ✅ | 5/5 |
| 03 | Edge AI Camera (InnoFusion) | vision-edge-ai | **20/20** | ✅ | 4/4 |
| 04 | Outdoor PTZ Camera (umbrella) | surveillance | **20/20** | ✅ | 4/4 |
| 05 | LMFP Cell BMS | battery-management | **20/20** | ✅ | 5/5 |
| 06 | Home Zone-Detection Gateway | smart-home | **20/20** | ✅ | 4/4 |

**Scored 5/5 · mean 20/20 · passed 5/5 · every planted trap caught.**

---
## Full detail per scenario

### scenario-02 — Solar LoRaWAN Agri Node · 20/20 ✅

**Live decision:** _Reject concept baseline due to nRF52840 hardware incompatibility (lacks LoRa), Class C / 10s uplink power and airtime violations, and unviable supercapacitor holdover assumptions._

- recommendation: Do not freeze schematic inputs until core architecture is restructured: (1) Replace nRF52840 with a sub-GHz LoRaWAN SoC (e.g., STM32WLE5) or add a companion LoRa transceiver (e.g., SX1262); (2) Change node operating mode from Class C to Class A with duty-cycled sleep; (3) Change reporting cadence from 10 seconds to 15–60 minutes (with local thresho
- confidence **0.2** · status `recommended` (capped — never self-frozen) · risks 5 · freeze_blockers 4 · next_actions 5
- freeze_blockers held:
  - D-1 part choice error: nRF52840 lacks integrated sub-GHz LoRaWAN transceiver; MCU/radio selection must be corrected.
  - Regulatory and network capacity violation: 10-second uplink cadence violates regional duty-cycle limits and saturates LoRaWAN gateways.
  - Power architecture contradiction: Class C continuous receive and continuous 10s active sampling exceed 5x5 cm solar and supercapacitor energy limits.
  - Unbounded data buffer requirement: Offline buffering capacity and backlog upload strategy must be bounded and physically specified.

**Judge — traps caught 5/5:**
  - ✅ nRF52840 has no sub-GHz LoRa radio
  - ✅ 10 s cadence vs LoRaWAN duty-cycle/airtime limits
  - ✅ solar = 'unlimited power' energy-budget fallacy
  - ✅ on-device ML + Class C continuous-receive over-engineering
  - ✅ unbounded 'never lose a reading' buffer

> The evaluation system identified all five critical architectural traps with precise quantitative calculations (energy consumption, duty cycle limits, and buffer sizing) and appropriately low confidence score. It correctly enforced freeze discipline by blocking schematic lock until core RF, power, and buffer design flaws are rectified.

### scenario-03 — Edge AI Camera (InnoFusion) · 20/20 ✅

**Live decision:** _Approve single AI-ISP SoC architecture with decoupled 640x640 inference, dual-stream recording, and metal thermal enclosure, subject to InnoFusion datasheet validation._

- recommendation: Proceed with the single AI-ISP SoC topology (InnoFusion with CV5 fallback) utilizing a decoupled 640x640 NPU branch, 1080p continuous record + 4K live/event streams, and a die-cast metal housing. Hold carrier-board layout lock and housing tooling freeze until the missing InnoFusion datasheet confirms MIPI CSI-2 lane count (>=4 lanes), sustained NPU
- confidence **0.61** · status `recommended` (capped — never self-frozen) · risks 4 · freeze_blockers 4 · next_actions 6
- freeze_blockers held:
  - Missing InnoFusion datasheet: cannot verify >=4 MIPI CSI-2 lanes required for 4K60 link.
  - Unconfirmed NPU sustained throughput: YOLOv8 INT8 640x640 execution must be benchmarked on InnoFusion hardware before freezing architecture.
  - Unconfirmed thermal parameters: SoC TDP and Tj max needed to complete thermal balance calculation before committing enclosure tooling and PCB copper l
  - Unverified hardware security features: secure boot and key storage confirmation required prior to locking firmware OTA and encryption architecture.

**Judge — traps caught 4/4:**
  - ✅ NPU TOPS is not real FPS; pin inference resolution separately
  - ✅ 4K60 MIPI CSI-2 bandwidth (~5 Gbit/s) vs lane count
  - ✅ continuous-record storage (~130 GB/day) + SD wear
  - ✅ thermal throttling in a sealed plastic housing

> The system successfully identified all four critical engineering traps with accurate calculations and domain awareness. It correctly flagged missing datasheet parameters as freeze blockers and decoupled high-resolution capture from lower-resolution inference to address real-world hardware constraints.

### scenario-04 — Outdoor PTZ Camera (umbrella) · 20/20 ✅

**Live decision:** _Outdoor solar/battery PTZ umbrella camera architecture is conditionally sound as an event-driven system, but blocked from freeze by missing solar, battery, and optical zoom parameters._

- recommendation: Adopt the dual-chip architecture (Sigmastar SSC338Q + STM32G431) and event-driven duty cycle. Do not freeze the design or commit to the solar specification until panel wattage (Wp), site sun-hours, battery capacity (Wh), position feedback strategy, and optical zoom ratio are explicitly provided and verified.
- confidence **0.62** · status `recommended` (capped — never self-frozen) · risks 5 · freeze_blockers 3 · next_actions 5
- freeze_blockers held:
  - Missing solar panel rated wattage (Wp) and site sun-hours — energy harvest feasibility remains unproven.
  - Missing battery capacity (Wh), autonomy target (days), and low-temperature charge strategy.
  - Unspecified optical zoom ratio and mount stiffness specification — wind-induced image stability limits unquantified.

**Judge — traps caught 4/4:**
  - ✅ continuous 360 pan with wires -> cable twist (slip ring vs limits)
  - ✅ optical zoom on a wind-loaded umbrella -> shaky image
  - ✅ small-panel solar energy budget vs PTZ motors + streaming
  - ✅ IP66 on a rotating/tilting joint

> The system successfully identified all four design traps, correctly addressing the trade-offs between slip rings versus cable flex limits, optical zoom instability on wind-loaded structures, solar energy budgeting vs PTZ duty cycles, and IP66 rotary seal friction. Freeze discipline is strictly maintained with clear, actionable blockers.

### scenario-05 — LMFP Cell BMS · 20/20 ✅

**Live decision:** _14S LMFP BMS concept is architecturally sound (STM32G474 + BQ79616-Q1 + Shunt), but locked from design freeze due to missing chemistry parameters, unpinned FuSa target, and 48V voltage rating conflicts._

- recommendation: Proceed with the proposed host/AFE core (STM32G474 host + BQ79616-Q1 AFE + Shunt-based coulomb counting with Mn/Fe plateau re-calibration). Maintain a variant split for the ESS version. Do NOT freeze schematic or layout until the LMFP cell datasheet, Functional Safety target, and charger interface control are formally supplied.
- confidence **0.66** · status `recommended` (capped — never self-frozen) · risks 5 · freeze_blockers 4 · next_actions 5
- freeze_blockers held:
  - Missing LMFP cell datasheet: Voltage thresholds (OVP/UVP) and absolute maximum charge voltage remain unverified.
  - Undefined Functional Safety target: Architecture cannot be frozen until safety target confirms whether STM32G474 host MCU is compliant without externa
  - Unverified charger control interface: Uncontrolled CC-CV charging without BMS CAN interlock creates an unresolved overcharge safety risk.
  - Legacy '48 V' component rating mismatch: Unverified component survival margins under 58.8 V – 60.2 V top-of-charge conditions.

**Judge — traps caught 5/5:**
  - ✅ copying LFP 3.65 V thresholds to LMFP (~4.2-4.3 V)
  - ✅ voltage-based SoC on a flat LMFP OCV curve
  - ✅ 14S LMFP ~59-60 V vs '48 V' platform part ratings
  - ✅ cold-charge lithium plating (no sub-0C inhibit)
  - ✅ 'same board' for a stationary-ESS variant vs cost/life/cert

> The system caught all five domain traps cleanly, accurately analyzing LMFP electrochemistry, 14S voltage limits against 48V legacy parts, low-temperature lithium plating inhibits, and variant splits. It maintained strict design-freeze discipline with well-calibrated confidence and clear next actions.

### scenario-06 — Home Zone-Detection Gateway · 20/20 ✅

**Live decision:** _Mains gateway architecture using EFR32MG24 (802.15.4) + dual-band Wi-Fi (5 GHz primary) + BGT60TR13C radar/PIR fusion is conditionally sound, but gates on compute host selection, mmWave calibration spec, and DAC provisioning line setup._

- recommendation: Proceed with the decoupled architecture (EFR32MG24 for 802.15.4 mesh/TBR + separate 5 GHz-primary Wi-Fi/BLE + BGT60TR13C radar with PIR fusion for mains gateway; PIR-first Thread Sleepy End Device for battery satellite variant). Hold full architecture freeze until compute host class, mmWave mounting/calibration spec, and factory DAC provisioning ar
- confidence **0.78** · status `recommended` (capped — never self-frozen) · risks 4 · freeze_blockers 3 · next_actions 5
- freeze_blockers held:
  - Compute host class is unpinned (MCU-only vs Linux host + RCP); selecting an under-resourced core risks complete system architecture rework late in des
  - Radar mounting specification and room calibration flow are uncommitted; lack of calibrated boundaries causes wrong-room triggers and field returns.
  - Matter Device Attestation Certificate (DAC) factory provisioning line and PKI infrastructure are unconfirmed, gating regulatory and logo certification

**Judge — traps caught 4/4:**
  - ✅ 2.4 GHz coexistence: Wi-Fi clobbers Zigbee/Thread
  - ✅ 'Matter is a radio' -> it runs over Thread; border-router + cert
  - ✅ mmWave zone detection needs calibration/mounting; false positives
  - ✅ 'one SoC does everything' vs radio load / coexistence

> The system flawlessly identified all four domain traps, highlighting RF coexistence (5 GHz primary + PTA), Matter certification/DAC injection over Thread, mmWave radar mounting/calibration requirements with PIR fusion, and compute/radio load constraints (MCU vs Linux RCP architecture). Confidence levels are realistically calibrated to genuine technical uncertainties, and freeze blockers appropriately prevent premature commitment.

---
## Caveats (before trusting the numbers)

1. **Judge is also Gemini** scoring Gemini's output — self-favouritism likely; use blind/independent judging to derive the freeze threshold `T`.
2. **One decision per scenario** (not a 31-turn session) — yet it caught **5/5 traps on all 5 scenarios** with quantified math: strong signal the prompt hardening + model work.
3. **These test trap-catching**, not the temperament modes (07 false-alarm / 10 caving) Gemini failed and we hardened against — validate those with the round-2 scenarios.
4. **Free tier → Flash 3.6** (Pro quota-locked at 0). Real `T` derivation wants: paid key + Pro frontier + stable network + blind judging. **Freeze stays DISABLED until then.**

_Raw per-run artifacts under `benchmark-runs/run-*/`; consolidated JSON under `benchmark-runs/consolidated/`._
