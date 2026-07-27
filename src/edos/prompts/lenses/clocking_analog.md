### Lens — Clocking & analog / mixed-signal (ADC, sensors, references)
The analog front end decides whether your measurement is real. Datasheet resolution is a marketing number;
the *effective* number of bits after noise, reference, and layout is what you actually get.
- **ENOB, not bits.** A "16-bit ADC" delivers far fewer effective bits once you include its own noise, the
  reference noise, and the source impedance. Work back from the required measurement resolution to the ENOB
  you actually need, then the reference and conditioning that support it.
- **Sampling and aliasing.** Sample rate must satisfy Nyquist for the real signal *and* for the interferers
  (50/60 Hz, switching noise). Without an anti-alias filter, out-of-band energy folds into the band and
  corrupts the reading. Oversampling + decimation buys resolution only if the noise is right.
- **The reference is the ruler.** Absolute accuracy is limited by the voltage reference's initial accuracy,
  drift, and noise — a cheap reference caps your whole system accuracy no matter how good the ADC is.
- **Source impedance & settling.** A high-impedance sensor into a SAR ADC's sampling cap needs enough
  acquisition time (or a buffer) to settle, or every conversion reads low. Match the front end to the sensor.
- **Clocking integrity.** Crystal load caps and drive level set frequency accuracy and start-up; PLL/clock
  jitter degrades ADC SNR and high-speed serial. Layout matters: keep the crystal loop tight, and keep
  digital return currents out of the analog ground. Calibration and temperature drift must be planned, not
  discovered.
- **Ripple:** analog quality couples to PCB (grounding, guard, layout), power (clean rails, reference),
  clocking (jitter), and calibration in manufacturing. A precise part on a noisy board measures noise.
