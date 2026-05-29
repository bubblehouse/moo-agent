# Bugs Found (HHG)

Newest first. Format:

```markdown
- [ ] **<one-line summary>** (room: `<Room Name>`, command: `<cmd>`, identity: `<arthur|ford|trillian|zaphod>`)
  - **Response**: `<verbatim, trimmed to 5 lines max>`
  - **Hypothesis**: <translator / generator / bootstrap / IDENTITY-FLAG seed / sandbox / parser>
  - **Workaround**: <what kept the session moving>
```

Fixed bugs are pruned out — see [references/completed-work.md](references/completed-work.md) for the running history. If a bug needs a moo-core change, move it to [TODO.md](TODO.md) per Rule Zero.

---

## Open

- [ ] **Babel-fish: Ford's satchel isn't placed in the Hold on natural arrival (world-geometry restore gap)** (room: `Vogon Hold`, command: `take satchel`, identity: `arthur`)
  - **Response**: After the natural Dark→Hold arrival, `take satchel` → "There is no 'satchel' here."  The satchel is stuck inside off-stage Ford (`ford.location` off-map; `satchel.location == ford`), so the panel-blocking step (`put satchel in front of panel`) can't run.  Gown/towel/junk-mail are fine (gown worn, towel already surfacebit on the drain, mail in inventory).
  - **Hypothesis**: Canonically the I-FORD daemon in the Hold has Ford "take a nap" and drop the satchel into the room (`earth.zil:1221` `<MOVE ,SATCHEL ,HERE> <FCLEAR ,SATCHEL ,TRYTAKEBIT>`).  `FORD-SLEEPING` persisted True across resets (snapshot gap), so the nap never re-armed.  The 2026-05-29 reset now clears `FORD-SLEEPING`, but the satchel/towel/Ford *object positions* are still not restored, and I-FORD isn't queued/Ford isn't present at the natural arrival — so the nap-drop doesn't fire.  Fix: per-object world-geometry restore in `_hhg_reset_state_body.py` (mirror zork1's reset re-placement) for SATCHEL (+ contents), TOWEL, FORD, plus ensuring I-FORD is queued so the Hold nap fires.  **The dispatch half of this puzzle is FIXED** (see completed-work 2026-05-29) — the full natural solve was demonstrated end-to-end by manually placing the satchel (`MOVE SATCHEL HERE`), then `take satchel` / `put satchel in front of panel` / `put mail on satchel` / `push button` → babel fish in ear, +12 score.
  - **Workaround**: `Object…satchel.moveto(hold); satchel.set_flag("trytakebit", False)` via shell, then solve normally.

- [ ] **Green-button double-DISPATCH: V-PUSH runs after green_button_f** (room: `Country Lane`, command: `push green button`, identity: `arthur`)
  - **Response**: `push green button` prints the canonical "Lights whirl sickeningly … You are in…" (green_button_f → LEAVE-EARTH → goto Dark) AND a trailing "Pushing the green button doesn't do anything." / "has no desirable effect." (the V-PUSH substrate).  Cosmetic now — the double-ROLL it used to cause (DARK-F M-ENTER twice) was fixed by the `verb_to_const` look→M-LOOK change, so it no longer flips the dark destination — but the substrate still fires a second, redundant message.
  - **Hypothesis**: `do_command`'s OBJECT-FUNCTION pre-dispatch fires green_button_f (returns truthy → should short-circuit), yet the migrated PUSH runner still reaches the V-PUSH substrate.  Same root as the PRSI gap above: the pre-dispatch hook and the migrated runner both touch the action chain.  Low priority (cosmetic).
  - **Workaround**: Ignore the trailing line; the hitchhike works.

- [ ] **`take phone` emits mangled `>>> ��` instead of the canonical pickup text** (room: `Bedroom`, command: `take phone` (with toothbrush previously taken), identity: `arthur`)
  - **Response**: `>>> ��` (literal two-byte garbage, took 2.4s vs typical 0.3s)
  - **Hypothesis**: Substrate split / queue interaction. `verbs/rooms/bedroom/phone/take.py` calls `_.zork_thing.two_trees()` which does `_.queue('i-reply', 2)` then `print(...)`. The 2-tick delay fires `i_reply` mid-Celery-task, producing async output during open delimiters. The PREFIX/SUFFIX side-channel writes the second response's prefix bytes but no real text arrives in the framing window, so the harness sees garbage. Either `two_trees` should use `passthrough` for its print, or daemon output needs to be deferred past the SUFFIX marker.
  - **Workaround**: Take the phone without taking the toothbrush first (skips the `two_trees` branch).

