# Beyond Zork — Open Bugs

Bugs found via shakedown. Newest first. Each entry has a hypothesis +
workaround. See `../zork-shakedown/BUGS.md` for the entry format and the
mature example.

## Second shakedown — 2026-06-07 (village → Accardi → Guild Hall + Weapon Shop)

Reached the Guild Hall Lobby + Weapon Shop + Babbling Brook. **Nine bugs fixed
across the Mode-2 passes** — see
[references/completed-work.md](references/completed-work.md). Resolved: raw-mode
line fragmentation (zout coalescing), `examine <USELESS scenery>` crash, PRINTD
ordering, `examine me`/`door` misresolution (P-IT-OBJECT invariant), `wait`
crash (clocker shim), `inventory` rejection (VERB-SYNONYM + migration gate), the
Weapon Shop SHOP-DOOR crash (bare-object TELL), the PLTABLE missing length
prefix, and PICK not stripping that prefix. The smoke
(`scripts/beyondzork_smoke.py`) now passes 24/24 and asserts these. Still open
below: the forest/moors maze (exit-table model), the M-EXIT gags, and a stray
Weapon-Shop line.

- [ ] **Forest / moors maze setup (`SCRAMBLE`) crashes — exit-table XROOM
  byte-model gap** (room: `Babbling Brook` `west` → forest; also Moor's Edge
  `south` → moors)
  - **Response**: `An error occurred`. Celery: first `int + Object` in
    `ztables.py` (fixed — PLTABLE prefix), now `'int' object has no attribute
    'set_flag'` at `scramble.py:80` (`home.set_flag` where `home` is an int).
  - **Root cause (partial)**: `SETUP-FOREST?`/`SETUP-MOOR?` call `SCRAMBLE`,
    which walks the rooms via the Z-machine exit-table model — `<GETP rm dir>`
    is expected to return a byte table whose `XROOM` cell is the destination
    room. `NEW-HOME?` reads `<GET <GETP rm dir> ,XROOM>` into `GOOD-DIRS`, then
    `home = NEW-HOME?(...)` should be a room Object but comes back an `int` (0 /
    the count) because our engine stores room exits as **Exit Objects**, not the
    byte-addressable `[XTYPE, XROOM, …]` tables the maze code reads and mutates
    (`NEW-EXIT?`/`CONNECT`). The PLTABLE-prefix fix (completed-work.md) cleared
    the first crash; the remaining blocker is this exit-table model.
  - **Scope**: large — needs a byte-table exit representation for maze rooms
    (XTYPE/XROOM cells) that `zaddr_*` can read/mutate, OR a game-side rewrite of
    `SCRAMBLE`/`NEW-HOME?`/`NEW-EXIT?` over Exit Objects. Blocks BOTH the forest
    and the moors (the two largest remaining areas). Deferred.
  - **Workaround**: none — the forest and moors are unreachable. Everything
    else (village, coast, Accardi, Guild Hall, Weapon Shop) is reachable.

- [ ] **Weapon Shop emits a stray `I don't know how to do that.` each turn**
  (room: `Weapon Shop`, command: any — `look`, `north`, …)
  - **Response**: the line appears mid-render, e.g. between the description and
    `Your attention comes to rest on a glass display case…`.
  - **Hypothesis**: the `IN-WEAPON-F` M-ENTERING runs `GET-OWOMAN-AND-CURTAIN`
    (places the old woman + her per-turn behaviour daemon `I-OWOMAN`); that
    daemon dispatches a verb/action that doesn't resolve, surfacing the
    parser's `NoSuchVerbError` text. Not an exception (no traceback) and the
    room still works — low priority. Check the owoman daemon's queued action.
  - **Workaround**: ignore the line; navigation/examine/inventory all work.

- [ ] **M-EXIT room-action gags never fire — RFATAL doesn't block movement**
  (rooms: `The Rusty Lantern` west-exit dagger-throw; `Outside Guild Hall`
  north-exit nymph block; also the Wharf salt + gate grinder)
  - **Response**: `west` out of the pub walks straight to the Kitchen (no
    `Thwack! A dagger streaks past your ear…`); `north` at the gate walks
    straight into the Lobby (no `A tiny nymph appears… Go away… Bye!`).
  - **Root cause (confirmed)**: `verbs/exit/move.py` fires the destination's
    `enterfunc` (M-ENTER) but **never invokes the source room's exit handler**
    and has no concept of an RFATAL abort. Compounding it, Beyond Zork's room
    routines use the `M-EXIT` constant, which is **absent from `M_TO_VERB`**
    in `translator/constants.py` (the table maps `M-LEAVE`→`exitfunc`, not
    `M-EXIT`) — so no `exitfunc` role/alias is even registered for these
    clauses. Two-part game-neutral fix: (1) map `M-EXIT`→`exitfunc` (or alias
    to M-LEAVE) so the clause becomes a callable role; (2) in `move.py`, before
    relocating, invoke the source room's `exitfunc` with `P-WALK-DIR` set and
    abort the move when it signals RFATAL. Cross-check zork1/EZIP (which use
    M-EXIT for similar gags) when adding the mapping.
  - **Workaround**: none — currently makes the map *more* traversable (no
    scripted blocks), which is why the smoke spine passes; the famous
    starting-dagger pickup is unreachable.

## Inaugural shakedown — 2026-06-07 (raw-mode session, Hilltop opening) — ALL FIXED

All five inaugural bugs are now resolved (2026-06-07 Mode-2 pass — see
[references/completed-work.md](references/completed-work.md)):

- ✅ **`wait` crash** (`has no attribute 'clocker'`) → added the beyondzork
  `clocker` shim.
- ✅ **TELL of a bare Object** (`can only concatenate str (not "Object")`, e.g.
  Edge of Storms "extend to the None", Weapon Shop SHOP-DOOR) → `_tell_segments`
  appends `.desc()` to bare object atoms.
- ✅ **`inventory` rejected** → `VERB-SYNONYM` parsing + migration-gate synonym
  matching → `syntax_rows/i.py`.
- ✅ **`examine me` → oak tree** (and `examine door` → onion) → `do_command`
  maintains the P-IT-OBJECT == PRSO invariant.
- ✅ **`score` fragmented** → resolved by the zout scroll-coalescing fix (all
  multi-fragment output now renders as continuous wrapped lines).

<!-- template:
- [ ] **<one-line summary>** (room: `<Room Name>`, command: `<command>`)
  - **Response**: `<verbatim, trimmed to 5 lines max>`
  - **Hypothesis**: <translator? generator? bootstrap state? sandbox? parser?>
  - **Workaround**: <what you did to keep moving>
-->
