# AGENTS.md: ZIL Importer Guide

> # 🛑 STOP — THE BOUNDARY IS HARD
>
> ## **NEVER MODIFY `moo/` (OUTSIDE `moo/bootstrap/zork1/`) TO MAKE THE ZIL IMPORTER WORK.**
>
> The ZIL importer is an *external adapter*. Everything ZIL-aware must live inside this directory, including the runtime shim layer under `extras/zil_import/verbs/` that gets copied verbatim into generated output.
>
> If you find yourself wanting to:
>
> - Add a special case to `moo/core/parse.py`, `moo/core/models/object.py`, `moo/core/code.py`, or any other engine file —
> - Hard-code Zork class names, ZIL primitives, or `zstate_*` properties into core code —
> - Edit `moo/bootstrap/__init__.py` (the shared loader) for translation convenience —
> - Touch `moo/bootstrap/default/` verbs to align with translated output —
>
> **STOP and ASK THE USER FIRST.** The default answer is no. This rule has been violated repeatedly and has cost real time and trust. The user will not give you another chance.
>
> The right place to fix translation gaps is here, in `extras/zil_import/translator/`, `extras/zil_import/generator/`, or a shim verb under `verbs/zork_root/`, `verbs/zork_thing/helpers/`, or `verbs/system/`. Shrink the shim layer over time; do not grow `moo/`.

## What this directory does

`extras/zil_import/` translates Infocom-style ZIL (Z-machine Implementation Language) source into a DjangoMOO bootstrap package. Output lands in `moo/bootstrap/zork1/` and is checked in (not regenerated in normal CI).

## Layout

- `parser.py` — ZIL lexer/parser; produces raw token trees consumed by `converter.py`.
- `converter.py` — entry point that reads ZIL files and produces IR.
- `ir.py` — intermediate-representation dataclasses + flag/property mappings.
- `game_config.py` — per-game knobs (banner, dataset name, NPC atom map). The default `ZORK1_CONFIG` configures the Zork 1 importer; another game would land its own `GameConfig` here without touching translator/generator.
- `translator/` — IR → Python verb-source translation. Per-routine, per-clause, per-M-clause splits live here, split across `__init__.py` (main driver), `stmt_handlers.py`, `expr_handlers.py`, `daemon_modes.py`, `identifiers.py`, and `constants.py`. Game-neutral by construction; reads NPC atom mappings from the active `GameConfig`.
- `generator/` — drives translator output into a complete `moo/bootstrap/<dataset>/` tree (rooms, objects, exits, tables, verbs). `__init__.py` is the driver; `config.py` holds shared paths/constants. Banner / dataset-name strings come from `GameConfig`.
- `verbs/` — static templates copied verbatim into generated `verbs/`:
  - `verbs/zork_root/`, `verbs/zork_thing/helpers/`, `verbs/system/` — runtime shim layer (flag/zstate/table primitives, queue/scheduler, parser helpers) that the translator emits calls to. Game-neutral.
  - `verbs/system/`, `verbs/zork_*/`, `verbs/PREFIX.py`, `verbs/SUFFIX.py` — System Object verbs and delimiter helpers. Game-neutral.
  - `verbs/zork1/` — game-specific overrides (e.g. `pot_of_gold_pre_take.py`). New game-specific verbs land in their own `verbs/<dataset_name>/` subdir; templates outside these subdirs must stay neutral.
- `scripts/zork1_smoke.py` — end-to-end smoke driving the live `zork1.local` universe over SSH.
- `scripts/zork1_spot.py` — quick spot-test that runs a short command sequence (skips the slow reset by default).
- `tests/` — translator unit tests + Z-machine-leakage regression test.

## Game-agnosticism

`extras/zil_import/` must work for *any* ZIL game — not just Zork 1. Don't store Zork-specific verb tables, object names, or workarounds here. Game-specific logic belongs in the generated `moo/bootstrap/zork1/` output (which is checked in but conceptually disposable).

## Memory entries that govern this work

- `feedback_zil_translator_no_core_changes` — the rule above, in memory form.
- `feedback_zil_importer_game_agnostic` — keep `extras/zil_import/` game-neutral.
- `feedback_zork1_all_generated` — `moo/bootstrap/zork1/` is 100% translator output; fix bugs in `extras/zil_import/` then regenerate.
- `feedback_zil_no_system_aliases_for_on` — don't pollute `$/_` with per-object aliases just to support `--on`.
- `feedback_zil_verbs_organized_by_owner` — verb-tree layout convention.
