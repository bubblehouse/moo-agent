# Zork II — Completed work

Translator/generator/SDK/config fixes that landed for Zork II. Don't re-do
these; build on them. Mirrors `../../zork-shakedown/references/completed-work.md`.

## Landed

- **Initial port (2026-06-04).** `ZORK2_CONFIG` added to
  `moo/zil_import/game_config.py` (banner, manifest `zork2.zil`,
  `zork_number=2`, MIT license blurb, `reset_body_filename`). First regen
  succeeded on the first attempt — 86 rooms, 165 objects, 437 routines
  (380 emitted, 34 drops). The classic-EZIP-family assumption held: Zork II
  translates like Zork 1.
- **Generator: per-game room-override copy filter** (`generator/__init__.py`,
  the template-verbs copy loop). Hand-written room-instance overrides live
  under the shared `verbs/rooms/<room_slug>/` tree (e.g. zork1's
  `rooms/living_room/turnfunc.py`, `--on "Living Room"`). They were copied
  into *every* game's bootstrap, so zork2's verb load raised
  `Object.DoesNotExist` on a "Living Room" it never created. Fix: restrict
  copied `rooms/<slug>` subdirs to rooms in the current game
  (`_valid_room_slugs`). Game-agnostic; zork1 keeps its override (verified),
  zork2 no longer inherits it. 223 importer unit tests still pass.
- **`_zork2_reset_state_body.py`** created (minimal first-pass): snapshot
  capture/restore + park the Adventurer at Inside the Barrow (ZIL
  `INSIDE-BARROW`, the `GO` start room) + basic zstate + substrate
  property-write grants. Seeds **both** `zstate_always_lit` and
  `zstate_lit=True` — `describe_room` reads the *cached* `LIT` zstate
  directly (not the `is_lit` predicate), so without the `zstate_lit` seed
  the very first `look` reported "It is pitch black." even in a lit room.
- **`zork2_spot.py`** added (`moo/zil_import/scripts/`): the fast iterative
  spot-test tool for the fix loop (`--reset` re-syncs with Celery stopped).

## Verified live (2026-06-04, first session)

`look` (full room banner + description, correctly lit), `south`/`north`
(movement), `take lantern`/`take sword`, `turn on lantern` ("The lamp is
now on."), `inventory`, `examine sword`, `down` at Narrow Tunnel (canonical
"you slip on the crumbling rocks" ravine block). No tracebacks.

## Not yet built

## Landed — first shakedown session (2026-06-04)

- **`drop` fix (shared g-verb relocation).** `drop sword` raised
  `#... (Thing) has no attribute idrop`. `IDROP` is a shared `gverbs.zil`
  routine in `_SKIP_ROUTINES`; its generic hand-written replacement was
  misfiled under per-game `verbs/zork1/thing/helpers/idrop.py`, so only
  zork1 got it. Relocated to shared `verbs/thing/helpers/idrop.py` — the
  body is pure PRSO logic with no zork1-specifics. Now all classic games
  inherit it; zork1 unchanged (gets it from the shared dir).
  **Regression check:** 223 importer unit tests pass; zork1 smoke re-run
  scored 309/350 ("Master") — `drop` fired cleanly throughout (multiple
  "Dropped."), and the FAIL was the documented thief-RNG torch-steal
  cascade (`project_zork_smoke_nondeterministic`, ±50 band), not the idrop
  move.
- **Reset determinism — canonical item placement.** The bootstrap's
  `get_or_create` doesn't reposition objects that already exist, so a prior
  session's inventory (and a lit lamp) survived into the captured snapshot —
  the opener started with the lamp/sword pre-held and the lamp on.
  `_zork2_reset_state_body.py` now force-places `lamp` + `elvish sword` on
  the barrow floor with the lamp OFF on every reset (authoritative over
  snapshot drift). Opener is now deterministic.
- **`zork2_smoke.py` written + green** (`moo/zil_import/scripts/`). 17-command
  assertion-driven walk of the opening spine + core verbs; PASS, idempotent
  across runs. Stops short of the (nondeterministic) Carousel Room.

## Landed — second shakedown session (2026-06-04)

- **Carousel Room wired smoke-safe.** The spinning hub (SW from Path Near
  Stream) randomizes the walk direction at PROB 80 while
  `CAROUSEL-FLIP-FLAG` is unset (CAROUSEL-ROOM-FCN). Canonically the flag is
  flipped by the *robot* pressing the triangular button (the Adventurer
  pressing any button → `JIGS-UP` death). `_zork2_reset_state_body.py` now
  seeds `zstate_carousel_flip_flag=True` — the smoke-safe shortcut, mirroring
  zork1's MAGIC-FLAG/CYCLOPS-FLAG seeds. Verified: `north` → Marble Hall
  reliably (round-trip x2, idempotent x3 runs). The real robot puzzle is a
  future shakedown target (unset the seed to drive it).
- **`ZORK2_CONFIG.npc_atom_map` populated** (12 atoms → exact object names,
  all verified to `lookup()` live): UNICORN/GLOBAL-UNICORN,
  PRINCESS/GLOBAL-PRINCESS, DRAGON, CERBERUS, SERPENT, GNOME,
  GNOME-OF-ZURICH, ROBOT, GENIE (object "demon"), WIZARD. Disambiguates the
  NPC/global-scenery twins so `,UNICORN`/`,PRINCESS` in routines resolve to
  the NPC, not the alias collision. (Generated `unicorn_fcn.py` now
  references `unicorn (UNICORN)`.) 223 importer unit tests pass.

## `zork2_smoke.py` coverage

26 commands: opening spine (8 rooms) + `look`/`inventory`/`take`/`drop`/
`turn on`/`examine`/`go <dir>` + Great Cavern blocked-`east` fail-probe +
the Formal Garden side-trips (North End of Garden — unicorn bounds away;
Topiary) + the now-deterministic Carousel Room → Marble Hall. Extend
room-by-room (next: beyond Marble Hall; Topiary W arbor; the robot).

## Smoke progress

| Date | Pass / Total | Score | Notes |
| --- | --- | --- | --- |
| 2026-06-04 (port) | n/a (by hand) | n/a | First working bootstrap; opener + core verbs clean. |
| 2026-06-04 (shakedown 1) | **17 / 17 PASS** | n/a | `zork2_smoke.py` landed. Fixed `drop`/idrop + lamp-on-reset. Idempotent. |
| 2026-06-04 (shakedown 2) | **26 / 26 PASS** | n/a | Extended through Formal Garden side-trips + Carousel (flag seeded). npc_atom_map populated. Idempotent x3. |
| 2026-06-04 (shakedown 3) | **31 / 31 PASS** | n/a | Extended the ravine chain (Deep Ford → Ledge in Ravine → End of Ledge → Dragon Room) + `examine dragon` (DRAGON-FCN gaze). Mapped Stone Bridge + Topiary→W→Carousel. Logged `diagnose` gap. Idempotent. |

## Open gaps (session 3)

- **`diagnose` missing** — `V-DIAGNOSE` is skipped; zork1's replacement
  depends on `FIGHT-STRENGTH`, a **zork1-only** ZIL routine (zork2's combat
  model differs). Needs a zork2-specific diagnose, not a relocation. Logged
  in BUGS.md. Not a moo-core change — stays game-side when implemented.

Add a row each session.
