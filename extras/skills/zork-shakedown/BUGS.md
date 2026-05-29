# Bugs Found

Newest first. Format:

```markdown
- [ ] **<one-line summary>** (room: `<Room Name>`, command: `<cmd>`)
  - **Response**: `<verbatim, trimmed to 5 lines max>`
  - **Hypothesis**: <translator / generator / bootstrap / sandbox / parser>
  - **Workaround**: <what kept the session moving>
```

When a bug is verified fixed, move the entry to
[references/completed-work.md](references/completed-work.md) — don't leave
ticked entries here. Items deferred to a deeper layer (parser features,
moo-core changes) live in [TODO.md](TODO.md), not here.

Canonical-or-cosmetic items that are NOT bugs live in [references/known-quirks.md](references/known-quirks.md),
but don't move items there unless you are explicitly instructed.

---

- [ ] **`push`/`press` OBJECT never fires the dobj's OBJECT-FUNCTION (buttons, dam bolt, …)** (room: `Maintenance Room`, command: `press yellow button`)
  - **Response**: `Pushing the yellow button isn't notably helpful.` (generic V-PUSH) instead of `Click.` (button_f, which sets GATE-FLAG).
  - **Hypothesis**: generator. Dispatcher-verb substrates (`thing/substrate_verbs/push.py`, `turn.py`, `slide.py`, …) are emitted `--on "Thing" --dspec this`, so `push X` parser-matches the substrate on the dobj (search rank 3, last-match-wins) and runs V-PUSH (`hack_hack`) directly — bypassing both the Actor dispatcher AND the `dispatch_object_function` pre-phase that migrated syntax-row runners perform. The Option-A muting pass (`generator/__init__.py` ~L2643) only sets `--dspec none` when every shebang name is in `MIGRATED_VERBS`; PUSH/TURN/etc. were never migrated. Confirmed via parser trace: `press yellow button` → `press {on Thing}`, `this=yellow button`.
  - **Workaround**: none in-world. Affects every push/turn OBJECT-FUNCTION in real play (yellow/blue/red/brown buttons, dam bolt). Score-neutral in the smoke (the wrench the yellow button gates is thief-stolen anyway).
  - **Deferred**: architectural. Either migrate PUSH/TURN to syntax-row runners, or mute the dispatcher-verb substrates AND resolve the cross-dispatcher alias ambiguity (`press` is shared by the push/turn/slide dispatchers, so muting reroutes it by verb_id tiebreak and can pass the wrong canonical verb to the OBJECT-FUNCTION ladder). Adding the pre-phase to the Actor dispatcher alone is a no-op (the substrate wins parse — verified, then reverted). Won't move the smoke score.

- [ ] **NPC-direct command pattern not implemented: `<npc>, <verb>`** (room: any, commands: `wizard, hello`, `wizard, jump`, `troll, take axe`)
  - **Response**: `I don't know how to do that.`
  - **Hypothesis**: canonical Zork's `<object>, <command>` syntax routes the command through the addressed object's PERFORM. Our parser doesn't split on the comma+space pattern to retarget the dispatcher.
  - **Workaround**: use direct verbs (`give axe to troll`) which mostly route to the same logic.
  - **Deferred**: parser feature, likely needs `moo/core/parse.py` changes. Move to TODO.md if/when a player tries to script with this syntax.

- [ ] **Brief and superbrief modes don't suppress room descriptions on re-entry** (room: any, command: `brief` / `superbrief` then revisit)
  - **Response**: full description prints on every visit regardless of mode
  - **Hypothesis**: V-BRIEF / V-SUPERBRIEF set the verbosity flag but V-LOOK / FIRST-LOOK doesn't honor it. Per-room M-LOOK clauses ignore VERBOSE-FLAG and always print the long-form desc.
  - **Workaround**: tolerate the longer output.
  - **Deferred**: Plan Phase 2F (high-risk, touches every per-room M-LOOK).

- [ ] **B1. Decompose god-verbs into per-verb files**
  - ZIL `OBJECT-FUNCTION` blocks emit a single 30+-name shebang with `if the_player_verb in [...]` switches in the body (e.g. `iboat_function.py`). Decomposing into per-verb files lets DjangoMOO's parser do natural verb dispatch with `passthrough()` for substrate fall-through, drops `run_v_routine` cascades, removes the `rarg` lifecycle parameter.
  - **Where to start**: `moo/zil_import/translator.py` `translate_routine` and `translate_m_clause`. Add a third emission path that splits by `the_player_verb` clauses. The existing per-VERB? clause splitter (`verb_clauses_for_split`) is precedent. Validate by manually decomposing one god-verb first.
  - **Risk**: medium-high (50+ god-verbs; subtle routing edge cases).
  - **Status (2026-05-10)**: deferred. The 42 god-verbs in the kept tree work correctly; decomposition is a translator refactor that inverts the per-room → per-verb COND structure into per-verb → per-room files. Each god-verb has a different shape (per-room, per-flag, etc.), so the inversion has to handle every shape carefully — and the result is the same dispatch outcome with smaller files. No functional improvement, just structural cleanup. Keeping this as backlog until a god-verb actually misroutes a player command.
