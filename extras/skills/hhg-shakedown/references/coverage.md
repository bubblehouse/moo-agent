# Coverage Targets (HHG)

Tick `[x]` when you've personally verified the item works. Don't tick from memory or from the bootstrap source — the point is empirical coverage.

## Opening sequence (canonical from `misc.zil:GO`)

Player starts in Bedroom as Arthur, lying in bed, with three queued startup daemons.

- [x] `look` — bedroom description renders (mentions washbasin, chair, dressing gown, window, phone) — verified 2026-05-24
- [x] identity reports as Arthur — `examine arthur` / `examine dent` / `examine self` all resolve to the avatar (verified 2026-05-24 after avatar_aliases landed). Identity-branched LDESC still not exercised — generic "nothing special" response.
- [x] `examine gown` — refers to the dressing gown pocket contents — verified 2026-05-24
- [x] `wear gown` — verified 2026-05-24 (after `PROTAGONIST` fix; gown ends up on Adventurer, not phantom container; text ordering still wrong)
- [x] `open pocket` — works after gown worn — verified 2026-05-24
- [x] `take aspirin` — verified 2026-05-24 (synonym-expansion fix landed; canonical headache cure text fires)
- [x] `south` or `out` — exits to front porch — verified 2026-05-24 (after `describe_room` + `zstate_lit` fixes)
- [x] front-porch `look` — description renders (canonical text; identity branching not exercised)
- [ ] `I-HOUSEWRECK` fires at ~20 ticks — bulldozer arrives — *fires immediately, not after 20 ticks; daemon scheduling not wired up*

## Multi-POV switches

- [ ] swap to Ford — verify identity-keyed verbs change response — *not reached; `examine self` returns generic response so the identity dispatch isn't observable*
- [ ] swap to Trillian
- [ ] swap to Zaphod (two heads — extra responses?)
- [ ] swap back to Arthur

## Key rooms

- [x] Bedroom (`earth.zil`) — verified 2026-05-24
- [x] Front Porch — verified 2026-05-24
- [ ] Living Room — not reached (Front Porch goes south to Front of House, north to Bedroom)
- [x] Front of House — verified 2026-05-24 (bulldozer death fires here)
- [x] Back of House — verified 2026-05-24
- [x] Country Lane — verified 2026-05-24
- [x] Pub — verified 2026-05-24 (Ford is in `local globals`, not visible in pub scope)
- [x] Vogon Hold (`vogon.zil`) — verified 2026-05-25 (reached via teleport; M-LOOK description renders; `examine dispenser` works; `push button` dispenses fish through the hole)
- [ ] Heart of Gold bridge (`heart.zil`)
- [ ] Sub-etha sense-o-matic interactions
- [x] Babel fish puzzle area — verified 2026-05-25 (dispenser/button mechanics work; standing-up gating works; `hang gown on hook` blocked by dispatcher bug — see BUGS.md)

## Inventory / object interactions

- [x] dressing gown — wear/remove cycle works; `wear`/`remove`/`inventory` now print `your gown` (NARTICLEBIT fix landed)
- [x] toothbrush — verified 2026-05-24 (take prints the canonical "you should be taking more interest…" / tree-collapse text)
- [x] aspirin — verified 2026-05-24 (`take aspirin` triggers swallow + headache-cure text directly)
- [x] pocket fluff — verified 2026-05-24 (take/drop/take cycle works; `put fluff in pocket` is broken — see BUGS.md)
- [x] thing aunt gave you — verified 2026-05-24 (take works)
- [x] junk mail — verified 2026-05-24 (`take mail` / `examine mail` / `read mail` all work)
- [ ] towel — not reached
- [ ] thumb — not reached
- [ ] Babel fish — not reached

## Failure-mode probes

- [ ] dark room without light → grue-equivalent — HHG appears to use the same "pitch black + grue" text; with `zstate_always_lit=True` we never reach the dark branch
- [ ] commands rejected as "I don't know that word" should give helpful feedback — currently a bare `fill` (no registered verb) resolves to `phil` (Player username), printing `Phil who?` instead of "I don't know how to do that" — see BUGS.md
- [x] `I-HOUSEWRECK` if player stays in bed past tick 20 → bulldozer kills Arthur — verified, but fires on the 2nd–3rd command after reaching Front of House regardless of time elapsed (daemon scheduling is wrong; see BUGS.md)
- [x] Death respawn — verified 2026-05-24 (after seeding `System Object.player_start`); JIGS-UP teleports Adventurer back to Bedroom
- [x] `take chair` (non-takeable scenery) — verified 2026-05-24 after `<RFATAL>` translator fix; PRE-CARVE rebuke fires and the chair stays put (was previously also emitting "Taken." and moving the chair into inventory)
- [x] `lie in mud` / `lie on bulldozer` / `lie down` — verified 2026-05-24 after dispatcher --dspec relax + compound preamble prep-fallback + cmd_particle-cleared-from-dobj fix. Bare `lie down` prints "What do you want to lie down?" (canonical missing-dobj prompt); `lie in mud` / `lie on bulldozer` reach the V-LIE-DOWN substrate with the right dobj.
- [x] `look out window` — verified 2026-05-24 after do_command rewrite + hyphen→underscore fix; now dispatches `look_inside` and produces "You see the country lane." (canonical WINDOW-F non-bedroom branch). Bedroom-specific curtains/bulldozer scene still routes via `examine window` (M-clause splitter quirk in BUGS.md).

