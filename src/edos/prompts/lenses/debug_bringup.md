### Lens — Debug & bring-up (JTAG, trace, DFT, watchdog)
"Can we actually bring this up and debug it in the field?" is a design question, decided at schematic time —
not something to discover when the first board is dead on the bench.
- **Preserve a debug path to production.** JTAG/SWD access, a serial console, and trace (SWO/ITM/ETM/RTT) are
  cheap to design in and priceless when a board won't boot. Confirm the debug pins survive pin-mux and aren't
  sacrificed to another function; plan how the port is *secured* in production (see the security lens) without
  losing all field diagnosis.
- **Fault handling that tells you what happened.** A HardFault/exception handler that captures the fault
  registers and a stack trace (a mini core-dump) turns a mystery reset into a fixable bug. A device that just
  silently reboots is a field-return with no information.
- **Watchdog strategy, not just a watchdog.** A watchdog that a hung task can still kick is useless; a
  windowed/task-aware watchdog that requires healthy tasks to check in catches real hangs. Define what "alive"
  means and what a watchdog reset leaves behind (safe state, logged cause).
- **Design for test (DFT).** Test points on key nets, a way to program/provision at the line, boundary scan
  where density hides joints, and a bring-up/functional-test plan. If you can't measure it in production, you
  can't yield it.
- **In-field observability.** Logging/telemetry (bounded, power-aware) and a way to retrieve it decide whether
  a field failure is diagnosable or a guessing game.
- **Ripple:** debug/DFT couples to security (locking the port), manufacturing (test/provisioning), firmware
  (fault handlers, logging), and PCB (test points). Skipping it doesn't save cost — it moves the cost to a
  painful, opaque bring-up.
