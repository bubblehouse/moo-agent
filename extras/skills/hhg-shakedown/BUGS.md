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

- [ ] **V-GET-DRUNK / I-VOGONS countdown reaches Vogon scene but doesn't transition to Vogon Hold** (room: `Pub` → `Front of House` → death, identity: `arthur`)
  - **Response**: After 4 beers + waits, the Vogon fleet arrives (counter 1-3 narrative fires), then `**** You have died ****` instead of transitioning to Vogon Hold.
  - **Hypothesis**: The Earth→Hold transition isn't pure-daemon-driven; it requires the player to interact with the THUMB during the I-VOGONS countdown.  Canonical sequence: at VOGON-COUNTER 2 Ford drops the thumb; player must `take thumb` and (eventually) the engine fires JIGS-UP with the "dematerialisation" message, which routes through JIGS-UP's `DREAMING` branch → calls `LEAVE-EARTH` → teleports to Vogon Hold.  Our generated I-VOGONS branch for VOGON-COUNTER==3 with IDENTITY-FLAG=ARTHUR + FORD-NOT-GONE just prints "Ford fights to reach you" and returns — there's no auto-progression because the canonical path requires PLAYER ACTION on the thumb.  Likely needs: investigate the THUMB-PUSH / THUMB-CLICKS / MUNGEDBIT path and whether the IDENTITY-FLAG switches to Ford at the right moment.
  - **Workaround**: Manual `docker exec ... shell -c "adv.location = Vogon_Hold; adv.save()"` to test babel-fish content.

- [ ] **`inventory` returns "I don't know how to do that" and `i` raises "An error occurred"** (room: `Vogon Hold`, identity: `arthur`)
  - **Response**: `inventory` → "I don't know how to do that."  `i` → "An error occurred while executing the command."
  - **Hypothesis**: HHG's SYNTAX rule is `<SYNTAX I = V-INVENTORY>` (the verb atom is `I`, not `INVENTORY`).  `MIGRATED_VERBS` checks for `verb.lower() in MIGRATED_VERBS`, so `i` doesn't get the syntax-row emission and falls through to legacy dispatcher emission.  The legacy `actor/dispatchers/i.py` registers aliases `i m im invent` — but NOT `inventory`.  So typing `inventory` is unknown to the parser.  The `i` exception likely comes from a separate path that has a real traceback worth investigating in celery logs.  **Fix candidate**: add `inventory` as a SYNONYM expansion or extend the dispatcher's alias list when generating the `i` dispatcher.
  - **Workaround**: Player must type `i` instead of `inventory`. The `i` error needs separate investigation.

- [ ] **`take junk mail` doesn't parse (multi-word adjective+noun phrase)** (room: `Front Porch`, command: `take junk mail`, identity: `arthur`)
  - **Response**: `There is no 'junk mail' here.`
  - **Hypothesis**: Parser doesn't combine ADJECTIVE atoms with the SYNONYM noun.  Object `MAIL` has aliases `order, mail, pile, letter` (all work) and adjectives `demoli, junk, my, offici, loose` (none recognized as part of the noun phrase).  Adjective-noun combination is a parser feature not yet supported.  **Not a blocker** for natural flow — `take mail` / `take pile` / `take letter` / `take order` all work and are what players typically type after seeing "pile of junk mail".
  - **Workaround**: Use `take mail` (or any of the other aliases).

