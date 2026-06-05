# Zork II — Open Bugs

Bugs found via shakedown. Newest first. Fixed items kept briefly for trail;
see `references/completed-work.md` for the durable record.

- [ ] **`diagnose` not recognized** (any room, command: `diagnose`)
  - **Response**: `I don't know how to do that.`
  - **Hypothesis**: `V-DIAGNOSE` is in `_SKIP_ROUTINES`; zork1's hand-written replacement (`verbs/zork1/actor/diagnose.py`) calls `_.thing.fight_strength`, but `FIGHT-STRENGTH` is a zork1-only ZIL routine — zork2's combat model differs, so the helper doesn't exist here. Needs a zork2-specific diagnose (or a fight_strength-free health readout) written against zork2's combat globals. Not a simple relocation like idrop.
  - **Workaround**: none; minor info verb, left unimplemented for now.

## Fixed this session (2026-06-04)

- [x] **`drop` raises a traceback** (`#... (Thing) has no attribute idrop`) —
  `IDROP` is a shared `gverbs.zil` routine in `_SKIP_ROUTINES`; its generic
  hand-written replacement was misfiled under per-game `verbs/zork1/`, so
  zork2 never got it. Relocated to shared `verbs/thing/helpers/idrop.py`.
- [x] **Lamp starts already-on / items pre-held after reset** — the
  bootstrap's `get_or_create` doesn't reposition existing objects, so prior
  inventory + a lit lamp leaked into the captured snapshot. The reset body
  now force-places lamp + sword on the barrow floor with the lamp OFF every
  reset (authoritative over snapshot drift).
