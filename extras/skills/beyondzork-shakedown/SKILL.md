---
name: beyondzork-shakedown
description: End-to-end ZIL→DjangoMOO debugging skill for Beyond Zork (The Coconut of Quendor). Drive beyondzork.local to find translator/server bugs, OR pick a known failure and fix it inside moo/zil_import/ (translator/generator/SDK/config). Beyond Zork is the first XZIP/v5 port — a windowed (split-screen) title with a font-3 auto-map. Use when the user asks to shake down Beyond Zork, debug a beyondzork failure, or close a translation gap for it. Read ../_shared/references/rule-zero.md before any edit under moo/.
compatibility: Designed for Claude Code. Requires the django-moo repository, a running docker-compose stack, the moo-agent extension installed (provides moo.bootstrap.beyondzork), Beyond Zork ZIL source at /Users/philchristensen/Workspace/beyondzork/, and the beyondzork.local Site (PK 7) initialised.
---

# Beyond Zork Shakedown

The full Beyond Zork debugging loop: **find** bugs by playing the canonical
world, then **fix** them inside `moo/zil_import/` and verify. One skill, two
modes. Beyond Zork is the **first XZIP (Z-machine v5) port** and the first
**windowed** title — the importer/engine assumptions built for the EZIP family
(Zork 1/2/3, HHG) often need an XZIP-gated extension here.

## What makes Beyond Zork different

- **XZIP/v5 dialect.** Gated in `game_config.py` via `BEYONDZORK_CONFIG`
  (`exit_tables=True`, `rooms_as_objects`, `placement_property="LOC"`,
  `in_is_direction`). The byte-addressed pointer model (`zaddr_*` substrate +
  `context.scratch`) and the windowed-output routing are XZIP-only.
- **Windowed (split-screen) display.** A fixed top region holds the centered
  status line + a **font-3 auto-map**; room text scrolls below. The renderer
  drives it via the `window_*` SDK and the `printt`/`zout`/`DIROUT` substrate.
- **Two client displays, chosen at connect by `confunc` on client capability:**
  - **rich** client (prompt_toolkit TUI) → `DMODE=T`: windowed. Status line +
    auto-map in the top pane, description in the DBOX (bordered box).
  - **raw** client (MooSSH, line-oriented MUD clients, plain terminals) →
    `DMODE=0`: Beyond Zork's *normal* display. Description prints inline to the
    scroll via `DESCRIBE-HERE`; **no auto-map, no DBOX** (V-LOOK never calls
    `DISPLAY-PLACE`). This is the degradation Beyond Zork shipped for terminals
    without a split screen.

## 🛑 The windowed display & how to drive it

**MooSSH is a raw client** (it has no prompt_toolkit/GMCP window). The shell
no-ops every `window_*` event for raw clients, so in raw mode you see the
**scroll only** — which, thanks to `DMODE=0`, now includes the room
descriptions (no map). **This is the right driver for narrative/parser/verb
shakedown** (Mode 1 below).

To inspect the **windowed** display itself (map glyphs, DBOX layout, status
line) you need the rich-mode rendering, which MooSSH can't show. Use the
headless window-capture probe: monkeypatch `moo.core._publish_to_player` to
record `window_write` events, then drive `parse.interpret(ctx, "look")` inside
a `code.ContextManager(adv, out.append, …)` and render the captured (row, col,
text) cells into a grid. (The headless path does NOT run `confunc`, so `DMODE`
stays at its seeded `T` → you get the windowed output.) See
`references/known-quirks.md` for the exact probe snippet.

## Where files live

- **moo-agent** is the working directory: the dataset (`moo/bootstrap/beyondzork/`,
  gitignored generated output), the ZIL importer (`moo/zil_import/`), and this
  skill all live here.
- **Beyond Zork ZIL source** is at `/Users/philchristensen/Workspace/beyondzork/`.
  Manifest is `beyond.zil` (`<VERSION XZIP>`); key files: `macros.zil`,
  `constants.zil`, `misc.zil` (renderer + windowed display), `places.zil`,
  `things.zil`, `events.zil`, `verbs.zil`.
