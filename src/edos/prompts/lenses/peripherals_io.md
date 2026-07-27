### Lens — Peripherals & I/O (buses, USB, MIPI, Ethernet)
The part's block diagram lists peripherals; the real question is whether *this* set of interfaces can run
*simultaneously* at *this* bandwidth on *these* pins. Check feasibility, not the feature list.
- **Pin-mux is a zero-sum game.** The same physical pins are shared across alternate functions. Map every
  required interface to a pin and confirm no two needed functions collide — a late "we can't route SPI2 and
  the second UART together" forces a part change. Count the pins you actually need vs. what the package gives.
- **Bandwidth must close, end to end.** A camera at N MB/s over MIPI-CSI, or a sensor stream over SPI, has to
  be moved by DMA and consumed without overrun. Compute the real data rate and check the bus, the DMA
  channels, and the CPU/memory that must keep up — not just "the peripheral supports it."
- **High-speed interfaces are PCB decisions.** USB, Ethernet (RMII/RGMII), MIPI, and PCIe need controlled
  impedance, length matching, and clean return paths — they belong to the PCB lens the moment you pick them.
  A "supported" high-speed interface on a two-layer board without impedance control will fail compliance.
- **Levels, drive, and protection.** Voltage-level compatibility (1.8/3.3/5 V), open-drain vs push-pull, bus
  loading/capacitance (I²C rise time at many nodes), and ESD/protection on any connector-facing line. CAN/
  RS-485 need proper transceivers and termination, not GPIO bit-banging.
- **Ripple:** the peripheral mix drives the compute-tier and pin-count (package choice), the PCB (layers,
  impedance), power (active peripherals), and memory (DMA buffers, cache coherency). Pick the interfaces
  against a pin/bandwidth budget, not a checkbox.
