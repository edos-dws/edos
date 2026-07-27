### Lens — Firmware architecture (boot, OTA, drivers, update safety)
Firmware architecture is what lets a shipped device be fixed, extended, and trusted in the field. The
expensive mistakes here are structural, not syntactic — and they are locked in early.
- **Field update is a first-class requirement, not an afterthought.** If the device ships, it will need a
  firmware fix. Decide the update path up front: **A/B (dual-bank) with atomic switch and automatic rollback**
  is the safe default — a failed or corrupted update must fall back to the last-good image, never brick.
  Single-bank "update in place" risks a dead device on a power cut mid-flash. Name the rollback story and the
  power-fail behavior.
- **Chain of trust, or the update is an attack surface.** A connected device that accepts unsigned firmware
  is remotely ownable. Signed images verified by a root of trust in the bootloader (ideally with secure boot
  and anti-rollback) is the baseline for anything networked. State how the image is authenticated.
- **Boot flow and recovery.** ROM → bootloader → app: where does verification happen, how long is the boot
  budget (instant-on products can't afford a slow boot), and what is the *recovery* path if the app is bad —
  a serial/USB/OTA recovery mode beats a return-to-factory.
- **Layering for portability and test.** A clean HAL/driver boundary lets the same logic move across silicon
  and be unit-tested off-target; a superloop is fine for simple deterministic devices, an RTOS earns its keep
  when there are concurrent real-time tasks. Match the structure to the concurrency, and keep hardware
  specifics behind an interface so a part change isn't a rewrite. For safety-relevant code, hold the line on
  MISRA/CERT-C and coverage from the start — retrofitting it is far more expensive.
- **Ripple:** the update scheme sizes memory (A/B doubles app flash), depends on security (signing/keys),
  touches connectivity (how updates arrive), and defines the recovery UX. A silicon choice made without the
  driver/boot/OTA reality is the classic "software as an afterthought" trap.
