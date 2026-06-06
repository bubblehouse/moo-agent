# Zork III — Open Bugs

Bugs found via shakedown. Newest first. Each entry has a hypothesis +
workaround. See `../zork-shakedown/BUGS.md` for the entry format and the
mature example.

## Open

_None._ All bugs found in the inaugural run are fixed (below). Next run:
push into the Land of Shadow combat (drive the hooded-figure daemon to
appearance — it didn't materialise in the 2026-06-06 sweep), the Lake/chest
swim puzzle, and the Scenic Vista time-travel mechanic.

## Fixed (see references/completed-work.md)

- [x] **`diagnose` → "I don't know how to do that."** (2026-06-06)
  `V-DIAGNOSE` was dropped (translator `_SKIP_ROUTINES`). zork3's version is
  a trivial `DIAG`-table lookup (NOT zork1's C-TABLE math). Added
  `moo/zil_import/verbs/zork3/actor/diagnose.py` reading `P-STRENGTH` zstate
  (default 5) and indexing the `zstate_diag` list on the System Object via
  `_.table_get`. Verified live: `diagnose` → "You are in perfect health."
- [x] **Daemon-sweep log line hardcoded "zork1"** (2026-06-06) During every
  game's `moo_init`: `INFO zork1 realtime daemons: swept N stale PT row(s)`.
  Fixed game-neutrally in `generator/__init__.py:_gen_daemons` → drop the
  game word: `'realtime daemons: swept %d stale PT row(s)'`. Affects all
  games' regenerated `050_daemons.py`.

## Fixed (inaugural session — see references/completed-work.md)

- [x] **First-time `moo_init --bootstrap zork3` crashed mid-load** —
  `Object.DoesNotExist` on `--on "man (MAN)"`. Root cause: zork3 had no
  `reset_body_filename`, so the generator emitted **zork1's** default reset
  body into `099_reset_state.py`, which hardcodes `zork1.local`, restores the
  zork1 snapshot, and calls `ContextManager.set_site(zork1_site)` mid-init —
  flipping the SiteManager to site 2 for the rest of the verb load. Every
  verb before `man_f.py` was silently being added to _zork1's_ objects;
  `man_f.py` crashed because zork1 has no MAN. Fixed with a dedicated
  `_zork3_reset_state_body.py` + `ZORK3_CONFIG.reset_body_filename`.
- [x] **`wait` crashed: `Thing has no attribute clocker`** — zork3 lacked the
  per-game `clocker` shim that bridges ZIL `<CLOCKER>` to `zil_sdk` `tick`.
  Added `verbs/zork3/thing/helpers/clocker.py` (no-early-break variant,
  cloned from zork1).

<!-- template:
- [ ] **<one-line summary>** (room: `<Room Name>`, command: `<command>`)
  - **Response**: `<verbatim, trimmed to 5 lines max>`
  - **Hypothesis**: <translator? generator? bootstrap state? sandbox? parser?>
  - **Workaround**: <what you did to keep moving>
-->
