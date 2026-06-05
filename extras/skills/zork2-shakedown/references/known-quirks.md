# Zork II — Known quirks (don't re-report)

Pre-existing limitations and accepted behaviours. Grep here before logging a
bug in `../BUGS.md`.

- **"There is a Wizard here." at the opening room.** The reset parks every
  Player avatar (including the world-owner Wizard) at the start room;
  gameplay runs as the non-wizard Adventurer, so the Wizard shows as a
  co-located occupant. Same pattern as zork1. Cosmetic — not a bug.
- **Carousel Room spin is seeded off in the smoke.** `zork2_smoke.py` /
  `_zork2_reset_state_body.py` seed `zstate_carousel_flip_flag=True` so the
  eight passages are deterministic. The *real* mechanism is the robot
  pressing the triangular button (Adventurer pressing any button → death).
  Don't "fix" the seeded carousel — it's the deliberate smoke-safe shortcut.
- **Marble Hall flavor: "annoying whirring sound" from the carousel (S).**
  Cosmetic residual line even with the spin stopped; harmless.
- **Opening rooms are self-lit.** Barrow + tunnels describe phosphorescent
  moss / "dim light" and stay lit with the lamp off — a grue probe needs a
  genuinely dark room (not yet mapped).
