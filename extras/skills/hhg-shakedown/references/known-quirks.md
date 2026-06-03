# Known Quirks (HHG)

Pre-existing limitations that are **not bugs** — either canonical HHG behavior or by-design constraints of the current setup. If you trip one, note it as "hit known quirk: \<name\>" in the end-of-session summary and move on.

If something here feels actionable, move it to [BUGS.md](../BUGS.md) (game-side fixable) or [TODO.md](../TODO.md) (needs a moo-core change).

---

## Translation gaps inherited from the feasibility scan

See [../HHG-FEASIBILITY.md](../HHG-FEASIBILITY.md) for the full scan results. Open items as of 2026-05-24:

- **Substrate routine names live under `verbs/thing/helpers/`** rather than as System Object routines. Works for HHG by dispatch fallback but the dispatcher receiver may be wrong for some semantics. Spot-check during shakedown.
- **HHG-specific `SETG`s inside routines other than `GO`** aren't captured by the converter (it only walks top-level forms). If a verb assumes a global was initialised by a routine other than `GO`, the read will return None.

## Identity-switch semantics

HHG's `IDENTITY-FLAG` mutates throughout the game. When debugging identity-keyed text, always verify which identity is active before assuming a wrong-branch bug:

```
hhg_session.py send "examine self"
```

If output reads as if the wrong character is speaking, that's a real bug. If output matches the current `IDENTITY-FLAG` value, the dispatch is correct even if the text feels odd.

## Testing gotcha: the Wizard has `location is None`

When verifying a command via isolated `manage.py shell -c` with `parse.interpret(ctx, cmd)`, the **caller matters**.  The `phil`/Wizard avatar lives in limbo (`location is None`), and `do_command` (the ZIL turnfunc) bails at `if loc is None: return False` BEFORE any of its pre-dispatch plumbing runs (numeric-dobj → INTNUM binding, pronoun resolution, late dobj resolution, multi-object dispatch, …).  A command that depends on that plumbing will therefore appear "broken" when tested as the Wizard but works fine for the real game avatar (the **Adventurer**, who always has a location).

This is exactly what made `footnote <N>` look broken for three sessions — see completed-work.md 2026-05-29.  **Always test gameplay commands as the Adventurer**, not the Wizard:

```python
adv = Object.global_objects.get(site=hhg, name="Adventurer")
with code.ContextManager(adv, out.append, site=hhg) as ctx:
    parse.interpret(ctx, "footnote 6")
```

The connected harness (`hhg_session.py`) already drives the Adventurer, so it doesn't hit this — it only bites isolated-shell spot tests.

### Empty / whitespace `send ""` looks like it "repeats the last command" — it's a harness read artifact

When probing edge cases, `hhg_session.py send ""` (or `"   "`) followed by `read --tail` shows the PREVIOUS command's output, which reads as "blank input repeats the last command." It almost certainly isn't an engine repeat — empty input produces no new server output, so `read` just surfaces the stale buffer. Don't log it as a bug without confirming the server actually re-dispatches (e.g. check for a fresh `>>>` prompt frame with a real body, not the prior one). Gibberish (`xyzzy`) and bare punctuation (`!!!`, `....`) correctly return "I don't know how to do that." / are stripped — those paths work.

## moo-core debug features

### `take #N` lifts objects by primary key

`Parser.get_pronoun_object` (`moo/core/parse.py:641`) treats `#N` as a wizard-style pronoun resolving to `Object.objects.get(pk=N)`. Documented behavior: lets a wizard reach into any object by id from any command that takes a dobj. Not a bug — the PK form is intentional debug tooling. Don't use it during normal play (the take may bypass scoping and move objects you didn't intend, like the SINK-into-Adventurer accident from the first shakedown).

## Canonical HHG behavior that looks like a bug

### Re-entering the house dies on `north` from Front of House

