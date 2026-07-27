### Lens — Thermal (dissipation, derating, heat path)
Thermal is quantitative — reason with numbers, not adjectives. Heat is the silent killer of reliability and
the constraint that most often invalidates an otherwise-clean design late.
- **Compute the rise, don't assert it.** ΔT = P · Rθ. Sum the real worst-case dissipation of each hot part
  (regulators, power stage, MCU under load, LEDs), take the actual Rθ (junction-to-ambient *in this
  enclosure*, not the datasheet's still-air JEDEC board), and check Tj = Tambient + ΔT against the part's max
  junction — with margin, at the *worst-case ambient*, not room temperature.
- **The datasheet Rθ is a lie about your board.** RθJA is measured on a specific test board with specific
  copper; your real number depends on copper area, layers, vias-under-pad, airflow, and the enclosure. A
  sealed plastic box has almost no convection — conduction to the case is the only path. Name the actual heat
  path.
- **Derate everything.** Electrolytics lose life halving every +10 °C; MOSFET RdsON rises with temperature
  (thermal runaway risk in linear regions); a "3 A" connector is 3 A at 20 °C, less when hot and derated for
  adjacent pins. Rate parts at the temperature they will actually see.
- **Sealed / harsh changes the whole answer.** IP-sealed, potted, or high-ambient designs cannot dump heat by
  air. That can force a lower-dissipation topology (switcher over LDO), a heat-spreader to the case, or a
  lower-power part — a decision the thermal budget must drive, not discover at the DVT thermal chamber.
- **Ripple:** thermal couples to power (topology/efficiency), mechanical (heat path, case temperature, user
  touch-temp limits), PCB (copper, vias, layer count), and reliability (every 10 °C roughly halves lifetime).
  A power or enclosure choice that ignores the heat path is not finished.