## System verbs

- [x] `score` — verified 2026-05-24 (READ-outside-REPEAT fix landed last session; the prompt still prints but the score now displays immediately after)
- [ ] `quit` — same `<READ>` recursion pattern as `sleep` — likely crashes; not exercised this run because tearing down the harness
- [x] `sleep` — verified 2026-05-24, re-verified 2026-05-25 (full JIGS-UP → score → RESTART/RESTORE/QUIT prompt → respawn in Bedroom)
- [x] `save` — verified 2026-05-25 (returns canonical `Failed.`; restore also returns `Failed.`; not a translation gap, just a stubbed translator emit — promote to bug only if we want save/restore working)
- [x] `verbose` — verified 2026-05-24 (prints "Maximum verbosity." and re-renders the room)
- [x] `brief` — verified 2026-05-24 (prints "Brief descriptions.")
- [x] `diagnose` — verified 2026-05-24 (no longer crashes; HHG no-op falls through to "I don't know how to do that.")
- [x] `version` — verified 2026-05-24 (no longer prints Zork banner; falls through to "I don't know how to do that.")
- [x] `inventory` — verified 2026-05-24 (flat inventory; pocket put/take verified 2026-05-25 — `take fluff` + `put fluff in pocket` round-trip works)
- [x] `help` / `hint` — verified 2026-05-25 (canonical "dealer / mail order" copyright deflection)
- [ ] `footnote N` — broken; rejects every number with "Specify a number, as in 'FOOTNOTE 6.'" (see BUGS.md)
- [ ] `again` / `g` (repeat last command) — `I don't know how to do that.` (parser-meta gap; HHG ZIL may or may not implement it — check before promoting to bug)
- [ ] `oops` (typo correction) — `I don't know how to do that.` (same caveat)
- [ ] `undo` — `I don't know how to do that.` (same caveat)
- [x] `score` after death-and-respawn — verified 2026-05-25 (turn counter keeps incrementing across deaths)
- [x] `jump` — verified 2026-05-25 ("Wheeeeeeeeee!!!!!")
- [x] `shout` / `yell` — verified 2026-05-25 ("You begin to get a sore throat.")
- [x] `smell` (no dobj) — verified 2026-05-25 ("You smell nothing unexpected.")
- [x] `smell gown` — verified 2026-05-25 ("It smells just like your gown.")
- [x] `kiss self` — verified 2026-05-25 ("This is family entertainment, not a video nasty.")
- [x] `kill <NPC>` / `attack <NPC> with <weapon>` — verified 2026-05-25 (canonical "letting things get to you" deflection)
- [x] `open curtains` — verified 2026-05-25 (canonical bulldozer reveal in bedroom)
- [x] `answer phone` — verified 2026-05-25 (canonical "It is hardly likely that the telephone is interested." — note: probably wrong response, but not a crash)
- [ ] `take phone` — broken; emits `>>> ��` garbage when toothbrush previously taken (see BUGS.md)
- [x] `stand` / `stand up` / `get up` (bare) — verified 2026-05-25 (`allows_bare_invocation` plumbing in translator/generator)
- [x] death respawn — verified 2026-05-25 (bulldozer death by walking `north` into house re-triggers Bedroom)

## 2026-05-25 translator-fix pass (after landing M-clause splitter + iobj-host ispec + PUT-ON alias fixes)

- [x] **`block bulldozer` at Front of House works naturally** — canonical "The bulldozer rumbles slowly toward your home. / You lie down in the path of the advancing bulldozer. Prosser yells at you to for crissake move!!!" (translator overlap-bail + LYING-DOWN reset)
- [x] **`drink beer` in Pub fires the canonical NDESCBIT-guard rebuke** — "You'd better buy some first." (was substrate "You can't drink that!" before the M-clause splitter fix)
- [x] **`hang gown on hook` works** — canonical "The gown is now hanging from the hook, covering a tiny hole." (iobj-host ispec fix)
- [x] **`put towel on drain` works** — canonical "The towel completely covers the drain." (ispec + PUT-ON→put alias)
- [x] **Babel fish puzzle stages 1-3 progress through canonical narrative** — push button dispenses, gown blocks the hole, fish bounces off gown into drain, towel catches, cleaning robot takes fish to panel
- [ ] **Babel fish puzzle stage 4 (`put satchel on panel`) hits PERFORM-recursion** — see BUGS.md.  Translator's PERFORM helper skips parser-state mutation, so when a ZIL action handler PERFORMs another verb on itself the re-entry hits the original verb branch and infinite-loops.
- [x] **Prosser/Ford encounter triggers naturally after `block bulldozer`** — canonical "With a terrible grinding of gears... Ford Prefect arrives... takes a towel from his battered leather satchel"
- [x] **`take towel from ford` works** — towel transfers to inventory
- [x] **Walk Front of House → Country Lane → Pub** — descriptions render correctly

