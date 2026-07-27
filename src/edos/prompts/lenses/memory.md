### Lens — Memory (flash / RAM / DDR, map, NVM, wear)
Memory is sized from the real workload and checked at the worst case — an out-of-memory failure shows up as a
field crash, not a compile error. Reason about footprint, lifetime, and integrity, not just capacity.
- **Budget code, data, stack, and heap separately — with margin.** Flash for code + read-only data + OTA
  slots; RAM for .data/.bss + per-task stacks + heap. Size the *worst-case* stack depth (deepest call chain
  plus the largest ISR nesting), not the typical, and leave headroom — a stack that overflows into .bss
  corrupts silently. On Linux/MPU: DRAM sizing for the rootfs working set, page cache, and any framebuffers.
- **Heap fragmentation is the slow leak.** Long-running embedded systems that malloc/free variable sizes
  fragment and eventually fail an allocation after days of uptime. Prefer static or pool allocation in
  constrained/long-lived systems; if a heap is used, bound it and test at uptime.
- **NVM wears out — design for it.** Flash/EEPROM endurance is finite (e.g. ~10k–100k cycles per sector). A
  naive "write the counter every second" burns a sector in weeks. Use wear-leveling, journaling, or a
  filesystem built for it (LittleFS/UBIFS), and make every write **power-fail-safe** — a reset mid-write must
  not brick the device or corrupt config.
- **Cache coherency with DMA (MPU/Cortex-A/M7).** DMA moves data behind the CPU's cache. Forget to clean/
  invalidate around a DMA buffer and you get intermittent, un-debuggable data corruption. Name the buffers
  that cross a DMA boundary and how coherency is handled (cache ops, non-cacheable region, or MPU config).
- **Ripple:** memory sizing gates the compute tier (does it fit an MCU or force external DRAM?), OTA scheme
  (A/B needs 2× the app flash), cost (DRAM/flash are real BOM), and reliability (wear, fragmentation,
  power-fail integrity). Under-sizing memory is a late, expensive part change.
