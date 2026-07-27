### Lens — Certification / compliance (EMC · radio · safety · environmental · industry)
Reason about certification as a **schedule and design constraint**, not a checkbox at the end:
- **Scope is set by markets × product class.** Target regions and the product's category decide which regimes
  apply: EMC (emissions + immunity), intentional-radiator/radio approval per region, product safety,
  environmental (RoHS/REACH), and any industry regime (medical / automotive / industrial / rail). Name the
  actual set for *this* product and market — not a generic list.
- **Test-house lead time is often the real critical path.** Booking slots, pre-scan, fix-and-retest cycles
  take weeks to months. A cert regime discovered late doesn't just cost money — it moves the ship date. Flag
  the long-lead regime early and treat it as a schedule item.
- **Design for cert, don't fail at cert.** The cheap path is pre-compliance thinking during design: EMC
  containment (the power/PCB/enclosure cluster), a pre-certified radio module to skip intentional-radiator
  testing, creepage/clearance and isolation for safety, materials for environmental. Retrofitting compliance
  after a failed scan is the expensive path.
- **Evidence burden scales with class.** Safety-critical regimes (medical/auto/rail/avionics) demand process
  and documentation (traceability, verification records), not just a passing test. If the criticality class
  implies this, the burden is a first-class cost — say so.
- **Ripple:** certification pulls on power/EMC, PCB/enclosure (containment, shielding), radio (module vs
  chip-down), and the whole development process. It is rarely a late, isolated step.
