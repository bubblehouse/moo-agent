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

## Daemon ticks

HHG's startup daemons run on the realtime scheduler if classified as such by `daemon_modes.py`. Wall-clock elapsing between `send` calls counts toward their tick deadline. To test deterministically, use the connected harness with explicit waits, or stop Celery during state-sensitive setup and restart when ready (mirrors the zork-shakedown pattern).
