### Lens — Reliability & functional safety
Reliability is designed in, not tested in — and safety-critical work is governed by standards that dictate
*process*, not just design. Match the rigor to the real consequence of failure, and no more.
- **Name the safety class and what it demands.** Consumer, industrial (IEC 61508), automotive (ISO 26262 /
  ASIL), medical (IEC 62304), avionics/rail (DO-178C / EN 50128) each impose different documentation,
  redundancy, and verification burdens. The class is set by the hazard; it then drives the whole program.
- **Enumerate failure modes systematically (FMEA/FMEDA).** For each function: how can it fail, what is the
  effect, what causes it, and — separately — **would we even detect it?** Detection is its own axis; an
  undetectable dangerous failure is the worst kind. Prioritize by severity first (a rare catastrophe outranks
  a frequent nuisance), never by a single multiplied score that averages catastrophe away.
- **Define the safe state and how you reach it.** On fault, what does the system do (de-energize, hold,
  degrade), and what forces it there (watchdog, hardware interlock, safety monitor, lockstep cores)? A safe
  state you can't guarantee reaching is not a safe state.
- **Integrity mechanisms.** ECC/CRC on memory and comms, redundancy where a single fault is intolerable, and
  brown-out/power-fail behavior that leaves the system and its stored state consistent.
- **Environmental & EMC robustness is reliability.** ESD, surge, and EMC immunity, plus temperature/vibration
  derating, decide whether the device survives the real world — not just the lab. Rate parts for the
  environment they'll see.
- **Ripple:** the safety class ripples into architecture (redundancy), firmware (MISRA/coverage/process),
  certification (evidence), and cost/schedule (the process is expensive). Over-classifying wastes months;
  under-classifying is a recall.
