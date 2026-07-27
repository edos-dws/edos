### Lens — Mechanical / enclosure / electro-mechanical
The enclosure is where the electronics meet the physical world — and where PCB, thermal, sealing, and
certification all collide. Reason about it *with* the board, never after it.
- **Fit and tolerance are a stack-up, not a guess.** The PCB, connectors, battery, display, and mounting
  bosses must all coexist inside the shell with real tolerance margins. Board outline, connector cut-outs,
  and component keep-out heights are fixed early — a late "it doesn't fit" is a respin of both the PCB and the
  tool. State the critical dimensions the enclosure imposes on the board.
- **IP sealing is a system property.** An IP67/IP68 claim is only as good as its weakest path: gasket groove
  and compression, ultrasonic weld vs screw-boss, membrane vents for pressure equalization, and — the usual
  failure — the connector and button penetrations. A sealed box with no serviceable opening means no rework
  and no battery swap: a field failure is a scrapped unit. Name how each penetration is sealed.
- **Connectors are a reliability and lifecycle decision.** Mating cycles, retention, keying, and strain
  relief; board-to-board vs cable; the connector's own current/temperature derating. The cheapest connector
  that meets the cycle count usually wins — but "meets the cycle count" must be checked, not assumed.
- **Survive the environment.** Drop, vibration, and thermal cycling load the solder joints and the mounting;
  heavy or tall parts need mechanical support beyond their pads. Wearables and handhelds see far more abuse
  than a rack unit — design the retention for the real use case.
- **Ripple:** the enclosure sets board size and layer count (PCB), the heat path (thermal), the sealing that
  drives environmental/IP certification, and the connector/BOM. Treat form-factor, PCB, thermal, sealing, and
  cert as one coupled cluster — moving any one moves the others.