- [ ] **`>>> ��` mangled PREFIX bytes during room transitions** (room: any with active daemons, command: `south`/`drink beer`, identity: any)
  - **Response**: `>>> ��` (literal two-byte garbage; command takes 2.3s vs typical 0.4s)
  - **Hypothesis**: Daemon `print(...)` runs in a different output frame than the player's command response.  Filed previously for `take phone` (took 2.4s, same byte pattern).  Generic to any verb that triggers a daemon mid-execution.  This session confirmed it fires on every south→Front-of-House transition (I-HOUSEWRECK daemon firing inside the Celery task's PREFIX/SUFFIX window) and on the 4th `drink beer` (V-GET-DRUNK's PERFORM, likely a queued daemon firing mid-task).
  - **Workaround**: Ignore the garbage; the daemon side effects still apply (we DID move south, we DID get the drunk message). Real bug is in the PREFIX/SUFFIX side-channel framing for queued daemon output.

- [ ] **`take phone` emits mangled `>>> ��` instead of the canonical pickup text** (room: `Bedroom`, command: `take phone` (with toothbrush previously taken), identity: `arthur`)
  - **Response**: `>>> ��` (literal two-byte garbage, took 2.4s vs typical 0.3s)
  - **Hypothesis**: Substrate split / queue interaction. `verbs/rooms/bedroom/phone/take.py` calls `_.zork_thing.two_trees()` which does `_.queue('i-reply', 2)` then `print(...)`. The 2-tick delay fires `i_reply` mid-Celery-task, producing async output during open delimiters. The PREFIX/SUFFIX side-channel writes the second response's prefix bytes but no real text arrives in the framing window, so the harness sees garbage. Either `two_trees` should use `passthrough` for its print, or daemon output needs to be deferred past the SUFFIX marker.
  - **Workaround**: Take the phone without taking the toothbrush first (skips the `two_trees` branch).

- [ ] **`footnote <N>` rejects every numeric argument as "Specify a number"** (room: `Bedroom`, command: `footnote 6`, identity: `arthur`)
  - **Response**: `Specify a number, as in "FOOTNOTE 6."`
  - **Hypothesis**: Translator. The V-FOOTNOTE verb expects the parser to pass a parsed integer (Z-machine `P-NUMBER`), but the dispatcher isn't recognising the number as a valid argument. ZIL's INTNUM/P-NUMBER plumbing isn't wired up — the parser would need to detect numeric dobjs and bind them to `player.zstate_set('P-NUMBER', int(dobj_str))` plus stamp PRSO as a pseudo-object that compares equal to `lookup('intnum')`. Cosmetic — footnotes are flavor — but is a small parser-coverage gap worth closing for completeness.
  - **Workaround**: None; footnotes are unreachable.

- [ ] **`look out window` shows the country-lane fallback instead of the bedroom curtains/bulldozer scene** (room: `Bedroom`, command: `look out window`, identity: `arthur`)
  - **Response**: `You see the country lane.`
  - **Hypothesis**: M-clause splitter. The auto-emitted `verbs/rooms/bedroom/window/look_inside.py` carries only the non-bedroom branch of WINDOW-F (canonical "country lane"); the bedroom branch is folded into `describe.py` (which handles `examine`/`x`/`describe`/`what` but NOT `look_inside`). When `look out window` dispatches `look_inside`, only the country-lane file fires. Splitter needs to detect when a per-VERB? clause is also handled in a gated outer clause (like `<EQUAL? ,HERE ,BEDROOM>`) and either merge the gated branch into the per-verb file or extend the residual's verb list. `passthrough()` between sibling verbs on the same object isn't supported (passthrough only walks parents), so registering `look_inside` on both files isn't an option.  **Related to today's PUB-F fix**: the same generalisation of AND-cond clause extraction could close this if extended from RARG/M-clause dispatch to HERE-gated VERB? clauses.
  - **Workaround**: `look at window` / `examine window` triggers the curtains-open branch and the canonical bulldozer scene.

## Followups to consider

- **Translator coverage report** (deferred from this session) — emit `coverage.json` alongside the bootstrap listing every routine/clause processed vs dropped, with a baseline-ratchet test that fails when new gaps appear.  The PUB-F-style "AND-wrapped M-clause silently dropped" bug would have surfaced on the very first HHG regen if this existed.  Mid-effort feature (~half day); blocked on prioritisation.

## Pre-existing limitations surfaced (acceptable for now)

- **`--reset` doesn't reset object positions to canonical bootstrap state.** `_hhg_reset_state_body.py` only re-places the Adventurer in the Bedroom and seeds zstate; objects that moved during a previous session stay moved.  Manual `adv.location = bedroom; gown.location = bedroom; adv.save(); gown.save()` is required between sessions if the prior session moved objects around (e.g., via warp to Vogon Hold for testing).  This affected at least three sessions this past week — promoting to a proper "world geometry restore" feature would require either a full bootstrap re-init (potentially destructive) or per-object canonical-location tracking baked into the snapshot.
