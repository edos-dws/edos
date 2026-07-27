### Lens — PCB / layout / signal-integrity
Where a correct schematic still fails in hardware. This lens reasons about physical realization:
- **Layer count & stackup are derived, not chosen by cost alone.** They fall out of: controlled-impedance
  nets (USB, Ethernet, MIPI, DDR), the number of routing layers the BGA/fine-pitch parts force, and the need
  for solid reference planes. Under-layering to save cost reappears as SI/EMC failures — the expensive kind.
- **Return paths are the hidden failure.** Every high-speed signal needs a continuous reference plane beneath
  it; a split or a gap under a fast edge is an antenna and an EMC failure. Check plane continuity, not just
  trace routing. Ground is a network, not a node.
- **Decoupling & PDN.** Placement and loop inductance of decoupling caps matter more than their value; the
  power-distribution network must hold impedance across frequency for the fast parts. State the strategy.
- **The constrained nets, explicitly.** Length-match and differential-pair rules (USB/Ethernet/DDR), crystal
  and antenna keep-outs and ground pours, sensitive analog kept away from switchers. Name which nets are
  critical and why.
- **DFM is part of the design.** Trace/space, via and annular-ring rules, and board size interact with the
  fab's capability and cost tier; HDI/rigid-flex are real options with real cost. Form-factor and connector
  placement constrain all of it.
- **Ripple (physical-realization cluster):** board size ⇄ enclosure fit ⇄ connector placement ⇄ thermal
  copper ⇄ antenna keep-out ⇄ EMC. A change to one moves the others — reason about the cluster, not the board
  alone.