`HOUSE-ENTER-F` (`earth.zil`) is the puzzle gate: while `PROSSER-LYING` is False, going `north` into the house triggers the bulldozer's "just pushed your home down on top of you" JIGS-UP. The I-HOUSEWRECK daemon you might expect doesn't queue until AFTER you've made Prosser lie down (the T branch at the bottom of HOUSE-ENTER-F). Canonical solution: lie in front of the bulldozer first.

### `buy beer` (as Arthur) routes to peanuts

In HHG, `beer` in the Pub has `NDESCBIT` set when the game starts (Ford has already bought enough). The buy verb on the beer object redirects to peanuts: `_.perform('buy', lookup('peanuts'), None)`. Peanuts has no Arthur-identity branch → falls through to V-BUY → "Sorry, the peanuts isn't for sale." This is the game design (Arthur shouldn't be ordering beer in the Pub at game start); only Ford or post-beer-clearing states allow direct beer purchase.

### `close curtains` returns "You must tell me how to do that to your curtains."

Canonical HHG behavior. `<ROUTINE V-CLOSE>` (`verbs.zil`) falls through to `<TELL-ME-HOW>` for any PRSO that lacks `SURFACEBIT`/`ACTORBIT`/`DOORBIT`/`CONTBIT`. Curtains have none of those flags (just a generic SEARCHBIT / NDESCBIT scenery item), so any `close <curtains>` lands on the canonical "tell me how" rebuke. `TELL-ME-HOW` is defined in `globals.zil:` as literally `<TELL "You must tell me how to do that to" <ARTICLE PRSO> "." CR>`. Not a translation bug.

### `wave <anything>` returns "You have no carving instrument."

HHG ZIL is literally `<ROUTINE V-WAVE () <V-CARVE>>` — V-WAVE delegates to V-CARVE, which falls through PRE-CARVE's "no carving instrument" rebuke when STONE isn't held. Adams humor: waving and carving share a stub. Not a dispatch bug; matches canonical Z-machine behavior.

### `look under bed` lists handkerchiefs / book / coins but they're not takeable

The "soiled handkerchiefs, a book you thought you'd lost, a couple of foreign coins" text is canonical HHG flavor in BEDROOM's M-LOOK / look-under handler — NOT real Objects. `take handkerchief` correctly returns "There is no 'handkerchief' here." `take book` and `take coins` hit V-CARVE's rebuke because they're aliases for BEDROOM-FURNISHINGS or another scenery object. Not a bug; matches Z-machine behavior.

### `fill <anything>` returns "Phil who?"

V-FILL in `verbs.zil:1235` is literally `<TELL "Phil who?" CR>` — an Adams joke. There's no implementation; the verb name is recognised but the response is a pun on his name. Not a parser fallback; this is the canonical V-FILL routine. (Same shape as several other `V-` routines that are stubbed with deadpan one-liners.)

### `lie down` (bare) prompts for an object; `lie before / in front of <X>` now blocks

HHG's syntax requires an object after `lie down` / `stand up`:

- `<SYNTAX LIE DOWN OBJECT (FIND RLANDBIT) = V-LIE-DOWN>` — needs floor/ground
- `<SYNTAX LIE BEFORE OBJECT = V-BLOCK>` — `before` / `in front of` / `near` / `against`
- `<SYNTAX STAND UP OBJECT (FIND RLANDBIT) = V-STAND>` — same FIND-default shape

**2026-05-30 update:** the LIE compound dispatcher now routes any canonical `before` preposition — which includes `in front of` (the lexer canonicalises it) — to `block` per the ZIL `LIE BEFORE OBJECT = V-BLOCK` rule, and re-dispatches through the dobj's OBJECT-FUNCTION so `BULLDOZER-F` intercepts it. So at Front of House all of these stop the bulldozer: `block bulldozer`, `stop bulldozer`, `lie before bulldozer`, `lie in front of bulldozer`, `lie down in front of bulldozer`. (See completed-work 2026-05-30.)

Bare `lie down` (no object) produces the substrate prompt "What do you want to lie down?" rather than blocking. The canonical `(FIND RLANDBIT)` default — which would auto-supply GROUND so bare `lie down` routes through GROUND-F → `PERFORM V?BLOCK BULLDOZER` — is **not** implemented in the parser (no FIND-default object resolution). Minor pre-existing gap; the prompt is coherent and the prep phrasings above all work. Not worth a parser change.

`stand` (bare, no particle) DOES work because HHG has `<SYNTAX STAND = V-STAND>`. `STAND` alone exits a vehicle / dismounts.

### Heart of Gold rooms: nautical "fore/aft/port/starboard" ARE now navigable directions

**Updated 2026-06-02** — superseding the old "flavor text only" note. The importer now merges
each exit-direction's own `<SYNONYM>` table (HHG's `syntax.zil`: `<SYNONYM WEST W PORT P>`
/ `<SYNONYM NORTH N FORE F FOREWA>` / `<SYNONYM SOUTH S AFT>` / `<SYNONYM EAST E STARBO SB>`)
into the exit aliases AND the bare-direction dispatcher (completed-work 2026-06-02 "Nautical
directions"). So on the Heart of Gold **`fore`/`aft`/`port`/`starboard`/`forward` now work as
movement commands** — verified live 2026-06-02: from Corridor Fore End, `aft` → Corridor Aft
End, `starboard` → back. The mapping is still **fore = north, aft = south, port = west,
starboard = east, gangway up/down = up/down**, but you no longer have to translate by hand.
(The post-airlock Dark's "exit to port" is still solved with `go south` — that Dark room is
not a HoG room and its exit predates the nautical-alias plumbing; the LYING-ABOUT-EXIT line
lampshades it anyway.)

### Heart of Gold endgame: the improbability-drive WIN works (and how to verify it)

`turn on switch` / `turn on drive` reaches SWITCH-F, and the canonical win ending fires when
`DRIVE-TO-PLOTTER` + `BROWNIAN-SOURCE` + `DRIVE-TO-CONTROLS` are set and I-TEA is running with
`TEA-COUNTER > 6` (completed-work 2026-06-02 — the `RUNNING?`/C-TABLE fix). The nested spare-drive
parts (`generator switch`, `small/large plug`) DO resolve from player input now — `resolve_dobj_late`'s
`peek_into` descends into the transparent held drive (the earlier non-resolution was a stale
red-button `switch` alias, since cleared). So both `turn on switch` and `turn on drive` work.
A full legitimate win still needs the plotter (in the GLASS-CASE, grab it during the Vogon act —
it's gone after ejection) and the Nutrimat-tea solve. To verify just the win MACHINERY from a parked
post-smoke Bridge, force the state via shell (see smoke-workflow "Lesson: RUNNING? / C-TABLE").

### The bulldozer/towel handover is order-sensitive: take the towel only AFTER you stand up

At Front of House, `lie down in front of bulldozer` (or `block bulldozer`) starts the
Prosser/Ford scene. Ford then arrives and **offers** the towel. There are two canonical
branches and the order you act decides which:

- **Take the towel while still `LYING-DOWN`** → `earth.zil:1373` fires: "Er, look, thanks
  for lending me the towel... been nice knowing you... got to go now... He smiles oddly
  and walks down the Country Lane." Ford departs **solo** (FORD-GONE, → LOCAL-GLOBALS,
  FOLLOW-FLAG 5, I-FORD disabled). The Pub drunk subplot is now **unreachable** — Ford
  never reaches the Pub, so `PUB-F`'s M-END `<IN? ,FORD ,HERE>` is false, the beer keeps
  its NDESCBIT, and `drink beer` stays "You'd better buy some first." forever.
- **`wait` through the negotiation first** (FORD-COUNTER 0→1→2: Ford asks about your home,
  Prosser agrees to lie in your place, **"You stand up"**) THEN take the towel → normal
  "Taken.", and FORD-COUNTER 3→4 walks Ford with you to the Country Lane and into the Pub,
  where he buys the beer ("Muscle relaxant...") and the DRUNK-LEVEL subplot opens.

The smoke avoids the trap by polling for **"stand up"** (not just the word "Ford") before
`take towel`. When shaking down by hand, don't break your wait-loop on "Ford" — wait for
the explicit stand-up. (The green-button escape route the smoke uses doesn't need the
beer/DRUNK-LEVEL at all, so it survives the solo-Ford branch; only the Pub act is lost.)

### Engine Room entry: go `south` repeatedly (NOT yes/no, NOT `in`)

The Aft Corridor's `SOUTH PER ENGINE-ROOM-ENTER-F` exit is a persistence gate, not a
yes/no confirm. Each `south` bumps `ARGUMENT-COUNTER` and re-arms the `i-argument`
abort daemon; the prompts escalate (Are you sure? → Absolutely sure? → "I can tell you
don't want to really" → "What? You're joking") and at counter `>4` you enter. Verified
2026-06-01: **`south`×5 consecutively → Engine Room** ("Infinite Improbability Drive
chamber"). `yes`/`no` are the *abort* path (they let the daemon reset the counter), and
`in` does NOT drive this exit (it's the wrong verb). So "yes doesn't confirm" / "can't go
that way on `in`" are both expected — keep typing `south`.

### The Magrathea missile death-timer DOES fire — `rub pad` alone doesn't start I-TEA

Was BUGS.md "Magrathea missile death-timer never fires." **Not a bug** — verified live
2026-06-02. I-TEA is a turn-mode recurring daemon (`<ENABLE <QUEUE I-TEA -1>>`); once it's
in `zstate_queue` it ticks `TEA-COUNTER` +1 every turn, and at `TEA-COUNTER 15` the `(T)`
branch DISABLEs itself and JIGS-UPs ("the missiles struck the Heart of Gold … **** You have
died ****" → respawn in Bedroom, `deaths`+1). Forced-state test: seed `tea_counter=6` +
append `{'name':'i-tea','fire_at_turn':moves+1,'recurring':1}` to `zstate_queue`, then `wait` —
the panic messages run 8–14 and the death lands on turn 9. The recurring re-arm works.

The earlier "never fires" was a **misdiagnosis**: I-TEA was never actually queued. `rub pad`
runs `PAD-F`, which only `<ENABLE <QUEUE I-TEA -1>>`s when **`NUT-COM-INTERFACE` is installed
in the NUTRIMAT** *and* `TEA` is in `PAD`. Without the interface board, `rub pad` falls to the
`SUBSTITUTE in PAD` branch — the "instant but highly detailed examination of your taste buds…"
message that dispenses the *Advanced Tea Substitute* and **does not queue I-TEA**. So the death
clock can't even start until you solve the canonical NUT-COM-INTERFACE / circuit-board puzzle
(Eddie's spare brain → board → install in Nutrimat → `rub pad` with real TEA). The death-timer
machinery is correct; reaching it naturally is gated on the (still-unsolved end-to-end) tea puzzle.

### `dive` is the third arm of `<SYNONYM JUMP LEAP DIVE>` (both games)

`jump`/`leap`/`dive` all print canonical "Wheeeeeeeeee!!!!!" bare (V-LEAP), and route
`<verb> in/out/through OBJECT` to V-THROUGH. Was BUGS.md ("`dive` → What do you want to
through?"): the hand-written `verbs/actor/jump.py` stub claimed only `jump leap`, so bare
`dive` fell through to the JUMP dispatcher whose bare fall-through is V-THROUGH (the real
bare arm, V-LEAP, is in `_SKIP_ROUTINES`). Fixed by adding `dive` to the stub (completed-work
2026-06-02). Both Zork and HHG define the DIVE synonym, so the fix is game-neutral.

## Daemon ticks

HHG's startup daemons run on the realtime scheduler if classified as such by `daemon_modes.py`. Wall-clock elapsing between `send` calls counts toward their tick deadline. To test deterministically, use the connected harness with explicit waits, or stop Celery during state-sensitive setup and restart when ready (mirrors the zork-shakedown pattern).
