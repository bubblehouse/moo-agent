# Rule Zero: No moo-core changes for ZIL

**DO NOT MODIFY `moo/` (OUTSIDE `moo/bootstrap/zork1/`) TO MAKE THE ZORK BOOTSTRAP WORK.**

## Why this is Rule Zero

The user has stated outright that another violation of this rule will end the collaboration. This is not a style guideline — it is a hard limit. Past violations have all been reverted, and several were caught only after significant time was invested in building on them.

## What "moo-core" means

Anything under `moo/` that is NOT `moo/bootstrap/zork1/` is core engine territory. That includes:

- `moo/core/` — parser, models, code sandbox, managers, exceptions, JSON serialization.
- `moo/sdk/` — verb-author public API.
- `moo/shell/` — SSH server, prompt, terminal view.
- `moo/bootstrap/__init__.py` — the shared loader (`parse_shebang`, `load_verbs`, `get_or_create_object`, `initialize_dataset`).
- `moo/bootstrap/default/` — the canonical example dataset.
- `moo/conftest.py` and `moo/**/tests/` — generic test infrastructure.
- `moo/settings/` — Django settings.

Anything in `moo/zil_import/` is fair game. So is `moo/bootstrap/zork1/` (though it's generated output, so edits should land in `moo/zil_import/` and be regenerated).

## Forbidden patterns — checklist

Before any edit under `moo/`, verify NONE of these are true:

- [ ] Adds or references ZIL primitives (`PRSO`, `PRSI`, `P-PRSO`, `P-PRSI`, `P-LEXV`, `M-BEG`, `M-LOOK`, `M-END`, `M-ENTER`, `M-LEAVE`, `M-FLASH`, `M-OBJDESC`, `getpt`, `ptsize`, `UEXIT`, `NEXIT`, `FEXIT`, `CEXIT`, `DEXIT`, `RTRUE`, `RFALSE`, `jigs_up`).
- [ ] Hard-codes Zork class names (`Zork Root`, `Zork Thing`, `Zork Container`, `Zork Room`, `Zork Actor`, `Zork Exit`, `ZIL SDK`).
- [ ] Adds a sandbox env var that mirrors a ZIL concept (`player_verb`, `the_player_verb`, `prso`, `prsi`).
- [ ] Filters/walks ZIL-shaped properties (`zstate_*`, `global_scenery`, `<LTABLE>`).
- [ ] Adds a management command, helper, or feature whose only purpose is the Zork dataset.
- [ ] Edits `moo/bootstrap/__init__.py` for translator convenience.
- [ ] Edits a `moo/bootstrap/default/` verb to align with translated Zork output.

If any box is checked: **STOP.** The fix belongs in `moo/zil_import/`.

## Anti-patterns already attempted (and reverted)

These all "looked reasonable in the moment" and all cost trust:

| What I did | Where | Why it was wrong |
| --- | --- | --- |
| Added `turnfunc` auto-fire to `parse.py` | `moo/core/parse.py` | Mechanism was generic enough to keep, but the rationale ("Zork's LIVING-ROOM-FCN needs it") was ZIL-driven. Comments stripped of ZIL refs; mechanism kept. |
| Added `player_verb` env var | `moo/core/code.py` | Mirror of ZIL's PRSA. REMOVED. Translated routines must use `verb_name` like every other verb. |
| Added `global_scenery` traversal | `moo/core/models/object.py` `find()` | LOCAL-GLOBALS lookup baked into generic dobj resolver. REMOVED. Game-side replacement landed via the `do_command` hook (see [completed-work.md § "do_command resolves scenery + open-container dobjs"](completed-work.md)). |
| Added open-container peek | `moo/core/models/object.py` `find()` | Generally-useful feature but added under ZIL pretext. REMOVED. Will likely come back as an approved generic feature later — not unilaterally. |
| Created `moo_reset` / `moo_save_state` commands | `moo/core/management/commands/` | Hard-coded `Zork Root` / `ZIL SDK` and `zstate_*` semantics. DELETED. Move to `moo/zil_import/scripts/`. |
| Added zork1-specific banner | `moo/core/management/commands/moo_init.py` | `if bootstrap == "zork1":` — REMOVED. Banner should print from inside `moo/bootstrap/zork1/bootstrap.py`. |
| Changed `get_or_create_object` to re-add parents | `moo/bootstrap/__init__.py` | Genuinely useful for any bootstrap — but added unilaterally for Zork sync. REVERTED. Re-propose with explicit user approval. |
| Added bare-name `--on` lookup | `moo/bootstrap/__init__.py` `load_verb_source` | Generic loader change motivated by "stop polluting `$/_` with Zork atom aliases." REVERTED. Re-propose. |
| Changed `--dspec any` → `--dspec either` on `default/go.py` | `moo/bootstrap/default/verbs/room/go.py` | Edited a default-bootstrap verb to fix a Zork edge case. REVERTED. |

## The one approved core change

The user has approved exactly one moo-core change since starting this work:

- `moo/core/parse.py` `Parser.get_pronoun_object` — extends pronoun resolution so the caller's location's name/aliases resolves as a pronoun (so e.g. `disembark boat` finds the boat the player is inside). Generic, not ZIL-specific. Currently staged in the working tree.

That's the only edit allowed. Anything else is a new conversation.

## Boundary cases encountered (2026-05-06)

These were temptations that I held the line on — kept here so the next session knows they're traps and what the right answer was.

| Temptation | What I did instead |
| --- | --- |
| Add `find_object` fallback walking `global_scenery` to `Parser` (just one line!) | Did the scenery walk inside `do_command` and mutated `parser.dobj` in place. The parser already exposes `dobj` and reads it from `get_search_order()` after `__init__` returns, so this is well-defined. |
| Inject `player_verb` env var for sub-call cases (the original anti-pattern, but "I have a new use case!") | Made the translator emit `the_player_verb` from `context.parser.words[0]` at routine top.  No env-var changes; the parser's existing surface is enough. |
| Edit `Parser.find_object` to be smarter about open containers | Did the open-container peek inside `do_command`. |
| Edit `moo/bootstrap/__init__.py` to fix `get_or_create_object` parent-add behaviour | Emitted an `_ensure_parent` helper at the top of `030_objects.py` and `020_rooms.py` and called it per-object.  Heals the same case without modifying the shared loader. |
| Edit `moo/core/management/commands/moo_init.py` to print a Zork banner | Emitted the banner from inside the generated `bootstrap.py` via `log.info`. |

The pattern: every "this would be one line in core" temptation has a one-line equivalent inside `do_command` or the bootstrap-emitted scripts.  When you can't see it, the answer is to ask the user, not to edit core.

## When you're tempted

The temptation looks like: "I just need to add this one tiny thing to core and `<command>` will work."

Stop. Read this checklist:

1. Could this be done in `moo/zil_import/translator.py` by emitting different verb code?
2. Could this be done in `moo/zil_import/verbs/zil_sdk/` as a runtime shim?
3. Could this be done by the System Object's `do_command` verb (which is allowed to be game-specific because it's a LambdaMOO hook)?
4. Could this be done by adding a verb on a generated zork1 class (Zork Thing, Zork Room, etc.) — which lives in `moo/bootstrap/zork1/` and is therefore allowed?
5. Could this be done by changing what the bootstrap **stores** (e.g., move objects between locations at bootstrap time) rather than what core **does** at runtime?

If the answer to all five is no, **stop and write a one-paragraph case for the user**. Don't pre-emptively edit core.
