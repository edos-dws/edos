### Lens — Compute tier (MCU · RTOS · MPU+Linux · heterogeneous · FPGA)
The most load-bearing decision: it fixes the memory model, boot, real-time ceiling, driver ecosystem,
security model, and power floor for everything downstream. Reason it in this order:
- **Derive the compute demand first, from the workload — not from familiarity.** What must run: control loops
  (rates, jitter tolerance), data movement (bytes/s in and out), any DSP/ML, connectivity stacks, UI. Size
  MIPS/RAM/flash from that, then pick the *lowest* tier that meets it with margin. A tier picked before the
  workload is derived is a guess.
- **Is Linux even justified?** Linux buys you a driver ecosystem, filesystems, and networking — at the cost
  of DRAM, boot time, non-determinism, a BSP to maintain, and a far larger attack/CVE surface. If there is no
  hard need for its stack, an RTOS or bare-metal MCU is cheaper, more deterministic, and instant-on. Name the
  *specific* Linux feature that forces the MPU tier; if you can't, drop a tier.
- **Real-time reality.** Hard deadlines on Linux need preemptible-kernel work and still aren't bare-metal
  deterministic. If determinism is safety-relevant, either keep the hard loop on a separate MCU/core
  (heterogeneous: application core + real-time core) or stay on an RTOS. State where the hard real-time work
  actually lives.
- **Ecosystem & lifetime, not just the silicon.** Mainline kernel/driver support vs a vendor BSP fork (the
  fork is a multi-year maintenance tax); toolchain maturity; SoM-vs-discrete (a SoM buys time-to-market and
  sidesteps DDR routing, at unit-cost and lock-in); part longevity and second-source at this tier.
- **Ripple:** the tier chosen dictates DDR/PCB layer count, power sequencing, boot/OTA scheme, and security
  (secure boot / key storage). Call those out — the compute choice is rarely local.
