# Zork III — Known quirks (don't re-report)

Pre-existing limitations and accepted behaviours. Before logging a bug in
`../BUGS.md`, grep here first. Per-game "boundary cases I held the line on"
(Rule-Zero temptations and the right game-side fix) also go here.

## Accepted behaviours

- **"There is a Wizard here." at the opening room.** The reset body parks
  *every* connected avatar (including the system Wizard's avatar) at the
  start room. Cosmetic; the same happens in zork1/zork2. Not a bug.
- **A `--sync` resets the live world and teleports your session avatar back
  to the start room.** `099_reset_state.py` runs on every `--sync`, restoring
  the snapshot and re-parking avatars at "Endless Stair". After any
  regen+sync mid-session, `look` first — don't read "You can't go that way"
  as an exit bug when you've actually been moved back to the start. (Bit me
  once this session: `east`/`down` "failed" at what I thought was Cliff but
  was really Endless Stair post-reset.)
- **Zork III max score is 7** (`score` → "potential is 0 of a possible 7").
  Unlike zork1's 350; don't mistake the low ceiling for a scoring bug.

## Map notes (verified live, 2026-06-05)

- Opening: **Endless Stair** (ZIL `ZORK2-STAIR`) — exits: south → Junction,
  up (endless), north. Start carrying nothing.
- **Junction**: N→Endless Stair, W→Barren Area, E/S cramped. "great rock"
  holds the sword — `take sword` is correctly refused ("deeply imbedded in
  the rock. You can't budge it.") until the canonical trigger.
- **Barren Area** (a.k.a. west-of-junction): E→Junction, W→Cliff, SW→mist
  opening, NW→rocky terrain, S→stone wall.
- **Cliff**: E→Barren Area (verified reverse exit), W→precipice, S→wall,
  SW→mist; rope dangles to the shelf below.
