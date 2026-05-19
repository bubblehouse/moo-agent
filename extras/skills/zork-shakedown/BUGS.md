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

- [ ] **Dam puzzle bolt-turn gating doesn't track yellow-button state correctly** (room: Dam, command: `turn bolt with wrench` after pushing yellow)
  - **Response**: First attempt after pushing yellow once succeeded (combined yellow+red+brown+blue presses); after returning to the Dam, `turn bolt with wrench` failed with "The bolt won't turn with your best effort.", required pushing yellow a *second* time to enable. Inconsistent — appears the bolt-state machine is influenced by something other than YELLOW-FLAG (perhaps WATER-LEVEL or another button toggling it off).
  - **Hypothesis**: `_button_yellow_function.py` or the dam's `pre_turn` is reading a wrong state slot, or another button (brown? red lights toggle?) is unintentionally clearing the yellow flag.
  - **Workaround**: re-push yellow immediately before each `turn bolt with wrench` attempt.
  - **Fix path**: trace which `zstate_*` flag the bolt-turn handler reads; verify the four buttons aren't writing to a shared bit.

- [ ] **Lights-off red button: room descriptions still print fully despite "lights shut off"** (room: Maintenance Room, command: `push red` then `look`)
  - **Response**: After `The lights within the room shut off.`, `look` still prints the full room description as though the lights were on.
  - **Hypothesis**: room's lit-status depends only on the outdoor / always_lit flag and lantern carry; the red-button shutoff doesn't actually flip the room's lit flag. Player still has the lantern so canonically they'd see SOMETHING, but the room-description-was-darkened nuance is missing.
  - **Workaround**: ignore — the red button has no gameplay consequence as a result.
  - **Fix path**: red button's handler in `extras/zil_import/verbs/.../button_red_function.py` should set a room-light flag that the description path honors.

- [ ] **`look` after re-launching boat at Dam Base prints leftover "fatal waterfall" message** (room: Dam Base / R1, command: `board boat; launch; look`)
  - **Response**: `Unfortunately, the magic boat doesn't provide protection from the rocks and boulders one meets at the bottom of waterfalls. Including this one.` — then the actual room name.
  - **Hypothesis**: the river-segment intro routine's print buffer is reused without clearing between sessions or between boardings. The waterfall warning is supposed to fire only at R5 / the falls; here it leaks at R1.
  - **Workaround**: ignore the spurious message; the actual room state is correct.
  - **Fix path**: trace which routine emits "Unfortunately, the magic boat doesn't provide protection" and ensure it's gated on `here == aragain_falls` or similar.

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
  - **Where to start**: `extras/zil_import/translator.py` `translate_routine` and `translate_m_clause`. Add a third emission path that splits by `the_player_verb` clauses. The existing per-VERB? clause splitter (`verb_clauses_for_split`) is precedent. Validate by manually decomposing one god-verb first.
  - **Risk**: medium-high (50+ god-verbs; subtle routing edge cases).
  - **Status (2026-05-10)**: deferred. The 42 god-verbs in the kept tree work correctly; decomposition is a translator refactor that inverts the per-room → per-verb COND structure into per-verb → per-room files. Each god-verb has a different shape (per-room, per-flag, etc.), so the inversion has to handle every shape carefully — and the result is the same dispatch outcome with smaller files. No functional improvement, just structural cleanup. Keeping this as backlog until a god-verb actually misroutes a player command.
