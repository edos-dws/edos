### Lens — Power (source, rails, regulation, low-power, thermal coupling)
Power is where optimistic designs meet physics. Reason quantitatively — this lens expects numbers:
- **Build the power budget before choosing regulators.** Enumerate every rail, its worst-case load (peak and
  average, not typical), and the source. Sum it. Battery life or thermal claims made without this budget are
  not credible.
- **LDO vs switcher is a dissipation decision, not a habit.** LDO drop × current = heat: check it against the
  package/ambient thermal limit (ΔT = P·Rθ). A "simple, low-noise" LDO that dissipates 0.5 W in a sealed
  enclosure is a thermal problem. Switchers add noise, EMI, and PCB complexity — justify the trade explicitly.
- **Sequencing & supervision.** Rails often must come up/down in order (core before I/O, PHY constraints);
  name the sequence and the reset/brown-out supervisor. Missing sequencing shows up as intermittent bring-up
  failures, not a clean bug.
- **Low-power is a system property, not a mode.** For battery/harvesting: the *average* current over the duty
  cycle dominates life, and it is usually set by leakage, always-on rails, and wake frequency — not the
  active burst. Check sleep-mode residuals, wake sources, and RTC/retention. Model the actual duty cycle.
- **Source realities.** Coin cell (pulse current limit, internal resistance, cold temperature) vs Li-ion
  (charge management, protection, safety/cert) vs harvesting (cold-start, storage). Each constrains the rest.
- **Ripple:** power choices drive thermal, EMC (switching noise → radiated emissions → cert), BOM, and
  enclosure (heat path). Flag the coupled ones.
