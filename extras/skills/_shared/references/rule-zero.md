# Rule Zero: No moo-core changes for ZIL

**DO NOT MODIFY `moo/` (OUTSIDE the game's own `moo/bootstrap/<dataset>/`) TO MAKE A ZIL BOOTSTRAP WORK.**

This is the shared, game-neutral statement of Rule Zero. It governs every
`*-shakedown` skill. `<dataset>` below means whichever game you're working
on (`zork1`, `zork2`, `hhg`, …).

## Why this is Rule Zero

The user has stated outright that another violation of this rule will end the collaboration. This is not a style guideline — it is a hard limit. Past violations have all been reverted, and several were caught only after significant time was invested in building on them.

## What "moo-core" means

Anything under `moo/` that is NOT `moo/bootstrap/<dataset>/` is core engine territory. That includes:

- `moo/core/` — parser, models, code sandbox, managers, exceptions, JSON serialization.
- `moo/sdk/` — verb-author public API.
- `moo/shell/` — SSH server, prompt, terminal view.
- `moo/bootstrap/__init__.py` — the shared loader (`parse_shebang`, `load_verbs`, `get_or_create_object`, `initialize_dataset`).
- `moo/bootstrap/default/` — the canonical example dataset.
- `moo/conftest.py` and `moo/**/tests/` — generic test infrastructure.
- `moo/settings/` — Django settings.

Anything in `moo/zil_import/` is fair game (it's the importer, shared by all
games — but keep it game-neutral; per-game knobs go in `game_config.py` and
per-game verb overrides in `moo/zil_import/verbs/<dataset>/`). So is the
generated `moo/bootstrap/<dataset>/` tree — though it's generated output, so
edits should land in `moo/zil_import/` and be regenerated.

## Forbidden patterns — checklist

Before any edit under `moo/`, verify NONE of these are true:

- [ ] Adds or references ZIL primitives (`PRSO`, `PRSI`, `P-PRSO`, `P-PRSI`, `P-LEXV`, `M-BEG`, `M-LOOK`, `M-END`, `M-ENTER`, `M-LEAVE`, `M-FLASH`, `M-OBJDESC`, `getpt`, `ptsize`, `UEXIT`, `NEXIT`, `FEXIT`, `CEXIT`, `DEXIT`, `RTRUE`, `RFALSE`, `jigs_up`).
- [ ] Hard-codes generated ZIL class names (`Zork Root`, `Zork Thing`, `Zork Container`, `Zork Room`, `Zork Actor`, `Zork Exit`, `ZIL SDK`) into core.
- [ ] Adds a sandbox env var that mirrors a ZIL concept (`player_verb`, `the_player_verb`, `prso`, `prsi`).
- [ ] Filters/walks ZIL-shaped properties (`zstate_*`, `global_scenery`, `<LTABLE>`) in core.
- [ ] Adds a management command, helper, or feature whose only purpose is one ZIL dataset.
- [ ] Edits `moo/bootstrap/__init__.py` for translator convenience.
- [ ] Edits a `moo/bootstrap/default/` verb to align with translated output.
- [ ] Adds a game-specific table/branch to `moo/zil_import/` itself (the importer must stay game-agnostic — use `game_config.py` / `verbs/<dataset>/`).

If any box is checked: **STOP.** The fix belongs in `moo/zil_import/` (game-neutral), `game_config.py`, `verbs/<dataset>/`, or the System Object's `do_command`.

## Anti-patterns already attempted (and reverted)

These all "looked reasonable in the moment" and all cost trust:

| What was done | Where | Why it was wrong |
| --- | --- | --- |
| Added `turnfunc` auto-fire to `parse.py` | `moo/core/parse.py` | Mechanism was generic enough to keep, but the rationale was ZIL-driven. Comments stripped of ZIL refs; mechanism kept. |
| Added `player_verb` env var | `moo/core/code.py` | Mirror of ZIL's PRSA. REMOVED. Translated routines use `verb_name` like every other verb. |
| Added `global_scenery` traversal | `moo/core/models/object.py` `find()` | LOCAL-GLOBALS lookup baked into the generic dobj resolver. REMOVED. Game-side replacement landed via the `do_command` hook. |
| Added open-container peek | `moo/core/models/object.py` `find()` | Generally-useful but added under ZIL pretext. REMOVED. Came back game-side via `do_command`'s `peek_into`. |
| Created `moo_reset` / `moo_save_state` commands | `moo/core/management/commands/` | Hard-coded `Zork Root` / `ZIL SDK` and `zstate_*`. DELETED. Live in `moo/zil_import/scripts/`. |
| Added dataset-specific banner | `moo_init.py` | `if bootstrap == "zork1":` — REMOVED. Banner prints from inside the generated `bootstrap.py`. |
| Changed `get_or_create_object` to re-add parents | `moo/bootstrap/__init__.py` | Useful for any bootstrap, but added unilaterally. REVERTED → emitted an `_ensure_parent` helper in the generated scripts instead. |
| Added bare-name `--on` lookup | `moo/bootstrap/__init__.py` | Generic loader change motivated by ZIL atom aliases. REVERTED. |
| Changed `--dspec any` → `--dspec either` on `default/go.py` | `moo/bootstrap/default/verbs/room/go.py` | Edited a default-bootstrap verb to fix a ZIL edge case. REVERTED. |

## The one approved core change

The user has approved exactly one moo-core change since this work began:

- `moo/core/parse.py` `Parser.get_pronoun_object` — extends pronoun resolution so the caller's location's name/aliases resolve as a pronoun (e.g. `disembark boat` finds the boat the player is inside). Generic, not ZIL-specific.

That's the only edit allowed. Anything else is a new conversation.

## When you're tempted

The temptation looks like: "I just need to add this one tiny thing to core and `<command>` will work." Stop. Run this checklist:

1. Could this be done in `moo/zil_import/translator/` by emitting different verb code?
2. Could this be done as a runtime shim under `moo/zil_import/verbs/<dataset>/`?
3. Could this be done by the System Object's `do_command` verb (allowed to be game-specific — it's a LambdaMOO hook)?
4. Could this be done by adding a verb on a generated class (Zork Thing, Zork Room, …) which lives in `moo/bootstrap/<dataset>/`?
5. Could this be done by changing what the bootstrap **stores** (move objects at bootstrap time) rather than what core **does** at runtime?

Every "this would be one line in core" temptation has a one-line equivalent inside `do_command` or the bootstrap-emitted scripts. When you can't see it, the answer is to ask the user, not to edit core.

Per-game boundary cases (temptations held off and how) belong in each
skill's own `references/known-quirks.md`, not here.
