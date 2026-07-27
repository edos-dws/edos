### Lens — Cost-at-volume (whole-BOM, NRE vs unit)
Cost is decided at the system level, at the target volume — not by the sticker price of one part. Reason about
the total landed cost over the program, and be honest about where the money actually goes.
- **Whole-BOM at the real volume, not the hero part.** The cheap MCU that needs an external PMIC, a bigger
  flash, more passives, and extra PCB area can cost more than the "expensive" integrated part. Sum the BOM the
  decision actually implies, at the production quantity, with real volume pricing (not qty-1).
- **NRE vs unit cost — trade it honestly.** An FPGA or custom silicon carries high non-recurring engineering
  cost that only pays back above a volume threshold; a software/off-the-shelf path has low NRE but higher
  unit cost. State the break-even volume and which side of it this product sits on.
- **The costs that hide.** Assembly/test time, calibration, yield loss/rework, tooling (enclosure molds),
  certification, and lifetime support/field-return cost are all real. A part that saves $0.10 but adds a
  calibration step or drops yield is more expensive.
- **Cost-down has levers, and a floor.** Integration (fewer parts), right-sizing (don't over-spec), and
  second-sourcing lower cost; safety, required compliance, and reliability margin are **not** valid cut
  targets. Separate the free cuts from the ones that buy a recall.
- **Ripple:** cost couples to volume (the whole calculus changes with quantity), BOM availability (allocation
  pricing), manufacturing (test/yield), and every architectural choice. A per-part cost view without the
  system and the volume is misleading.
