### Lens — Real-time & concurrency
Timing bugs are the ones that pass every bench test and fail in the field once a day. Reason about the
*worst case*, not the average, and about what happens when two things run at once.
- **Prove the deadline, don't hope for it.** For each hard real-time task, name the deadline and the
  worst-case execution time (WCET) — the deepest path, not the typical. Add interrupt latency and the longest
  higher-priority task/ISR that can preempt it. A deadline "usually met" is not met.
- **Interrupt design is where determinism lives.** Keep ISRs short (flag-and-defer), bound nesting, and know
  your controller's interrupt latency and priority model. A long ISR or a disabled-interrupt critical section
  silently blows another task's deadline.
- **Priority inversion is a real, shipped failure mode.** A low-priority task holding a mutex a high-priority
  task needs stalls the system (the Mars Pathfinder bug). Use priority inheritance, or avoid shared locks on
  the critical path. Name the shared resources between priority levels.
- **Concurrency correctness > cleverness.** Shared state between an ISR and a task, or between tasks, needs a
  defined discipline (atomic access, lock, lock-free ring, double-buffer). Reentrancy, `volatile` for
  memory-mapped/ISR-shared data, and race-free hand-off must be explicit — an intermittent corruption here is
  nearly un-debuggable.
- **Is Linux even viable here?** Hard determinism on general-purpose Linux needs PREEMPT_RT and still isn't
  bare-metal deterministic. If a loop must never miss, keep it on a bare-metal core/MCU or an RTOS, and say
  where it lives.
- **Ripple:** the concurrency model drives the compute-tier choice (RTOS vs bare-metal vs Linux), memory
  (per-task stacks), power (wake/sleep timing), and debug (the hardest bugs to reproduce). Under-specifying
  timing is a late-integration disaster.
