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

- [ ] **`zork1_smoke.py` boat-cadence assertions are off by one tick** (file: `extras/zil_import/scripts/zork1_smoke.py:704-712`)
  - **Response**: smoke's `wait wait look go east` sequence at the river leaves the player at RIVER-3 with `go east` failing because R3's east exit doesn't exist; the drift R3→R4 doesn't fire in time. Smoke logs `'go east' did not contain 'sandy'` and the subsequent `take buoy` / `take emerald` / `take shovel` / `take scarab` all fail with "no X here." The smoke's score baseline of 305-317 has **never** included the boat-leg treasures (buoy=4, emerald=10, shovel=0, scarab=5 → ~19 missing points).
  - **Hypothesis**: bookkeeping miscount in the smoke author's comment block. R1=4, R2=4, R3=3, R4=2, R5=1 ticks per drift. The smoke claims `look` at R3 drifts to R4 (R3 has speed 3, look = 1 tick → doesn't drift). The working cadence is `launch` + `look × 11` + `go east` (1+4+4+3 = 12 ticks total = land at SANDY-BEACH with R4 east exit). Verified live: at SANDY-BEACH the buoy, shovel, and scarab-via-Sandy-Cave-dig flow all succeed.
  - **Workaround**: drive the boat-leg manually with the corrected cadence — verified end-to-end during the 2026-05-17 boat shakedown.
  - **Fix path**: rewrite `ZORK_COMMANDS` boat block to use `launch` + 11 ×`look` + `go east` + `disembark boat` + `take buoy/open/emerald/shovel` + `go northeast` + 3 ×`dig` + `take scarab`. ALSO ensure no sharp object (sword, sceptre) is in inventory before `board magic boat` — sword puncture is canonical but currently happens in the smoke at Dam Base because the sword isn't dropped after the Troll Room.

- [ ] **Loud Room duplicates the platinum bar in room descriptions** (room: `Loud Room`, command: any room render)
  - **Response**: `On the ground is a large platinum bar.\nOn the ground is a large platinum bar.` (verbatim, appearing twice).
  - **Hypothesis**: every room's auto-translated `M-LOOK` body ends with an explicit `_.zork_thing.describe_objects(True)` call AND `V-FIRST-LOOK` (called on entry by `M-ENTER`) ALSO calls `describe_objects()` after `describe_room()` invokes the room's M-LOOK. The room intro text gets printed once (M-LOOK falls through describe_room), but `describe_objects` runs twice — first from inside the room's M-LOOK, then from first_look's tail. Most rooms hide this because their first-loop items lack `first_description`; the Loud Room's bar has one ("On the ground is a large platinum bar."), so the duplicate is visible.
  - **Workaround**: cosmetic.
  - **Fix path**: in `extras/zil_import/translator/__init__.py` `translate_m_clause`, when the constant is `M-LOOK`, stop appending the trailing `_.zork_thing.describe_objects(True)` call — let `V-FIRST-LOOK` be the only call site. Cross-cutting (touches every room's `look.py`), so worth a dedicated pass with smoke verification.

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
