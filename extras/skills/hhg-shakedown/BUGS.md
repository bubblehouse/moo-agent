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

- [ ] **`<JIGS-UP>` deaths skip HHG's DREAMING/POV-switch cleanup (dead `Thing.jigs_up`)** (deep-endgame / multi-POV frontier; found 2026-06-03 while fixing the FINISH respawn)
  - **What's wrong**: `<JIGS-UP msg>` is in `SDK_HEADS`, so it emits `_.jigs_up(msg)` → the System Object `verbs/system/death.py`, a *simplified* respawn (print msg → teleport `player_start` → `DEATHS`++). The generated `Thing.jigs_up` (translated from ZIL's `<ROUTINE JIGS-UP …>`) carries the whole **DREAMING** branch — the Ford/Trillian/Zaphod object-restore + `<LEAVE-EARTH>` / `_.goto(dark)` that ends a POV dream and returns you to the Dark with state cleaned — but nothing ever calls `_.thing.jigs_up(...)`, so that branch is **dead code**. A death *inside a dream* therefore respawns to Bedroom instead of running the dream-exit cleanup.
  - **Hypothesis**: the right fix is probably to make `verbs/system/death.py` **delegate** to `_.thing.jigs_up(args[0])` (the full generated routine — its non-dream path now respawns correctly via the 2026-06-03 HHG `finish()` override, and its dream path does the cleanup) rather than reimplementing a partial death. **CAUTION**: `death.py` is **shared with Zork** (Zork's reset also seeds `player_start` for it), and Zork's own elaborate `Thing.jigs_up` (DEAD flag / Land of the Living Dead / forest_1) is dead for the same reason — so changing `death.py` needs a Zork death regression pass too. Defer until the multi-POV dream content is actually reachable (it's post-Heart-of-Gold improbability-drive endgame).
  - **Workaround**: none needed yet — no reachable dream-death today. Logged so the multi-POV session doesn't rediscover it cold.

- [ ] **Bridge `look` prints the receptacle-plugged line ABOVE the room description** (room: HoG `Bridge`, command: `look`, identity: `arthur`)
  - **Response**: after DRIVE-TO-CONTROLS, `look` shows `Bridge` / `A spare Improbability Drive is plugged into the large receptacle.` / `This is the bridge of the Heart of Gold...`. ZIL order is the room-description TELL first, then the appended `<TELL " "> <PERFORM V?EXAMINE LARGE-RECEPTACLE>`.
  - **Root cause (confirmed live 2026-06-02)**: the write channel is **line-buffered** — a `print(...)` *with* a trailing newline flushes immediately, but a `print(..., end='')` (no newline) stays buffered. BRIDGE-F emits the banner `print("Bridge")` (flushes), then the room desc `print("This is the bridge…", end='')` (no CR — ZIL's TELL has no CR there; the receptacle line was meant to continue the paragraph) which stays **buffered**, then `_.perform('examine', large_receptacle)`. The perform runs LARGE-RECEPTACLE-F as a **sub-verb**, whose `print("A spare…receptacle.\n")` flushes on sub-verb completion — *before* BRIDGE-F's own task ends and flushes the held room-desc line. So the order becomes banner, receptacle, room-desc.
  - **Why still open**: a clean game-side fix would be a translator peephole that flushes a no-CR `print(…, end='')` before a following `_.perform(...)`/sub-verb dispatch (i.e. emit the room desc WITH a newline when a PERFORM follows — cosmetically identical, since the sub-verb output always lands on its own line anyway). Deferred this session: broad blast radius across both games for a single cosmetic instance (only the Bridge, only post-DRIVE-TO-CONTROLS). The buffering itself lives in `moo/core` (off-limits, Rule Zero). All text is present; only the order is wrong.

- [ ] **`>>> ��` mangled-PREFIX artifact on every command in the Dark** (room: `Dark`, command: any, identity: `arthur`)
  - **Response**: trailing `>>> ��` (mojibake) after each `dark_function` response (e.g. after `listen`, `go south`).
  - **Hypothesis**: the `>>> ��` is the IAC GA bytes (`0xFF 0xF9`) the shell emits after each prompt, decoded as U+FFFD — a shell-layer cosmetic artifact, NOT a zil_import issue. Cosmetic only; the real text renders correctly above it.
  - **Workaround**: ignore the `>>> ��` line; the actual output is intact.
