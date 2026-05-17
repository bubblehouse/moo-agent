# Known Quirks

These are pre-existing limitations that are **not bugs** — either canonical
Zork behavior (the game was always like this) or by-design constraints of
the current setup. If you trip one of these, just note it in your
end-of-session summary as "hit known quirk: \<name\>" and move on.

If something in this file feels actionable, move it to [BUGS.md](../BUGS.md)
(game-side fixable) or [TODO.md](../TODO.md) (needs a moo-core change).

## Canonical Zork I behavior

- **Chimney up at Studio: the "with what you're carrying" wording is canonical.** `verbs/zork_thing/object_handlers/up_chimney_function.py` mirrors canonical Zork `UP-CHIMNEY-FUNCTION`: empty-handed climb returns "Going up empty-handed is a bad idea." (forces the player to take the painting); carrying ≤2 items including the lantern lets you climb to Kitchen; anything else returns "You can't get up there with what you're carrying." The wording sounds like a capacity check but really means "you must carry the lantern + at most one other item". The 2026-05-11 shakedown initially logged this as misleading but it's the exact canonical Zork I message — not a bug.
- **Mirror Room is two rooms with the same DESC.** Both halves of the rub-mirror teleport print "You are in a circular room … on a strange-looking mirror …" because the bootstrap appends an atom suffix when display names collide — visible as `Mirror Room (MIRROR-1)` / `Mirror Room (MIRROR-2)` in the DB only; the `desc()` verb strips the suffix from player-visible labels. Players distinguish via exits: south-side leads to Narrow Passage / Tiny Cave / Winding Passage; north-side leads to Cold Passage / Small Cave / Twisting Passage.
- **`break mirror` is irreversible after a teleport.** Canonical Zork: rub teleports, break ends the teleport. The slide from Slide Room → Cellar is the one-way escape if you've broken the mirror on the wrong side.
- **`exits` is not a canonical verb.** Canonical Zork I has no `exits` command — it returns "I don't know how to do that." Players use `look` (which describes available exits as part of the room text) or remember the map.
- **`x` is not an examine alias.** Canonical Zork I `<SYNONYM>` declarations don't include `x` for examine — that came in later Infocom games. Use `examine`, `describe`, or `what`.
- **Inventory fumble at 8+ items.** Canonical ITAKE check: when player carries more than 7 items (`FUMBLE-NUMBER=7`), each subsequent `take` triggers a `cnt * 8`-percent fumble roll that prints "You're holding too many things already!" and fails. At 8 items, ~64% chance per attempt; at 9, ~72%. Zork wants the player to drop or repack into the brown sack — it's deliberate game design.
- **`climb walls` fails at End of Rainbow.** The room description mentions cliffs, but canonical Zork has no UP exit there. The CLIMB dispatcher routes `climb <thing>` → `walk("up")`, which fails because no UP exit exists. The cliffs are decorative scenery.
- **Magic boat punctures on anything sharp in inventory.** Boarding while holding the sword (or sceptre, or other sharp items) instantly punctures the boat — "Oops! Something sharp seems to have slipped..." This is canonical and intentional: the puzzle requires you to drop the sword in the Troll Room (after killing the troll) before the boat sequence. Once punctured the boat can't be re-inflated ("No chance. Some moron punctured it.") and the puzzle is unrecoverable for that run.
- **Smoke reset doesn't clean up `punctured boat` Object.** Dam Base shows BOTH `magic boat` and `punctured boat` after a `--reset` if a prior run punctured one. Cosmetic only — `board magic boat` still works (the punctured one is a separate Object).
- **Boat-river drift cadence is tick-precise.** Each player command (including `look`) consumes 1 queue tick; `wait` consumes 4. River segment delays (R1=4, R2=4, R3=3, R4=2, R5=1) define drift timing. The smoke harness's documented cadence (`wait wait look go east`) is OFF by one tick and leaves you stranded at R3 with a failing `go east`. The **working cadence from R1**: `launch` + `look` × 11 + `go east` (lands at SANDY-BEACH with buoy / shovel accessible; smoke baseline 305-317 has never actually landed these treasures). The smoke's "go east at R4 lands at SANDY-BEACH" expectation matches the runtime; its earlier expectation that `look` at R3 drifts to R4 is wrong because R3's speed is 3 and `look` only ticks once. See [BUGS.md](../BUGS.md) entry on the smoke-cadence mismatch.

## By-design constraints of this bootstrap / harness

- **`zstate_score` and per-room/per-treasure `value` fields reset on `--sync`.** This is intentional — the smoke needs a known starting state. If you deposit a treasure mid-session and someone runs `moo_init --sync` outside this skill, the score resets.
- **`@quit` is the safe SSH disconnect.** `disconnect()` without `@quit` first leaves a server-side session lingering until the SSH timeout. The harness's `stop` subcommand does `@quit` then `disconnect`.

## Substrate substitutions (player-visible behavior unchanged)

These V-routines are intentionally not generated and have working game-side
replacements. Listed so the next session knows where they live and why
replacement was necessary.

- `V-WALK`, `V-WALK-AROUND` — replaced by `_.walk` exit-Object traversal in `extras/zil_import/verbs/system/movement.py`. The substrate would walk Z-machine memory exit tables we don't model.
- `V-CLIMB-UP`, `V-CLIMB-DOWN`, `V-CLIMB-ON`, `V-CLIMB-FOO` — replaced by the CLIMB dispatcher at [moo/bootstrap/zork1/verbs/zork_actor/dispatchers/climb.py](../../../../moo/bootstrap/zork1/verbs/zork_actor/dispatchers/climb.py): `climb <direction>` → `walk(direction)`, `climb <thing>` → `walk("up")`. So `climb tree` works at Forest Path (UP exit exists); `climb walls` at End of Rainbow fails for the canonical reason above.
- `V-LISTEN`, `V-SMELL` — bare-form fallbacks at `extras/zil_import/verbs/zork_actor/listen.py` / `smell.py` print canonical "You hear / smell nothing unexpected." OBJECT-form syntax dispatches to the substrate via the regenerated dispatcher (which now uses `--dspec any` so bare commands fall through to the fallback instead of crashing the substrate on `None.desc()`).
- `V-ECHO` — bare-form fallback at `extras/zil_import/verbs/zork1/echo.py` prints "echo echo ..." and (if in Loud Room) flips LOUD-FLAG so the platinum bar becomes takeable. The canonical V-ECHO walks parser-internal tables we don't materialize. Lives under `verbs/zork1/` (not `verbs/zork_actor/`) because the Loud Room and bar lookups are Zork1-specific atom names.
- `V-LEAP` — bare-form `extras/zil_import/verbs/zork_actor/jump.py` prints "Wheeeeeeeeee!!!!!" The canonical V-LEAP walks Z-machine exit tables to look for a fall-through direction.

## Verb-row duplication on dispatchers (cosmetic)

`Zork Actor` carries multiple `dispatchers/<verb>.py` files that share the same name set when their underlying ZIL action verbs map to the same V-routine (e.g. PULL/ROLL/YANK all → V-MOVE; PUNCTURE/POKE/DESTROY all → V-PUNCTURE). The parser's "shallowest match wins" picks the lowest-pk row, so duplicates aren't player-visible — but `obj.verbs.count()` shows the extras. Generator dedup is possible but the savings are small (~10 rows out of 350+) and the risk is real (changing dispatcher emission ordering could swap which row wins).