- **django-moo** is the engine repo (`moo/core/`, `moo/sdk/`, `moo/shell/`,
  `moo/bootstrap/__init__.py`, `moo/bootstrap/default/`) — off-limits for
  fitting game-specific bugs (Rule Zero). The windowed-display *infrastructure*
  in `moo/shell/window.py` + `moo/shell/prompt.py` and the `window_*` SDK in
  `moo/sdk/output.py` is game-neutral display plumbing; extend it only with
  explicit approval, never with Beyond-Zork-specific logic.

Both repos contribute to the `moo.*` namespace package, so
`moo.bootstrap.beyondzork` resolves regardless of working directory.

## 🛑 RULE ZERO — READ BEFORE EVERY EDIT IN `moo/`

**DO NOT MODIFY `moo/` (OUTSIDE `moo/bootstrap/beyondzork/`) TO MAKE THE BEYOND
ZORK BOOTSTRAP WORK.** Another violation ends the collaboration. Every
translation gap is solved inside `moo/zil_import/` (game-neutral
translator/generator/IR/parser), in `game_config.py` (`BEYONDZORK_CONFIG`
knobs), in `moo/zil_import/verbs/beyondzork/` (per-game overrides), the
substrate verbs (`verbs/system/`, `verbs/thing/`, `verbs/root/`), or the reset
body (`scripts/_beyondzork_reset_state_body.py`). The full anti-pattern catalog
is [../_shared/references/rule-zero.md](../_shared/references/rule-zero.md) —
read it first. If you're about to edit `moo/core/`, `moo/sdk/`, `moo/shell/`,
`moo/bootstrap/__init__.py`, or `moo/bootstrap/default/`, **stop and ask**.

## ✍️ This skill is self-updating

End every session by updating this skill's files with what you learned:

- New failure mode found via shakedown → [BUGS.md](BUGS.md).
- Bug needing a moo-core change → [TODO.md](TODO.md) with the rationale.
- Translator/generator/SDK/config fix that landed → [references/completed-work.md](references/completed-work.md).
- Pre-existing limitation surfaced → [references/known-quirks.md](references/known-quirks.md).
- A new game-side mechanic mapped → [FEATURES.md](FEATURES.md) / [references/coverage.md](references/coverage.md).

## Mode 1 — Shakedown (find bugs)

You are a Beyond Zork player who happens to be a MOO engine debugger. Drive
**one** raw SSH session open from start to finish.

```bash
# Always include --reset for a fresh session.
extras/skills/beyondzork-shakedown/scripts/beyondzork_session.py start --reset
extras/skills/beyondzork-shakedown/scripts/beyondzork_session.py send "look"
extras/skills/beyondzork-shakedown/scripts/beyondzork_session.py since "look"
extras/skills/beyondzork-shakedown/scripts/beyondzork_session.py stop
```

