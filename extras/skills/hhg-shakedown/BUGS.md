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

- [ ] **Vogon act daemon lifecycle: i-ford's DISABLE at GUARDS-COUNTER == 6 doesn't stick; player oscillates back to the Hold instead of landing in Dark** (room: `Vogon Hold` / `Airlock`, command: `wait` ×N after the babel fish, identity: `arthur`)
  - **Response**: after the babel fish, the guards drag you to the poetry chairs, the captain spaces you, and you're thrown in the airlock — but instead of `AIRLOCK-COUNTER` reaching 4 → "scooped up by a passing ship" → Dark, the sequence loops: `GUARDS-COUNTER` runs away (observed 38–67), `AIRLOCK-COUNTER` sits at 4, and `loc` returns to `Vogon Hold` with `DARK-FLAG=False`.
  - **Hypothesis**: the **`clocker` +1 fix (2026-05-30, completed-work)** made the counters step cleanly so `CAPTAIN-COUNTER`/`GUARDS-COUNTER` now reach their `== 6`/`== 11` gates — but a **second, independent daemon-lifecycle bug remains**: i-ford's `_.cancel('i-ford')` at the `== 6` gate (it self-re-queues at the top of its body with `_.queue('i-ford', -1)`) doesn't reliably remove it, so after the airlock fires once the player returns to the Hold (likely `HOLD-F`'s M-END re-arming i-ford for the satchel-drop branch now that `captains_quarters.touchbit` is set), i-ford re-enters the guard branch and the cycle repeats. Also seen: `POEM-ENJOYED` was apparently True without the player ever typing `enjoy poem` (i-captain ran to 11 via the enjoy-path), worth confirming the `POEM-ENJOYED` default / gibberish-branch translation in `i_captain.py`. Likely fixable in `moo/zil_import/verbs/system/queue.py` (cancel-vs-self-requeue ordering) and/or `verbs/rooms/hold/hold_f.py` (re-arm guard), but needs a focused session. Verify the airlock→DARK→ENTRY-BAY (Heart of Gold) hand-off afterward: the post-airlock Dark uses the `listen`/`go` star-drive puzzle (DARK-FLAG=ENTRY-BAY), NOT the `smell`/`examine shadow` path the green-button escape uses.
  - **Workaround**: none yet. The poetry trial itself now works at human pace (verified: `CAPTAIN-COUNTER` 2→4→6 with the old build, clean to its gate with the +1 build). The smoke's `_survive_vogons` sentinel exists (in `hhg_smoke.py`) but is **not wired into `HHG_COMMANDS`** until this lands — re-add `("__survive_vogons__", "scooped up")` once the guard/airlock loop is fixed.
