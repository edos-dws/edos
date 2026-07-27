### Lens — Security (secure boot, keys, update signing, attack surface)
For a connected device, security is not a feature you add later — it is decided by the silicon and the boot
architecture, and it is increasingly a *legal* requirement (EU CRA, ETSI EN 303 645, IEC 62443). Reason from
the threat model, not from a checklist.
- **Root of trust first.** Secure boot that verifies each stage against an immutable root (ROM + fused keys)
  is the foundation — without it, signed firmware and secure storage are theatre. Confirm the chosen part
  actually supports a hardware root of trust and key fusing; retrofitting it means a silicon change.
- **Where do keys live, and who can read them?** Keys in external flash or plain MCU flash are extractable.
  Use a secure element / TPM / on-die secure key storage, and a TRNG for key generation. State the key
  hierarchy (device identity, update-signing, transport) and how each key is protected at rest.
- **Signed, anti-rollback updates.** Every firmware image must be authenticated before it runs, and
  anti-rollback must stop an attacker re-flashing a known-vulnerable version. This is the same mechanism as
  the OTA story — design them together.
- **Lock the debug surface.** JTAG/SWD and readout protection (RDP) left open in production is remote/physical
  game-over. Define the lifecycle: open in development, locked (with a defined, auditable transition) in
  production. Consider fault-injection and side-channel exposure for high-value targets.
- **Minimize and patch the attack surface.** Every open port, service, and third-party library is surface;
  track the CVE exposure of the whole stack (especially on Linux) and have a patch path. Regulatory: name the
  regime (CRA/303645/62443) and what evidence it demands.
- **Ripple:** security drives the compute-tier (secure-boot-capable silicon), firmware (signing/boot),
  manufacturing (secure key provisioning/injection at the line), and certification. A device that ships
  unlocked or unsigned cannot be made secure by an update.
