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
- [x] `I-HOUSEWRECK` fires at ~20 ticks — bulldozer arrives — verified 2026-06-03 (fired at exactly turn 20 from a clean reset: `south`→Front Porch then `wait` to turn 20 → "Astoundingly, a bulldozer pokes through your wall…" → BETTER-LUCK demolition. The old "fires immediately" note was stale.)

## Multi-POV switches

**POV machinery mapped (2026-06-01).** All non-Arthur POVs flip `IDENTITY-FLAG` on a dream-room **M-ENTER**, and you reach those rooms from the **Dark** (DARK-FUNCTION's PROB roll picks the destination via DARK-FLAG):

- **Ford** ← `COUNTRY-LANE-F` M-ENTER, branch gated on `HOLD` TOUCHBIT (`earth.zil:1531`); also the Ford bulldozer-replay is `FRONT-OF-HOUSE-F` M-LOOK when IDENTITY=FORD (`earth.zil:560`).
- **Trillian** ← `LIVING-ROOM-F` M-ENTER (`unearth.zil:795`).
- **Zaphod** ← `SPEEDBOAT-F` M-ENTER (`unearth.zil:1029`).
The dream PROBs (`TRILLIAN-PROB`/`ZAPHOD-PROB`/`FORD-PROB`) start at 0 and are armed to 25 only after the `TRAAL-PROB`/LAIR dark roll fires — i.e. the multi-POV dreams are **deep-endgame** (post-Heart-of-Gold improbability-drive) content. This is the clearly-defined next frontier now that the HoG is reachable.

**🎉 ALL THREE DREAM POV SWITCHES TRIGGERED + VERIFIED LIVE 2026-06-04 — first time in project history.** Reached via the legitimate dream-Dark path with **zero translation fixes needed** (the dream/POV machinery translated faithfully). The gateway is **SWITCH-F** (`heart.zil:1721-1728`): `turn on switch` with `DRIVE-TO-PLOTTER` + `BROWNIAN-SOURCE` set but `DRIVE-TO-CONTROLS` NOT set and I-TEA not running → `GOTO DARK` (entry #3+). With `BROWNIAN-SOURCE == TEA` it sets `DARK-CONTROLLED` (deterministic cycle through `DARK-EXIT-TABLE`). In the Dark, the matching sense reveals the clue object → sensing the clue → `LEAVE-DARK` → `GOTO DARK-FLAG` → the dream room's M-ENTER flips `IDENTITY-FLAG`. Sense↔room map (`dark_function.py`): **examine→light** (COUNTRY-LANE "front of eyes"=Ford / SPEEDBOAT "back"=Zaphod), **rub→liquid→taste** (LIVING-ROOM=Trillian / INSIDE-WHALE), **smell→shadow** (HOLD / LAIR), **listen→star-drive→walk south** (ENTRY-BAY / WAR-CHAMBER). The plotter+tea puzzle is gameplay-unreachable post-ejection, so the trigger globals (`DRIVE-TO-PLOTTER`/`BROWNIAN-SOURCE=tea`) were forced via shell (same precedent as the 2026-06-02 win verification); the Dark navigation, `LEAVE-DARK`, and dream M-ENTERs all ran for real through the harness. See completed-work 2026-06-04.

- [x] swap to **Ford** — verified 2026-06-04. DARK-FLAG=COUNTRY-LANE (HOLD touched), `examine darkness`→"front of eyes"→`examine light`→"yellow Sun of Earth"→`LEAVE-DARK`→COUNTRY-LANE-F M-ENTER: "You are hurrying up a country lane…matter transference beam." (BEAM string-global resolves fine — no crash), M-LOOK says "**Arthur's** home" (identity≠arthur). `IDENTITY-FLAG = Ford Prefect`.
- [x] swap to **Trillian** — verified 2026-06-04. DARK-FLAG=LIVING-ROOM, `rub darkness`→liquid→`taste liquid`→"sitting in a glass of white wine"→`LEAVE-DARK`→LIVING-ROOM-F M-ENTER: party intro ("a shy, mousy fellow…named Arthur, and a flamboyant guy named Phil"), `party_desc` renders. `IDENTITY-FLAG = Trillian`. (Surfaced — then RESOLVED 2026-06-04 — a whole embedded Zork I world in site 4 that rendered phantom trophy-case/lantern/sword here; fixed by a full purge + clean re-bootstrap. Re-verified clean. See completed-work 2026-06-04.)
- [x] swap to **Zaphod** (two heads) — verified 2026-06-04. DARK-FLAG=SPEEDBOAT, `examine darkness`→"back of eyes"→`examine light`→"orange Sun of Damogran"→`LEAVE-DARK`→SPEEDBOAT-F M-ENTER: "both your heads are suffering the worst hangover…plan to steal the Heart of Gold." I-SPEEDBOAT steering daemon runs each turn. `IDENTITY-FLAG = Zaphod Beeblebrox`.
- [x] swap back to Arthur — *`ENTRY-BAY-F` M-ENTER sets IDENTITY=ARTHUR (verified incidentally 2026-06-01 on the HoG arrival).*
- **Cosmetic quirk (all 3):** the `LEAVE-DARK` clue tail ("The light resolves itself into…" / "It tastes just like wine…") prints AFTER the destination room's M-ENTER text instead of before it — same `print(…, end='')` no-newline buffering as the Bridge-receptacle ordering quirk (BUGS.md). All text is present; only the order is off.

### Drunk subplot reached 2026-06-01 (NEW — never exercised before)

Played the **alternate Pub intro** end-to-end for the first time (requires the towel-timing in known-quirks — wait for "you stand up" before `take towel` so Ford walks to the Pub):

- `west` into Pub with Ford present → `PUB-F` M-END fires **"Ford buys lots of beer and offers half to you. 'Muscle relaxant...'"** (clears BEER NDESCBIT).
- `drink beer` ×3 plays the canonical narrative (Betelgeuse → "world ends in twelve minutes" → "distant crash... your house being knocked down"), reaching **DRUNK-LEVEL 3 / HOUSE-DEMOLISHED**.
- `east` to Country Lane (DRUNK-3 as Arthur) → `COUNTRY-LANE-F` enables **I-DOG** ("a small dog runs up to you, yapping").
- `north` to Front of House → `FRONT-OF-HOUSE-F` arms **I-VOGONS**; the demolition cascade runs (announcement → **"Ford removes a small black device from his satchel, but accidentally drops it at your feet"** → device lights flicker).
- **Finding: the drunk path CONVERGES with the green-button escape** — it's an alternate route to the same Sub-Etha-device drop, NOT a separate matter-transference. You must `take device` + `push green button` before VOGON-COUNTER hits demolition or you die ("Earth is destroyed by the fleet of Vogon Constructor ships / You have died" → respawn in Bedroom). The "muscle relaxant" beer is flavor; the mechanical escape is identical to the green-button path.

## Key rooms

- [x] Bedroom (`earth.zil`) — verified 2026-05-24
- [x] Front Porch — verified 2026-05-24
- [x] Living Room — reached 2026-06-04 via the Trillian dream-Dark (`taste liquid`→LEAVE-DARK→LIVING-ROOM). M-ENTER party scene + `party_desc` render correctly (clean: `{door, hostess}` + the dream-injected Arthur/Phil/cage — the embedded-Zork phantoms were purged 2026-06-04).
- [x] Country Lane (as a dream-Dark destination) — reached 2026-06-04 via the Ford dream (`examine light`→LEAVE-DARK→COUNTRY-LANE, identity→Ford). (Also reachable early-game via the drunk subplot.)
- [x] Presidential Speedboat — reached 2026-06-04 via the Zaphod dream (`examine light`→LEAVE-DARK→SPEEDBOAT, identity→Zaphod).
- [x] Front of House — verified 2026-05-24 (bulldozer death fires here)
- [x] Back of House — verified 2026-05-24
- [x] Country Lane — verified 2026-05-24
- [x] Pub — verified 2026-05-24 (Ford is in `local globals`, not visible in pub scope)
- [x] Vogon Hold (`vogon.zil`) — verified 2026-05-28 reached **NATURALLY** (Bedroom → block bulldozer → Pub → drink ×3 → Country Lane → wait for fleet → take thumb → push green button → Dark → smell ×5 → examine shadow → Vogon Hold), deaths=0. (Previously only via teleport, 2026-05-25.)
- [x] Dark / improbability-drive sensory puzzle — verified 2026-05-28 (DARK-FLAG=hold via VOGON-PROB roll; `smell` ×5 bumps DARK-COUNTER past 3, reveals the shadow; `examine shadow` → "Ford Prefect" → LEAVE-DARK → Vogon Hold). The "death-race" / sensory gating were snapshot pollution — fixed; see completed-work.md.
- [x] Captain's Quarters (`vogon.zil`) — reached 2026-05-30, **naturally** (babel fish → `wait` → I-GUARDS drags you to the poetry-appreciation chairs). M-LOOK renders ("You and Ford are strapped into poetry appreciation chairs."). Poetry trial (I-CAPTAIN) reads the verses and reaches its `== 6`/`== 11` gate after the `clocker` +1 fix (was a runaway). Required the `goto` VTYPE-gate fix to extract the player from the chair on the GOTO-to-Hold; see completed-work 2026-05-30.
- [x] Airlock (`vogon.zil`) — reached 2026-05-30; "blown out into space" / "scooped up by a passing ship" fires (act-counter reset fix, completed-work 2026-06-01). Now hands off cleanly to Dark(ENTRY-BAY) → Heart of Gold.
- [x] **Post-airlock Dark → Entry Bay** (`globals.zil` DARK-FUNCTION, DARK-FLAG=ENTRY-BAY) — verified 2026-06-01. After "scooped up" (HEART-PROB=100 → DARK-FLAG=ENTRY-BAY), `listen` reveals the star drive ("exit to port"; needs DARK-COUNTER > 3 so `is_missing()` is True — takes ~2 turns to build), then **`go south` → "You emerge from a small doorway..." → LEAVE-DARK → Entry Bay Number Two**. Unblocked by the `_h_prso_p` direction-atom fix (completed-work 2026-06-01) — the `<PRSO? ,P?SOUTH>` exit check had emitted dead `prso == zstate_get('P?SOUTH')` code. NB: the listen text says "exit to port" but the engine only accepts compass `south` (see known-quirks: nautical directions are flavor).
- [x] **Heart of Gold bridge** (`heart.zil`) — REACHED 2026-06-01, first time ever. From Entry Bay, `wait` ticks I-FORD's HEART-COUNTER 1→4: "Heart of Gold!" → GOTO Bridge → Zaphod (multiple heads) / Trillian recognition at the controls → at counter 4 they "head off to port" (→ LOCAL-GLOBALS, canonical) and Marvin appears (I-MARVIN). Bridge M-LOOK renders ("gangway leads down, steam from an entrance to port, Eddie at the console"). Bridge contents: Eddie, handbag, large receptacle, molecular hyperwave pincer, satchel. `take handbag` works.
- [x] **Corridor Fore End + Galley** — reached 2026-06-01 by compass nav (Bridge `down` → Corridor Fore End; `west` → Galley, "nutrimat begins to whirr"). Confirms the whole HoG is navigable. The Vogon-captain intercom announcement daemon keeps firing each turn on the bridge (noisy but harmless flavor).
- [~] **Galley / Nutrimat tea puzzle** — exercised 2026-06-01 (happy path, deepest ever). `examine nutrimat` ("touch-sensitive pad, dispensing slot, service panel"), `ask nutrimat for tea` (Zaphod walks in, gets a Pan-Galactic Gargle Blaster), the PROCESSOR/RESERVE MEMORY OVERLOAD → "SWITCH TO TERMINAL MODE" → "NUMBERS BEING CRUNCHED" sequence all fire. `open panel` **now works** (2026-06-02 — the `THIS-IS-IT`/print_contents crash is fixed; close-then-open → "Opening the Nutrimat reveals a circuit board."); `look in panel` → "circuit board". Tea-machinery dispatch verified crash-free 2026-06-02: `rub pad` → "A cupful of Advanced Tea Substitute appears in the dispensing slot" → starts I-TEA → `examine slot` triggers the **Magrathea missile crisis** announcement (TEA-COUNTER hits 7); `take substitute` / `drink substitute` ("almost, but not quite, entirely unlike tea"). The real win needs BROWNIAN-SOURCE = hot **TEA** (not the Substitute) submerged on the PLOTTER's DANGLY-BIT (`put tea on dangly bit` → `<SETG BROWNIAN-SOURCE>`), which requires connecting Eddie's spare brain via the NUT-COM-INTERFACE/circuit board — the canonical hardest puzzle, not yet solved end-to-end.
- [x] **Magrathea missile crisis** — REACHED 2026-06-01 (the climax). Eddie: "Nuclear missiles have just been launched at us from... the legendary lost planet of Magrathea... all circuits are currently engaged by the Nutrimat... atomic fireball in approximately eight turns." The Engine-Room entry + "receptacle" synonym gaps that earlier blocked the win are both fixed (completed-work 2026-06-01/02); the spare drive is now plugged into the large receptacle in the hhg_smoke. The remaining gate to "missiles turned into a sperm whale" (heart.zil:1654-1700) is the Nutrimat-tea + plotter puzzle (DRIVE-TO-PLOTTER + BROWNIAN-SOURCE). **The 8-turn death timer DOES fire** (verified 2026-06-02 via forced I-TEA seed: counter climbs 6→15, "the missiles struck the Heart of Gold… **** You have died ****", respawn in Bedroom) — the prior "never fires" was a misdiagnosis (I-TEA isn't queued unless the NUT-COM-INTERFACE is installed; `rub pad` alone only dispenses the Substitute). See known-quirks "The Magrathea missile death-timer DOES fire."
- [x] **Engine Room** (Improbability Drive chamber) — REACHED 2026-06-01. Enter via **`south`×5 consecutively** from the Aft Corridor (the `SOUTH PER ENGINE-ROOM-ENTER-F` persistence gate — see known-quirks; yes/no is the abort path, `in` is wrong). M-LOOK: "You're in the Infinite Improbability Drive chamber. Nothing happens; there is nothing to see." Aft Corridor `look` (inter-room routine-call crash) and the `receptacle` synonym gap both fixed this session (completed-work).
- [x] **Spare Improbability Drive revealed + taken** — 2026-06-02. ENGINE-ROOM-F hides its contents until the **third M-LOOK** (`LOOK-COUNTER == 3` moves SPARE-DRIVE / PLIERS / RASP into the room, awards +25, prints "Okay, okay, there are a FEW things to see here." + the spare drive FDESC). `take spare drive` / `take all` work; `examine spare drive` renders "a switch, a long cord ending with a large plug, and a short cord ending with a small plug." LOOK-COUNTER + ARGUMENT-COUNTER were stale-zstate (snapshot never cleared them) → reset-body reseed landed this session (completed-work 2026-06-02). Now in the hhg_smoke.
- [x] **Spare drive plugged into the Bridge large receptacle (DRIVE-TO-CONTROLS)** — 2026-06-02, deepest verified beat on the win path. `plug large plug into large receptacle` → "Plugged. Eddie says 'You shouldn't be playing around with a spare Improbability Drive...'" + the manual-override announcement. The `receptacle` synonym resolves correctly. Bridge M-LOOK then shows "A spare Improbability Drive is plugged into the large receptacle." (ordering quirk — BUGS.md). The drive globals (DRIVE-TO-CONTROLS/PLOTTER, BROWNIAN-SOURCE, HOLDING-NO-TEA, LANDED, TEA-SHOWN, PLANT-BLOOMED) were stale-zstate → reset-body reseed landed this session. Now in the hhg_smoke.
- [x] **Activate the drive → the WIN ENDING FIRES** 🎉 — verified live 2026-06-02. With the full win-state set (`DRIVE-TO-PLOTTER` + `BROWNIAN-SOURCE`=TEA + `DRIVE-TO-CONTROLS` + I-TEA running + `TEA-COUNTER`>6), `turn on switch` → SWITCH-F win branch → *"As you flip the switch, sparks fly… The missiles have turned into a sperm whale at an improbability factor of 2 to the 39,745th power to 1 against… **Good work, kid, says Zaphod**."* Crash-free; post-win `look` stable. This required the **`RUNNING?` fix** (the win gate `<RUNNING? ,I-TEA>` was dead because RUNNING? walked the never-populated C-TABLE instead of `zstate_queue` — completed-work 2026-06-02) AND the stale red-button-`switch`-alias cleanup so `turn on switch` reaches SWITCH-F. Both `turn on drive`/`turn on switch` and the nested part-names now resolve. **Note**: the win-state was forced via shell because the plotter is unreachable from a parked post-ejection state; the legitimate puzzle solve (next bullet) is still open.
- [ ] Plotter / Tree of Foreknowledge / small-receptacle (DRIVE-TO-PLOTTER + BROWNIAN-SOURCE half of the win) — not yet exercised.
- [ ] Sub-etha sense-o-matic interactions
- [x] Babel fish puzzle area — SOLVED 2026-05-29.  All stages work via natural commands (`remove gown`, `put gown on hook`, `put towel on drain`, `take satchel`, `put satchel in front of panel`, `put mail on satchel`, `push button`) → babel fish lands "with a loud squish in your ear", **+12 score**.  Verified end-to-end (full natural playthrough Bedroom → Vogon Hold → babel fish).  Object-function dispatch regression fixed (see completed-work 2026-05-29); one residual: Ford's satchel needs manual placement at the natural arrival (world-geometry restore gap — BUGS.md).  Re-verified 2026-05-29 after the moo-core parser ispec-specificity refactor (`5714867d`): all six same-name/prepositional dispatches (`put...on hook` / `on drain` / `in front of panel` / `on satchel`, `take`, `push button`) still route correctly — no regression.

## Inventory / object interactions

- [x] dressing gown — wear/remove cycle works; `wear`/`remove`/`inventory` now print `your gown` (NARTICLEBIT fix landed)
- [x] toothbrush — verified 2026-05-24 (take prints the canonical "you should be taking more interest…" / tree-collapse text)
- [x] aspirin — verified 2026-05-24 (`take aspirin` triggers swallow + headache-cure text directly)
- [x] pocket fluff — verified 2026-05-24 (take/drop/take cycle works); `put fluff in pocket` → "Done." re-verified working 2026-05-29 (the old "broken" note is stale)
- [x] thing aunt gave you — verified 2026-05-24 (take works)
- [x] junk mail — verified 2026-05-24 (`take mail` / `examine mail` / `read mail` all work)
- [x] towel — verified 2026-05-28 (offered by Ford in the bulldozer scene; carried into the Hold)
- [x] thumb — verified 2026-05-28 (`take thumb` after the fleet drops it; required for `push green button` hitchhike)
- [x] Babel fish — caught 2026-05-29 ("squish in your ear", +12 score) via the full natural puzzle solve

## Failure-mode probes

- [ ] dark room without light → grue-equivalent — HHG appears to use the same "pitch black + grue" text; with `zstate_always_lit=True` we never reach the dark branch
- [ ] commands rejected as "I don't know that word" should give helpful feedback — currently a bare `fill` (no registered verb) resolves to `phil` (Player username), printing `Phil who?` instead of "I don't know how to do that" — see BUGS.md
- [x] `I-HOUSEWRECK` if player stays in bed past tick 20 → bulldozer kills Arthur AND respawns — verified 2026-06-03 (fires at turn 20; the demolition death now teleports the Adventurer back to Bedroom + `DEATHS`++. Was broken: pre-2026-06-03 the death narrative printed but the player kept playing at Front of House — see completed-work.md "HHG terminal deaths now respawn".)
- [x] Death respawn — verified 2026-05-24 (`<JIGS-UP>` deaths via `verbs/system/death.py`) and 2026-06-03 (BETTER-LUCK / sleep / drunk / groggy / brick / ramp deaths, which funnel through FINISH, now respawn too via the `verbs/hhg/thing/score/finish.py` override). All HHG deaths teleport the Adventurer to `player_start` (Bedroom) and bump `DEATHS`.
- [x] `take chair` (non-takeable scenery) — verified 2026-05-24 after `<RFATAL>` translator fix; PRE-CARVE rebuke fires and the chair stays put (was previously also emitting "Taken." and moving the chair into inventory)
- [x] `lie in mud` / `lie on bulldozer` / `lie down` — verified 2026-05-24 after dispatcher --dspec relax + compound preamble prep-fallback + cmd_particle-cleared-from-dobj fix. Bare `lie down` prints "What do you want to lie down?" (canonical missing-dobj prompt); `lie in mud` / `lie on bulldozer` reach the V-LIE-DOWN substrate with the right dobj.
- [x] `look out window` — FIXED 2026-05-29. In the bedroom, `look out window` now fires the canonical curtains/bulldozer scene (was the country-lane fallback). Root cause: the combined OBJECT-FUNCTION emitter hoisted generic `<VERB?>` clauses above the gated `<EQUAL? ,HERE ,BEDROOM>` clause, breaking COND first-match order; now emits clauses in source order (see completed-work.md). The non-bedroom `look_inside` → "You see the country lane." branch is preserved (now correctly ordered after the bedroom branch).

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
- [x] `footnote N` — WORKS (verified 2026-05-29 as the Adventurer). `footnote 6` → "That was just an example." The old "broken" status was a Wizard-avatar test artifact (location is None → do_command bails before the P-NUMBER plumbing); see known-quirks.md.
- [x] `again` / `g` (repeat last command) — **works** (verified 2026-06-02 on the HoG: `again` re-ran the prior command). The earlier "I don't know how to do that" no longer reproduces.
- [x] `oops` (typo correction) — NOT an HHG verb. Confirmed 2026-06-04: `OOPS`/`UNDO` appear nowhere in `syntax.zil` or `parser.zil`; HHG's parser never implemented them. `I don't know how to do that.` is the correct response, not a bug. (Not a known-quirk worth a separate entry — they're simply absent verbs.)
- [x] `undo` — NOT an HHG verb (see `oops` above). `I don't know how to do that.` is correct.
- [x] `score` after death-and-respawn — verified 2026-05-25 (turn counter keeps incrementing across deaths)
- [x] `jump` / `leap` / `dive` — verified 2026-05-25 / 2026-06-02 ("Wheeeeeeeeee!!!!!"). `dive` was the odd one out (bare → "What do you want to through?") until added to the `verbs/actor/jump.py` stub — now symmetric with `jump`.
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
- [x] **Babel fish puzzle stage 4 (`put satchel on panel`)** — **RESOLVED** (superseded by the 2026-05-29 full natural solve — see master "Babel fish puzzle area" entry above). The PERFORM-recursion was fixed by the hand-written `verbs/thing/helpers/perform.py` shim (proper parser-state push/restore via `d_apply`); the whole gown→hook→towel→drain→satchel→panel chain now lands the fish "with a loud squish in your ear", +12 score.
- [x] **Prosser/Ford encounter triggers naturally after `block bulldozer`** — canonical "With a terrible grinding of gears... Ford Prefect arrives... takes a towel from his battered leather satchel"
- [x] **`take towel from ford` works** — towel transfers to inventory
- [x] **Walk Front of House → Country Lane → Pub** — descriptions render correctly

## 2026-05-25 babel-fish push (newly verified or surfaced)

- [x] `take towel` from Ford (after Ford manually moved to Front of House) — fires canonical "Er, look, thanks for lending me the towel... He smiles oddly and walks down the Country Lane."
- [x] walk Front of House → Country Lane → Pub via south, west — descriptions render
- [x] `buy beer` in Pub — fires canonical "Ford Prefect has already bought an enormous quantity for you!" (after Ford manually moved to Pub and `beer.ndescbit=False`)
- [x] `drink beer` — **RESOLVED** (superseded — see line above re NDESCBIT-guard rebuke, and the drunk subplot reached 2026-06-01). `drink beer` ×3 plays the full Betelgeuse → "world ends in twelve minutes" → DRUNK-LEVEL 3 narrative; the pub→Vogon-fleet transition is reachable naturally.
- [x] Vogon Hold M-LOOK description renders correctly (via DB teleport, bypassing I-VOGONS cascade)
- [x] `stand up` in Vogon Hold — clears LYING-DOWN, prints "You are now on your feet."
- [x] `push button` (dispenser) — canonical "A single babel fish shoots out of the slot. It sails across the room and through a small hole in the wall, just under a metal hook."
- [x] `push button` while LYING-DOWN — canonical "You can't reach it from down here." (DISPENSER-F's gating works)
- [x] `hang gown on hook` / `put gown on hook` / `hang gown from hook` / `put towel on drain` — **RESOLVED** (iobj-host ispec + PUT-ON→put alias fixes; superseded by the 2026-05-29 full solve). All canonical: "The gown is now hanging from the hook, covering a tiny hole." / "The towel completely covers the drain."
- **No longer blocked** — the full gown→hook→towel→drain→satchel→panel chain runs end-to-end; the cleaning-robot and fish-in-ear sub-puzzles are exercised (babel fish caught, +12). See master "Babel fish puzzle area" entry.

## 2026-05-25 second pass (newly verified or surfaced)

- [x] `wave fluff` / `wave gown` — canonical Adams routing: V-WAVE → V-CARVE → "You have no carving instrument." (HHG ZIL is `<ROUTINE V-WAVE () <V-CARVE>>`; not a bug, moved to known-quirks)
- [x] `look under bed` — produces canonical handkerchief/book/coins flavor text; the named items are NOT real takeable objects (they're embedded narrative, not PSEUDO entries)
- [x] `lift carpet` / `look under carpet` — canonical "nothing but dust" / "no effect" responses
- [x] `sing` / `dance` / `wave` / `yes` / `no` — all canonical responses
- [x] `eat aspirin` — works (synonym for swallow + headache cure)
- [x] `wash self` — works ("It is now much cleaner.")
- [x] `tell barman about beer` — dispatches to V-TELL with topic ("isn't interested in talking about lots of beer")
- [x] `get in bed` / `stand up` — V-BOARD / V-STAND on bed; works after `<SYNTAX STAND = V-STAND>` plumbing
**2026-06-03 re-shakedown of this whole cluster: almost every item below is ALREADY FIXED by intervening translator/generator work.** Verified live from a clean `--reset`:

- [x] `i` / `m` / `invent` (bare inventory abbreviations) — FIXED. No crash; prints the canonical inventory ("You have: no tea" + gown contents). The old `_.zork_thing.inventory()` crash is gone.
- [x] `i am ford` / `i am self` — FIXED. No crash; `i` matches inventory and the trailing words are ignored (HHG has no "I am X" command). Acceptable.
- [x] `drink from sink` / `drink from basin` — FIXED (no more `None` leak). Now a clean "I don't know how to do that." (the PLTABLE path no longer prints `None`).
- [x] `climb tree` (Back of House) — FIXED. Clean "There is no tree here suitable for climbing." (in Bedroom) — no `>>> ��` mojibake. (The mojibake, when it appears, is the cosmetic shell-layer IAC-GA artifact — BUGS.md open item, not zil_import.)
- [x] `examine wall` / `examine wallpaper` — FIXED. Now the canonical "That's not important; leave it alone." (was the wrong "nothing special about the carpet" BEDROOM-FURNISHINGS first-synonym fallback).
- [x] `close curtains` — canonical (moved to known-quirks: `V-CLOSE` → `TELL-ME-HOW` for non-CONTBIT scenery).
- [x] `lie before bulldozer` — FIXED (moved to known-quirks: the LIE compound dispatcher now routes `before`/`in front of` → V-BLOCK → BULLDOZER-F).
- [x] `throw fluff at washbasin` — FIXED. Single canonical "That's not important; leave it alone." (the iobj is unimportant scenery); no double-message, no stale state, fluff stays in inventory.
- [x] `tell me about X` — FIXED. "You can't talk to an Adventurer!" — note the article is now correctly "**an** Adventurer" (the missing-VOWELBIT bug is gone).
- [x] I-HOUSEWRECK daemon — FIXED 2026-06-03 (now actually kills + respawns; see the `I-HOUSEWRECK`/Death-respawn entries above and completed-work.md).

## 2026-06-03 edge-case / non-happy-path shakedown

Parser-robustness and verb-misuse sweep from a clean `--reset`. Almost everything is solid; two genuine issues found.

- [x] **`take all` / `take tool` / `take tools`** — `take all` grabs gown + toothbrush + screwdriver (all canonical); `take tool[s]` triggers a real disambiguation (toothbrush vs screwdriver). Screwdriver + `name` object confirmed canonical-in-bedroom, NOT leaks (see known-quirks). **Disambiguation prompt is malformed** (leading comma + raw `#PK`) → moo-core bug, TODO.md.
- [x] **`take phone` ×2 (already-touched)** — **BUG**: empty output + 2.3s hang (the `<PERFORM ,V?CALL ,DAIS>` branch silently short-circuits in the perform chain). First take is fine; `call home`/`call <x>` reaches the "cable is down" text correctly. See BUGS.md.
- [x] Conjunction `take X and Y` — both taken. Pronouns `it`/`them` with no antecedent → clean "There is no 'it'/'them' here."
- [x] Malformed input robust: `take the the the screwdriver` → "Taken." (articles stripped); `put screwdriver in basin on bed under carpet` (multi-prep) → graceful single rebuke; `put screwdriver on` (no iobj) → "What do you want to put it in?"; `take 5 screwdrivers` → "There is no '5 screwdrivers' here." (no crash).
- [x] Verb-misuse rebukes all canonical: `open` (bare) → prompt; `eat`/`read`/`wear`/`enter <tool>` → "…wouldn't agree with you" / "How can you read…" / "You can't wear…" / "That would involve quite a contortion."
- [x] `give <item> to me`/`to adventurer` → "…to that." (minor phrasing, known-quirk); `throw screwdriver at window` → "You missed."
- [x] **Death respawn does NOT re-loop**: bulldozer (I-HOUSEWRECK) fired at turn 20 → respawned in Bedroom; played past turn 34 with no re-fire (the daemon does not re-arm on respawn). Front Porch `north` → Bedroom is safe (the death gate is at Front of House, a different room).

### 2026-06-03 (second pass) — deep-game / endgame edge cases (parked at HoG Bridge via hhg_smoke, no reset)

Attached to the smoke's parked frontier (Bridge, score 60/400, turn ~124, spare drive plugged) and probed the HoG / Galley / Nutrimat verb surface. Two new bugs (both BUGS.md); everything else solid.

- [x] **HoG navigation (nautical)** — Bridge `down` → Corridor Fore End; `west`/`port` → Galley; `starboard`/`east` → back. All compass+nautical directions dispatch.
- [x] **Eddie interactions** — `talk to eddie` ("looks at you expectantly"), `ask eddie about tea` (generic), all dispatch. **BUG: `examine eddie` → "the eddie"** (NARTICLEBIT ignored in examine fallback — BUGS.md).
- [x] **Marvin** is daemon flavor only — the I-MARVIN "stalks in / wanders off" text fires on many turns, but `examine marvin` → "There is no 'marvin' here." (he's never a scoped object). Appears to be canonical (Marvin is ambient).
- [x] **Nutrimat / Galley** — `examine nutrimat` (label + pad/slot/panel state), `open panel`/`close panel` cycle (board hidden when closed, revealed when open), `look in panel` → board, `examine board` (full 8-dipswitch description), `read board` ("too small to read"), `search nutrimat` ("wouldn't be polite"), `put board in nutrimat` ("There's no room." — already inside). `rub pad` dispenses the Substitute. **BUG: `ask nutrimat for tea` → ASK-ABOUT fallback** (the `ask` dispatcher ignores the `for` preposition — BUGS.md; `rub pad` is the workaround).
- [x] **Dipswitch puzzle** — `turn first switch` → "Switched. Some lights on the Nutrimat flash briefly…" (ordinal addressing; `set dipswitch N` does not work — see known-quirks).
- [x] **Spare drive / receptacle** — `examine spare drive` (Sirius Cybernetics label, reflects plugged state), `unplug large plug` → "Done.", `pull large plug` → "Why juggle objects?", `take pincer` → "Taken.", `turn on switch` → "Nothing happens." (no win-state). `take board` → "Your load is too heavy." (real inventory-weight limit, not a bug).

### 2026-06-03 (third pass) — aft / Hatchway / Engine Room edge cases + fix verification

After landing the ASK-dispatch + examine-NARTICLEBIT fixes (parked at Bridge via smoke):

- [x] **Aft nav**: Bridge `down`→Corridor Fore End, `aft`→Corridor Aft End, `down`→Hatchway, `up`/`fore` reverse. All compass+nautical dirs dispatch.
- [x] **Engine Room**: reachable via `south` from Aft End (single `south` once the smoke has satisfied the ARGUMENT-COUNTER gate; cold it needs ×5 — known-quirks). M-LOOK renders; `examine/turn on/search generator` → "no 'generator' here" (canonical — no GENERATOR object, flavor like Marvin).
- [x] **Hatchway**: `down`/`out` gated `IF HATCH IS OPEN` (closed → "You can't go that way"); `east`/`starboard` → access-space gate "so narrow… maybe ONE thing" (holding-≤1 constraint, canonical). **BUG: `examine`/`open hatch` → "no 'hatch' here"** (HATCH is LOCAL-GLOBALS but not in the room's GLOBAL list → needs MOBY-FIND; BUGS.md).
- [x] **examine NARTICLEBIT FIX verified live**: `examine eddie` → "There's nothing special about Eddie (the shipboard computer)." (no "the", proper-cased); non-NARTICLEBIT keep "the".
- [x] **ASK dispatch FIX verified live**: `ask nutrimat for tea`→V-ASK-FOR, `ask … about …`→V-ASK-ABOUT (residual: doesn't dispense — BUGS.md; `rub pad` works).
- [x] Win switch no-op safe: `turn on switch` → "Nothing happens.", `press switch` → "Pushing the generator switch accomplishes nothing." (no win-state; no crash). Multi-word `examine heart of gold` fails but `examine heart`/`ship` work (known-quirks).

### 2026-06-03 (fourth pass) — nutrimat tea-ask FIXED + early-game probes

- [x] **`ask nutrimat for tea` DISPENSES** (harness + isolated): "A cupful of Advanced Tea Substitute appears in the dispensing slot." (NUTRIMAT-F ASK-FOR → rub pad). `ask nutrimat for substitute` likewise routes to ASK-FOR; `ask nutrimat about tea` → ASK-ABOUT. The actor-OBJECT-FUNCTION-dispatch + global-topic-resolution fix — completed-work 2026-06-03.
- [x] Early-game edge probes (fresh `--reset`): washbasin/water `turn on`/`drink`/`examine` → "not important; leave it alone" (canonical NDESCBIT scenery); `wear gown`→`open pocket` (reveals aunt-thing/fluff/analgesic); `put gown in pocket` (worn) → "You'll have to remove it first." (sensible refuse, no crash); `search chair` → "not important." `ask arthur about X` (asking self) → "no 'arthur' here" (minor). No new bugs.
- ⚠️ Harness SSH channel dropped once mid-session (`OSError: Input/output error`) right after a successful command; shell logs showed a clean "client disconnected" (NOT an engine crash). Transient — `start --reset` recovered. Watch for recurrence.

### 2026-06-04 (second pass) — `,PRSA` OBJECT-FUNCTION fix + breadth probe

Broad early-game probe of always-available objects and scenery; found + fixed the `,PRSA`
mistranslation (completed-work 2026-06-04 "`,PRSA` in OBJECT-FUNCTIONs").

- [x] **`tie gown` / `untie gown` FIXED** — was silent empty output; now routes through GOWN-F →
  `<PERFORM ,PRSA ,SLEEVES>` → SLEEVES-F (`"Complete waste of time."` WASTES pick / `"It isn't
  tied!"`). `fasten`/`secure`/`attach` synonyms dispatch.
- [x] **`examine house` FIXED** — was `RecursionError` ("An error occurred…"); HOUSE-F's
  `<PERFORM ,PRSA ,HOME>` now redirects correctly → `"You see nothing special about your home."`
  Same fix covers GLOBAL-BED-F / THIRD-PLANET-F / LIGHT-F / MESH-PSEUDO redirects.
- [x] Bedroom scenery breadth: `examine/look-in/turn-on washbasin`/`carpet`/`wallpaper` → canonical
  "That's not important; leave it alone."; `examine window` → curtains-part bulldozer scene;
  `open window` → "jammed shut for months"; `examine curtains` → "nothing special". All canonical.
- [x] Front of House NPC probes: `examine bulldozer` → canonical "really big bulldozers…";
  `foreman`/`mud`/`ford` not in scope pre-scene (canonical — they appear after `lie down`/the scene).
  `enter bulldozer` → "You hit your head…" (V-ENTER rebuke). No crashes.
- [x] **Natural bulldozer death + respawn** re-confirmed: dawdling past the I-HOUSEWRECK/I-VOGONS
  deadline → brick death narrative → score → respawn in Bedroom (FINISH override holds).
- [x] Verb-edge breadth on held items (`squeeze`/`eat`/`burn`/`pour`/`count`/`turn`/`smell` fluff/gown):
  all canonical (`"No, no, a thousand times no. Go boil an egg."` etc.); `burn`/`squeeze` not HHG
  verbs → "I don't know how to do that." No tracebacks.