- [ ] **`>>> ��` mangled PREFIX bytes during room transitions** (room: any with active daemons, command: `south`/`drink beer`, identity: any)
  - **Response**: `>>> ��` (literal two-byte garbage; command takes 2.3s vs typical 0.4s)
  - **Hypothesis**: Daemon `print(...)` runs in a different output frame than the player's command response.  Filed previously for `take phone` (took 2.4s, same byte pattern).  Generic to any verb that triggers a daemon mid-execution.  This session confirmed it fires on every south→Front-of-House transition (I-HOUSEWRECK daemon firing inside the Celery task's PREFIX/SUFFIX window) and on the 4th `drink beer` (V-GET-DRUNK's PERFORM, likely a queued daemon firing mid-task).
  - **Workaround**: Ignore the garbage; the daemon side effects still apply (we DID move south, we DID get the drunk message). Real bug is in the PREFIX/SUFFIX side-channel framing for queued daemon output.

- [ ] **`look out window` shows the country-lane fallback instead of the bedroom curtains/bulldozer scene** (room: `Bedroom`, command: `look out window`, identity: `arthur`)
  - **Response**: `You see the country lane.`
  - **Hypothesis**: M-clause splitter. The auto-emitted `verbs/rooms/bedroom/window/look_inside.py` carries only the non-bedroom branch of WINDOW-F (canonical "country lane"); the bedroom branch is folded into `describe.py` (which handles `examine`/`x`/`describe`/`what` but NOT `look_inside`). When `look out window` dispatches `look_inside`, only the country-lane file fires. Splitter needs to detect when a per-VERB? clause is also handled in a gated outer clause (like `<EQUAL? ,HERE ,BEDROOM>`) and either merge the gated branch into the per-verb file or extend the residual's verb list. `passthrough()` between sibling verbs on the same object isn't supported (passthrough only walks parents), so registering `look_inside` on both files isn't an option.  **Related to today's PUB-F fix**: the same generalisation of AND-cond clause extraction could close this if extended from RARG/M-clause dispatch to HERE-gated VERB? clauses.
  - **Workaround**: `look at window` / `examine window` triggers the curtains-open branch and the canonical bulldozer scene.

- [ ] **`footnote <N>` rejects every numeric argument as "Specify a number"** (room: `Bedroom`, command: `footnote 6`, identity: `arthur`)
  - **Response**: `Specify a number, as in "FOOTNOTE 6."`
  - **Hypothesis**: Updated 2026-05-27: added P-NUMBER plumbing to `verbs/system/do_command.py` — when `dobj_str` is a numeric string, bind `parser.dobj = lookup('intnum')` and store the integer in P-NUMBER.  Need to verify this resolved; if `footnote 6` now prints the canonical Keats letter, close.  Otherwise the verb still has `prso == lookup('intnum')` mismatch or P-NUMBER read mismatch.
  - **Workaround**: None; footnotes are unreachable.

## Followups to consider

- **VERIFY: HHG push/turn objects may share the zork1 OBJECT-FUNCTION-dispatch gap** (cross-game; shared translator/generator).  In zork1, `push`/`press`/`turn` OBJECT never fires the dobj's OBJECT-FUNCTION because the dispatcher-verb substrates are emitted `--on "Thing" --dspec this` and win parser dispatch on the dobj, bypassing the `dispatch_object_function` pre-phase that migrated syntax-row runners perform (full writeup in `zork-shakedown/BUGS.md`).  HHG's `push green button` works end-to-end (the Earth-escape path reaches Dark), so either HHG's green button isn't an OBJECT-FUNCTION reached via the push substrate, or it's handled in a room M-BEG / `do_command` path.  Worth a quick shakedown pass over HHG's pushable/turnable objects (buttons, dials, switches on the Heart of Gold / Vogon ship) to confirm none silently fall through to the generic V-PUSH message.

- **Translator coverage report** (deferred from a prior session) — emit `coverage.json` alongside the bootstrap listing every routine/clause processed vs dropped, with a baseline-ratchet test that fails when new gaps appear.  The PUB-F-style "AND-wrapped M-clause silently dropped" bug would have surfaced on the very first HHG regen if this existed.  Mid-effort feature (~half day); blocked on prioritisation.

## Pre-existing limitations surfaced (acceptable for now)

- **`--reset` doesn't reset object positions to canonical bootstrap state.** `_hhg_reset_state_body.py` only re-places the Adventurer in the Bedroom and seeds zstate; objects that moved during a previous session stay moved.  Manual `adv.location = bedroom; gown.location = bedroom; adv.save(); gown.save()` is required between sessions if the prior session moved objects around (e.g., via warp to Vogon Hold for testing).  This affected at least three sessions this past week — promoting to a proper "world geometry restore" feature would require either a full bootstrap re-init (potentially destructive) or per-object canonical-location tracking baked into the snapshot.  (Precedent: zork1's `_reset_state_body.py` now does explicit per-object re-placement **and** a room-`touchbit` sweep so a fresh run starts fully un-visited — a similar pass would close this for HHG.)
