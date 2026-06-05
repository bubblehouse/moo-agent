# Deferred Bugs (Rule Zero / out-of-scope)

Items found by `hhg-shakedown` sessions that cannot be fixed without touching `moo/` core. They sit here as a backlog. Each entry notes what would be needed to fix it. Move an item back to `BUGS.md` (and check it off there) once the deeper change has been approved.

Format mirrors `BUGS.md`.

---

- [ ] **Avatar display name should track IDENTITY-FLAG (Arthur / Ford / Trillian / Zaphod)** (user request, 2026-05-30; may be zil_import-only or need a moo-core display hook — investigate)
  - **What the gap is**: the player avatar Object is statically named `"Adventurer"`. The user wants it to display as the current viewpoint character — `Arthur` at the start, switching to `Ford` / `Trillian` / `Zaphod` as the game's `IDENTITY-FLAG` changes.
  - **Context**: canonically HHG's `PROTAGONIST` (`globals.zil:459`) is `DESC "it"` + `INVISIBLE` — narrative says "you", and identity lives in `IDENTITY-FLAG` → the `ARTHUR`/`FORD`/`TRILLIAN`/`ZAPHOD` Objects (each a proper `DESC`, e.g. `"Arthur Dent"`). So `"Adventurer"` is only the DjangoMOO Object-record name; it shows in meta contexts (`@who`, prompt, other players' `look`), not in prose. `IDENTITY-FLAG` is a zstate global already read by `me_f.py` as `IDENTITY-FLAG.desc()`.
  - **Why it's non-trivial**: `"Adventurer"` is a hard-coded lookup key (`_hhg_reset_state_body.py:158`, generator `098_adventurer.py`, the me/identity objects). Cleanest path: keep the internal `name` stable for lookups, drive the *displayed* name from `IDENTITY-FLAG.desc()` (first word). Whether that needs a moo-core change depends on how the engine renders a player's display name (Object `name` vs a `title()`/display hook) — **investigate first; present per Rule Zero if it needs a core hook.**
  - **Related symptom**: the post-airlock Dark prints "The shadow is vaguely \<identity\>-shaped." as "vaguely -shaped." (identity name blank) — same IDENTITY-FLAG-name plumbing.

---

- [ ] **Async daemon output is framed behind the command that triggers it (`>>> ▒▒` mangled bytes; mid-command daemon prints)** (moo-core: `moo/shell/` PREFIX/SUFFIX side-channel)
  - **What the gap is**: A queued daemon's `print(...)` runs inside the Celery task for some *later* command, but its bytes arrive during the synchronous PREFIX/SUFFIX framing window of the command that scheduled it (or the next one). The terminal/harness then sees `>>> ▒▒` (the PREFIX marker with no real text in its frame) and the daemon's actual text leaks into a neighbouring command's output. Surfaces on `take phone` (the `two_trees` → `_.queue('i-reply', 2)` path), on every `south`→Front-of-House transition (I-HOUSEWRECK), on the Vogon fleet/demolition announcements, etc. It also makes the green-button escape window hard to detect by *text* — `hhg_smoke.py`'s `__escape_earth__` works around it by polling game **state** (`take device` succeeding) instead of the daemon text.
  - **Why no game-side workaround exists**: The interleaving is between async daemon output and the synchronous command-response delimiters emitted by `moo/shell/prompt.py` — engine-side, and Rule Zero puts `moo/shell/` off-limits. Changing a specific daemon's timing (e.g. `two_trees`'s 2-tick `i-reply`) would alter canonical game behaviour without fixing the generic case.
  - **Minimal core API that would close it**: a way for daemon/queued output to flush to the connection *outside* the active command's PREFIX/SUFFIX window — e.g. the shell handler draining pending daemon writes and re-emitting its prompt frame after them, or tagging daemon output so it renders on its own line rather than inside the open command frame.
  - **Status**: deferred 2026-05-30. The narrow `take phone` instance was considered for a game-side `print`→`tell` mitigation and rejected: it doesn't address the generic case and changes daemon timing.

---

- [ ] **Ambiguous-object prompt has a stray leading comma and leaks raw `#PK` to the player** (engine-wide; surfaced via HHG `take tool` / `take tools`, 2026-06-03)
  - **What the gap is**: `AmbiguousObjectError.__init__` in `django-moo/moo/core/exceptions.py:46-61` builds the disambiguation message. Live output for `take tool` in the Bedroom (two `TOOL`-synonym objects): `When you say, "tool", do you mean , #6256 (toothbrush) or #6257 (flathead screwdriver)?` — note the `,` immediately after "do you mean" and the raw object PKs.
  - **Root cause**: the separator loop prepends the separator *before* each item including the first. For `index 0` of N≥2 matches, `index < len-1` is True so it appends `", "` before the first name → leading comma. The intent was clearly "separator before every item except the first" (the condition is inverted). PKs come from `str(match)` (Object `__str__` = `#<id> (<name>)`), which is debug-oriented, not player-facing.
  - **Minimal core change**: rewrite the join as `", ".join(names[:-1]) + " or " + names[-1]` (no leading comma; Oxford optional), and render each match by name (e.g. `match.name`/`match.title()`) rather than `str(match)` so players don't see `#PK`. Both are in moo-core (`moo/core/exceptions.py`) → Rule Zero; present before editing.
  - **Impact**: cosmetic but player-facing and affects BOTH games (any ambiguous noun). The leading comma is a clear logic bug; the PK leak is a polish issue.

---

The previous entry on `global_scenery` resolution was retired after confirming that `verbs/system/resolve_dobj_late.py` already implements it via the System Object hook. See `references/completed-work.md` (2026-05-24 — TODO triage). Outstanding `(PSEUDO ...)` per-room scenery is tracked in `BUGS.md` as a regular generator task.
