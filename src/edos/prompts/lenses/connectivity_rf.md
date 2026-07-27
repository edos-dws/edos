### Lens — Connectivity / RF (wireless & wired, stacks, antenna, coexistence)
Connectivity decisions lock in cost, power, range, certification, and the security surface at once:
- **Match the radio to the traffic and the power source, not to popularity.** Payload size, latency, range,
  duty cycle, and network topology (point-to-point / star / mesh) select the technology. A mains-powered
  gateway and a coin-cell sensor want different radios; picking one radio "because we know it" is the trap.
- **The stack and provisioning are most of the work.** The PHY is the easy part; the protocol stack,
  pairing/onboarding, roaming, retries, and OTA-over-the-link are where schedule goes. Account for them.
- **Module vs chip-down is a certification and schedule decision.** A pre-certified module carries modular
  radio approval (huge cert/time saving) at unit-cost and flexibility loss; chip-down means you own the RF
  layout, matching network, and full intentional-radiator certification. State which and why.
- **Antenna is a system constraint, not an afterthought.** Placement, keep-outs, ground plane, enclosure
  material and nearby metal/battery detune it; tuning needs the real enclosure. This couples hard into PCB
  and mechanical.
- **Coexistence & spectrum.** 2.4 GHz is crowded (Wi-Fi/BLE/Zigbee coexistence); cellular means carrier
  certification and module lifecycle; sub-GHz means regional band differences. Name the regional/spectrum
  constraint for the target markets.
- **Ripple:** connectivity drives radio certification (per region), power budget, antenna→PCB→enclosure, and
  the security/attack surface (an over-the-air update path is also an attack path).
