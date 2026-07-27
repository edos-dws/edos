### Lens — Manufacturing / production-test (DFM, provisioning, yield)
A design that works on the bench but can't be built repeatably at volume is not finished. Manufacturability
and testability are design decisions, and they scale with the production volume.
- **Design for manufacture & assembly (DFM/DFA).** Component courtyards, orientation, thermal relief,
  panelization, and no unbuildable footprints. At volume, a package that placement machines struggle with, or
  a hand-solder step, is real recurring cost and yield loss. Confirm every part is assembly-line friendly.
- **Provisioning & serialization at the line.** How does each unit get its firmware, unique ID, calibration
  data, and (for secure devices) its **injected keys**? Secure key provisioning at the factory is a real
  process with real equipment — design it in, don't bolt it on.
- **Test coverage you can run at volume.** In-circuit test (ICT), functional test, and boundary scan need
  access (test points, a test connector) and a defined pass/fail. What fraction of faults does the test
  actually catch? Untested nets ship latent defects.
- **Calibration in production.** If accuracy needs per-unit calibration (analog front ends, sensors), that is
  a line step with a time and fixture cost — budget it and store the coefficients in NVM.
- **Yield and traceability.** Estimate first-pass yield and the rework path; keep traceability (serial →
  build/test record) for field returns and any regulated market.
- **Ripple:** manufacturing couples to PCB (DFM, test points), security (key injection), firmware
  (provisioning image), cost (yield, test time), and certification (traceability). Volume changes the answer —
  a one-off prototype and a million-unit product make opposite calls.