**Run `start` with `Bash run_in_background: true`** (it's a long-running daemon
that won't return until `stop`). After `start`, poll `status` until it reports
`running` before the first `send`. If `read` shows `[harness] error:`, the SSH
connection dropped — `status`, restart with `start --reset`, and note a real
crash in `BUGS.md`. An `An error occurred while executing the command.` line in
the scroll means a celery traceback — capture it with
`docker logs django-moo-celery-1 --tail 60 | grep -A30 ERROR`.

### Canonical Beyond Zork opener

Beyond Zork opens on the **Hilltop** (set by GO via `<SETG HERE ,HILLTOP>`),
carrying nothing, overlooking a seaside village. Exits: **east** → Cove,
**northwest** → Edge of Storms, **up/down** → the oak tree (a blocked-climb
gag). Map the actual opening rooms/exits from `places.zil` and tick them into
`references/coverage.md` as you verify them live.

### Bug-logging workflow

Log to `BUGS.md` (newest at top) on: a `Traceback`/`NameError`/`TypeError`/
`AttributeError` (the `An error occurred` line); a canonical command rejected
as `I don't know how to do that` (grep `known-quirks.md` first); a description
emitting `None` or a raw object repr; a room missing an exit its description
claims; a verb returning wrong text; an unprompted connection drop. Don't fix
during shakedown — note and continue; don't restart per bug.

## Mode 2 — Fix (translator/generator/SDK/config)

### Before you start

1. Read [../_shared/references/rule-zero.md](../_shared/references/rule-zero.md).
2. Read [references/completed-work.md](references/completed-work.md) — don't re-do landed fixes.
3. Read [BUGS.md](BUGS.md) — open bugs with game-side fix paths.
4. Read [../_shared/references/smoke-workflow.md](../_shared/references/smoke-workflow.md) — the regen/sync loop (`<slug>` = `beyondzork`).
5. Skim `moo/zil_import/AGENTS.md` for the importer's design rules.

### The work loop

1. **Pick one failure category.** Cascading failures often share a root cause.
2. **Locate the cause.** Most XZIP gaps live in `moo/zil_import/translator/`
   (verb-body emission, TELL tokens, char literals), `moo/zil_import/parser.py`
   (tokenizer), `moo/zil_import/converter.py` (IR — e.g. the `"OPT"` param
   keyword), `game_config.py` (`BEYONDZORK_CONFIG`), the substrate verbs
   (`verbs/system/{apply,tables,ztables,zwindow}.py`, `verbs/thing/helpers/*`),
   or the reset body (constant/table seeding).
3. **Edit only inside the allowed surface.** Can't fix without core? Stop and ask.
4. **Regen + clear snapshot + sync** (the snapshot clobbers regen):

   ```
   uv run python -m moo.zil_import ~/Workspace/beyondzork/beyond.zil \
       --game-config beyondzork --output moo/bootstrap/beyondzork
   docker exec django-moo-shell-1 sh -c 'rm -f /usr/app/snapshots/beyondzork-site-7.json'
   docker exec django-moo-shell-1 sh -c '/usr/app/bin/python /usr/app/src/manage.py \
       moo_init --bootstrap beyondzork --sync --hostname beyondzork.local'
   ```

   `--sync` flushes the Redis `moo:verb:*` cache (needed after a substrate-verb
   edit). Core changes (`moo/shell`, `moo/sdk`, `moo/core`) need
   `docker compose restart shell webssh webapp celery`.
5. **Verify** — re-drive the failing command in a raw session (Mode 1). For
   windowed-display fixes, use the headless window-capture probe.
6. **Run the importer unit suite** (`uv run python -m pytest moo/zil_import/tests/`)
   and **cross-check the zork1 smoke** after any shared
   translator/parser/converter change — those live in code shared with EZIP.
   (zork1's bootstrap isn't regenerated automatically, so a shared-code change
   only reaches it on an explicit zork1 regen.)

## When something needs a core change

Stop work on it, move the bug from `BUGS.md` to `TODO.md` with the gap, why no
game-side workaround exists, and the minimal core API that would close it.
Present it; wait for explicit approval.

## Files in this skill

| File | Purpose |
|---|---|
| `BUGS.md` | Open bugs found via shakedown. Newest first. |
| `TODO.md` | Bugs deferred because they need a moo-core change. |
| `FEATURES.md` | Beyond-Zork-specific mechanics to exercise (RPG layer, auto-map, scroll-casting). |
| `references/coverage.md` | Room/verb/probe checklist. Tick when verified. |
| `references/known-quirks.md` | Pre-existing limitations + the windowed-display probe. |
| `references/completed-work.md` | Fixes that landed. |
| `BEYONDZORK-FEASIBILITY.md` | The original XZIP-gap assessment (historical). |
| `scripts/beyondzork_session.py` | Thin wrapper around the shared MooSSH harness (raw mode). |
| `../_shared/references/rule-zero.md` | The no-moo-core-edits constraint. Read first. |
| `../_shared/references/smoke-workflow.md` | Regen + sync loop. |

## Memory entries that govern this work

- `beyondzork-automap-polish-2026-06-07` — the windowed-display + auto-map +
  description-display fixes (the substrate this skill builds on).
- `feedback_zil_translator_no_core_changes` — Rule Zero.
- `feedback_zil_importer_game_agnostic` — keep `moo/zil_import/` game-neutral.
- `feedback_smoke_tee` — always `tee /tmp/smoke.out` on smoke runs.
- `reference_site_pk_layout` — beyondzork.local is Site PK 7.
