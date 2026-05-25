# HHG feasibility scan — 2026-05-24

## Verdict

**Continue is viable.** The translator ingests HHG end-to-end and writes a
syntactically-valid `moo/bootstrap/hhg/` tree from
`/Users/philchristensen/Workspace/hitchhikersguide/s4.zil`, completing in one
pass with two pre-existing importer bugs fixed along the way. Whether
HHG is actually *playable* under DjangoMOO is a separate question
beyond this scan's success bar; the multi-POV `IDENTITY-FLAG` mechanic
is the most likely thing to fall over at runtime.

## What translated cleanly

Manifest: `s4.zil` (9 `<INSERT-FILE>`s — misc / heart / parser / syntax /
verbs / earth / vogon / unearth / globals), 1437 top-level forms total.

| Metric            | HHG  | Zork I | Ratio |
|-------------------|-----:|-------:|------:|
| Rooms             |   31 |    110 |  0.28 |
| Objects           |  189 |    140 |  1.35 |
| Routines          |  549 |    439 |  1.25 |
| Tables            |    7 |     41 |  0.17 |
| Globals           |  280 |    202 |  1.39 |
| Syntax rules      |  141 |    132 |  1.07 |
| Synonyms          |   98 |     74 |  1.32 |
| Compound syntaxes |   62 |     46 |  1.35 |
| M-* clause splits |   37 |     64 |  0.58 |
| Generated files   | 1112 |    834 |  1.33 |

All 1112 generated Python files parse under `ast.parse`. Zork I still
translates cleanly and all 168 `zil_import` unit tests pass.

## Bucket A — game-neutral importer bugs (all fixed in this scan)

1. **`<INSERT-FILE …>` arity** — `cli.py:_expand_manifest()` required
   `len(node) == 2`. HHG's manifest uses the 3-arg form
   `<INSERT-FILE "MISC" T>` (the trailing `T` is the
   "treat-as-compiled" flag). Relaxed to `len(node) >= 2`. Without
   this the manifest expander silently skipped every include and the
   converter reported zero rooms/objects/routines.
2. **Apostrophe in `cfg.name`** — log-string emitters used
   single-quoted Python literals (`'{cfg.name} rooms: %d'`) which
   collapsed on `"Hitchhiker's Guide"`. Switched to
   `{cfg.name!r} + ' rooms: %d'` so Python picks the quote style.
3. **Apostrophe in room name** — `_write_test_exits` emitted
   `assert matches, 'no east exit on Marvin's Pantry'`. Switched the
   assertion message to `repr(...)` so any room name survives.

## Bucket B — HHG-specific gaps (deferred)

- **Static `verbs/zork1/` directory copied into HHG output.** The
  generator copies `extras/zil_import/verbs/*` verbatim, which
  includes `verbs/zork1/{echo,pot_of_gold_pre_take,daemons/i_thief,daemons/i_bat}`.
  These are Zork-specific overrides and have no effect on HHG dispatch
  (Zork-only object atoms / NPC daemons), but they're dead files in
  the HHG tree. Not a crash. Defer to a per-game `verbs/<dataset>/`
  copy filter.
- **Substrate classes stay named `Zork *`.** Per the user's "defer
  rename" choice for this scan, HHG inherits the `Zork Root` /
  `Zork Thing` / `Zork Actor` etc. class hierarchy. They live in a
  separate `hhg.local` Site so they don't collide with Zork's, but
  the names will surface in `@parents` output and class lookups.
  Cosmetic only; doesn't affect the success bar.
- **Multi-POV `IDENTITY-FLAG`.** The translator handled it as a
  regular zstate global — `player.zstate_get('IDENTITY-FLAG') == lookup('ford')`
  appears throughout. Whether runtime dispatch actually swaps
  protagonist behavior depends on whether the IDENTITY-FLAG value
  gets seeded with an Object reference (Arthur/Ford/Trillian/Zaphod)
  vs. a string atom — the translator emits `lookup('ford')` so the
  comparison expects an Object. Initialization is in HHG's untranslated
  `MAIN` / `GO` routine which the converter skipped. Likely first wall
  at runtime; flagged for the next session.
- **Substrate routine names from HHG.** The translator emits calls
  like `_.zork_thing.leave_earth()` for HHG-specific helpers
  (`LEAVE-EARTH`, etc.). Those routines DO translate, but they land
  under `verbs/zork_thing/helpers/` instead of as System Object
  routines — works for HHG by accident of the dispatch fallback, but
  there's no signal that the dispatcher receiver is correct for HHG's
  semantics. Worth a spot-check when we try to actually run the game.

## Bucket C — engine support needed (Rule Zero)

**None identified during the translation pass.** The translator and
generator did not request any new `moo/` capabilities to complete HHG
ingestion. The unknowns are all in the runtime behavior (which we
deliberately did not test) — moo-core changes might surface there,
but no Rule-Zero escalation is needed today.

## What changed in this scan

- [extras/zil_import/game_config.py](../../../extras/zil_import/game_config.py) — added
  `player_avatar_atoms` field; added `HHG_CONFIG`; added `GAME_CONFIGS`
  registry + `resolve_game_config()`.
- [extras/zil_import/cli.py](../../../extras/zil_import/cli.py) — added
  `--game-config` flag; derived `--output` default from `cfg.dataset_name`;
  relaxed `<INSERT-FILE>` arity check.
- [extras/zil_import/generator/**init**.py](../../../extras/zil_import/generator/__init__.py)
   — removed module-level `PLAYER_AVATAR_ATOMS`; threaded `cfg` into
  `_gen_rooms` / `_gen_objects` / `_gen_globals` / `_gen_tables`;
  replaced six `'Zork rooms'` / `'Zork objects'` / etc. log strings
  with `cfg.name`-aware emit; fixed apostrophe-safe assertion-message
  emission in `_write_test_exits`.
- [extras/zil_import/tests/test_daemon_modes.py](../../../extras/zil_import/tests/test_daemon_modes.py)
   — re-pointed at `ZORK1_CONFIG.player_avatar_atoms` instead of the
  removed module-level constant.

The `moo/bootstrap/hhg/` tree is gitignored (HHG ZIL has no open
license; the regenerated dataset is research-only and stays out of
version control).

## Next three fixes if we keep going

1. **Try `moo_init --bootstrap hhg --sync --hostname hhg.local`.**
   The Site doesn't exist yet; needs a one-time
   `Site.objects.create(domain="hhg.local", name="hhg")` first.
   This is the next real go/no-go signal: does the bootstrap actually
   load into the DB without raising?
2. **Find and translate HHG's `MAIN` / `GO` initialization routine** so
   `IDENTITY-FLAG` gets a starting value (likely `lookup("arthur")`).
   Without this the very first conditional that reads
   `player.zstate_get('IDENTITY-FLAG')` returns None and every
   identity comparison short-circuits to False.
3. **Per-game `verbs/<dataset>/` filter** — stop copying
   `verbs/zork1/` into HHG output. Small generator change in
   `generate_all`: skip subdirs that match a dataset slug different
   from `cfg.dataset_name`.

## Recommendation

**Continue.** The translator handled HHG well enough that the
remaining unknowns are runtime-side rather than translation-side. The
multi-POV mechanic is the most interesting risk; it'll surface as
soon as someone tries to play, but the translation itself didn't
choke on it.

If runtime testing reveals that multi-POV needs engine support
(parser-time avatar binding, Site-level identity context, or similar),
that's a Bucket C conversation to have separately — Rule Zero still
applies.