## 2026-05-25 babel-fish push (newly verified or surfaced)

- [x] `take towel` from Ford (after Ford manually moved to Front of House) — fires canonical "Er, look, thanks for lending me the towel... He smiles oddly and walks down the Country Lane."
- [x] walk Front of House → Country Lane → Pub via south, west — descriptions render
- [x] `buy beer` in Pub — fires canonical "Ford Prefect has already bought an enormous quantity for you!" (after Ford manually moved to Pub and `beer.ndescbit=False`)
- [ ] `drink beer` — broken, falls through to substrate "You can't drink that!" — see BUGS.md (M-clause splitter dropped BEER-F's (T) DRINK/ENJOY branches; entire pub→Vogon-fleet transition unreachable naturally)
- [x] Vogon Hold M-LOOK description renders correctly (via DB teleport, bypassing I-VOGONS cascade)
- [x] `stand up` in Vogon Hold — clears LYING-DOWN, prints "You are now on your feet."
- [x] `push button` (dispenser) — canonical "A single babel fish shoots out of the slot. It sails across the room and through a small hole in the wall, just under a metal hook."
- [x] `push button` while LYING-DOWN — canonical "You can't reach it from down here." (DISPENSER-F's gating works)
- [ ] `hang gown on hook` / `put gown on hook` / `hang gown from hook` / `put towel on drain` — all broken, fall through to substrate V-HANG / V-PUT-ON fallbacks — see BUGS.md (dispatcher --dspec this on iobj-host action handlers; blocks the entire babel-fish puzzle chain)
- **Blocked from advancing further into babel-fish puzzle** — without hook/drain/satchel/junk_mail dispatch fixes, the gown→hook→towel→drain→satchel→panel chain can't be exercised, so the cleaning-robot and fish-in-ear sub-puzzles are unreachable.

## 2026-05-25 second pass (newly verified or surfaced)

- [x] `wave fluff` / `wave gown` — canonical Adams routing: V-WAVE → V-CARVE → "You have no carving instrument." (HHG ZIL is `<ROUTINE V-WAVE () <V-CARVE>>`; not a bug, moved to known-quirks)
- [x] `look under bed` — produces canonical handkerchief/book/coins flavor text; the named items are NOT real takeable objects (they're embedded narrative, not PSEUDO entries)
- [x] `lift carpet` / `look under carpet` — canonical "nothing but dust" / "no effect" responses
- [x] `sing` / `dance` / `wave` / `yes` / `no` — all canonical responses
- [x] `eat aspirin` — works (synonym for swallow + headache cure)
- [x] `wash self` — works ("It is now much cleaner.")
- [x] `tell barman about beer` — dispatches to V-TELL with topic ("isn't interested in talking about lots of beer")
- [x] `get in bed` / `stand up` — V-BOARD / V-STAND on bed; works after `<SYNTAX STAND = V-STAND>` plumbing
- [ ] `i` / `m` / `invent` (bare inventory abbreviations) — CRASH on `_.zork_thing.inventory()` (Thing has no inventory verb; lives on Actor). See BUGS.md
- [ ] `i am ford` / `i am self` — CRASH (same root cause + dobj capture failure through compound `i am X` shape)
- [ ] `drink from sink` / `drink from basin` — prints `None` (PLTABLE not loaded from converter; V-COUNT → `_.pick(None)`). See BUGS.md
- [ ] `climb tree` (Back of House) — `>>> ��` garbage (same shape as `take phone`)
- [ ] `examine wall` / `examine wallpaper` — returns "There's nothing special about the carpet" (BEDROOM-FURNISHINGS first-synonym fallback). See BUGS.md
- [ ] `close curtains` — "You must tell me how to do that" (no V-CLOSE handler on curtains). See BUGS.md
- [ ] `lie before bulldozer` — dispatches to V-DIG. See BUGS.md
- [ ] `throw fluff at washbasin` (after fluff thrown away) — stale state + double-message. See BUGS.md
- [ ] `tell me about X` — "You can't talk to a Adventurer" (missing VOWELBIT on Adventurer). See BUGS.md
- [ ] I-HOUSEWRECK daemon at Front of House — prints death narrative but does NOT actually kill/respawn. Score keeps incrementing, player remains in scope. See BUGS.md
