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

## Fixed 2026-05-25 (this session)

- ~~**Bulldozer BLOCK-Arthur branch dropped by per-clause splitter**~~ — fixed in `extras/zil_import/generator/__init__.py` (`_emit_verb_clauses` now bails out to single-file emission when verbs overlap across clauses) + `translator/__init__.py` (`translate()` skips top-level VERB?-clause pruning when splitting was bypassed).  `block bulldozer` at Front of House now sets LYING-DOWN, queues I-PROSSER, and prints the canonical "You lie down in the path of the advancing bulldozer".  Same fix applies to BEER-F's M-clause split (drink-beer dispatch).
- ~~**`drink beer` falls through to substrate**~~ — fixed by the same `_emit_verb_clauses` overlap bail-out.  BEER-F now lives in a single `buy.py` whose body has clause 1's NDESCBIT guard (the "buy first" rebuke), clause 2's COUNT, clause 3's TAKE, and the Arthur DRINK/ENJOY branches with DRUNK-LEVEL increment.
- ~~**`hang gown on hook` / `put gown on hook` / `put towel on drain` fall through to substrate**~~ — fixed in `translator/__init__.py` (`_shebang_verb` / `_shebang` now detect PRSO references in the routine body and emit `--dspec any --ispec <prep>:this` for iobj-host action handlers).  HOOK-F's hang/put-on, DRAIN-F's put-on, SATCHEL-F's put-on all dispatch correctly now.
- ~~**V-PUT-ON / V-PUT-IN / V-PUT-UNDER per-object handlers register under `put_on` / `put_in` / etc., never reached by player input**~~ — fixed in `ir.py` (added PUT-ON/PUT-IN/PUT-UNDER/etc. → bare `put` in ZIL_VERBS atom-alias map) + `translator/__init__.py` (V?-atom lookup in PERFORM expressions now consults ZIL_VERBS so `<PERFORM ,V?BLOCK-WITH ,...>` emits the right verb name).
- ~~**Compound-particle ZIL atoms (LIE-DOWN, WALK-AROUND) emit hyphenated verb names that never match player input**~~ — fixed in `expr_handlers.py` (`_h_verb_p` normalises `lie-down`→`lie_down`) + `translator/__init__.py` (`_shebang` residual verbs also normalise) + `generator/__init__.py` (clause_split_verbs).
- ~~**Daemon counter state pollution across sessions** — fixed in `_hhg_reset_state_body.py` (resets BULLDOZER-COUNTER, PROSSER-COUNTER, VOGON-COUNTER, FORD-COUNTER, DEAD-COUNTER, DRUNK-LEVEL, HOUSE-DEMOLISHED, PROSSER-LYING, TOWEL-OFFERED, GONE-AROUND, FORD-GONE, EARTH-DEMOLISHED).  Also seeds LYING-DOWN=False (was True, blocking GROUND-F's lie-down dispatch).~~

## Open

- [ ] **`put satchel on panel` recurses infinitely → `An error occurred while executing the command.`** (room: `Vogon Hold`, command: `put satchel on panel`, identity: `arthur`)
  - **Response**: `An error occurred while executing the command.` (RecursionError in celery)
  - **Hypothesis**: Translator PERFORM semantics. `ROBOT-PANEL-F` has two clauses sharing the routine: `<AND <VERB? PUT-ON> <PRSI? ,PANEL>>` calls `<PERFORM ,V?BLOCK-WITH ,PANEL ,PRSO>`, and `<AND <VERB? BLOCK-WITH SPUT-ON> <PRSO? ,PANEL>>` does the actual block-with logic.  ZIL's PERFORM re-enters the action handler with updated PRSA/PRSO/PRSI; the translator's PERFORM helper (`zork_thing/helpers/perform.py`) is annotated "SETG of parser-state slot is a no-op in DjangoMOO" — it skips the parser-state mutation, so when it calls the host's action handler via `d_apply('PRSI', i.getp('action'))`, the handler re-enters with the ORIGINAL parser context (verb=`put`, prsi=panel), hits the same PUT branch, and recurses.  Generic to any ZIL routine that calls `<PERFORM ,V?OTHER ,ME ,X>` on itself.  Fix: either teach PERFORM to push/pop a parser-state frame around `d_apply`, or have the translator inline cross-clause PERFORM calls when the target action handler is the same routine.
  - **Workaround**: None — blocks the babel-fish puzzle stage 4 (gown→hook + towel→drain + satchel→panel + junk_mail→satchel).  Puzzle progresses through stages 1-3 naturally now (canonical "gown is hanging from hook", "fish slides down the sleeve", "tiny cleaning robot whizzes across the floor").

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
  - **Hypothesis**: M-clause splitter. The auto-emitted `verbs/rooms/bedroom/window/look_inside.py` carries only the non-bedroom branch of WINDOW-F (canonical "country lane"); the bedroom branch is folded into `describe.py` (which handles `examine`/`x`/`describe`/`what` but NOT `look_inside`). When `look out window` dispatches `look_inside`, only the country-lane file fires. Splitter needs to detect when a per-VERB? clause is also handled in a gated outer clause (like `<EQUAL? ,HERE ,BEDROOM>`) and either merge the gated branch into the per-verb file or extend the residual's verb list. `passthrough()` between sibling verbs on the same object isn't supported (passthrough only walks parents), so registering `look_inside` on both files isn't an option.
  - **Workaround**: `look at window` / `examine window` triggers the curtains-open branch and the canonical bulldozer scene.

## Pre-existing limitations surfaced (acceptable for now)

- **`--reset` doesn't reset object positions.** `_hhg_reset_state_body.py` only re-places the Adventurer in the Bedroom and seeds zstate; objects that moved during a previous session stay moved. The gown wasn't restored to the Bedroom across resets, requiring a manual fix-up to re-run the wear puzzle. The Zork reset has the same shape — it operates on the avatar + System Object, not on the world geometry. Promoting this to a proper bug would require either a full world-geometry restore (potentially expensive) or per-object canonical-location tracking.
