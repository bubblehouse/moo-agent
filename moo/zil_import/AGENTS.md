# AGENTS.md: ZIL Importer Guide

> # 🛑 STOP — THE BOUNDARY IS HARD
>
> ## **NEVER MODIFY `moo/` (OUTSIDE `moo/bootstrap/zork1/`) TO MAKE THE ZIL IMPORTER WORK.**
>
> The ZIL importer is an *external adapter*. Everything ZIL-aware must live inside this directory, including the runtime shim layer under `moo/zil_import/verbs/` that gets copied verbatim into generated output.
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
> The right place to fix translation gaps is here, in `moo/zil_import/translator/`, `moo/zil_import/generator/`, or a shim verb under `verbs/root/`, `verbs/thing/helpers/`, or `verbs/system/`. Shrink the shim layer over time; do not grow `moo/`.

## What this directory does

`moo/zil_import/` translates Infocom-style ZIL (Z-machine Implementation Language) source into a DjangoMOO bootstrap package. Output lands in `moo/bootstrap/zork1/` and is checked in (not regenerated in normal CI).

## Path note

The importer used to live at `extras/zil_import/`. It was relocated to `moo/zil_import/` so the `moo` namespace package (PEP 420) picks it up the same way Django's bootstrap loader picks up `moo.bootstrap.zork1`. Tests, generator output, and docker mounts now reference the `moo.zil_import` path uniformly.

## Layout

- `parser.py` — ZIL lexer/parser; produces raw token trees consumed by `converter.py`.
- `converter.py` — reads ZIL files and produces IR. `extract_syntax_rules()` (Phase 1 reification) returns a typed `dict[str, list[ZilSyntaxRule]]` alongside the legacy dict views.
- `ir.py` — intermediate-representation dataclasses + flag/property mappings. `ZilSyntaxRule` carries `(verb, arity, v_routine, particle, iobj_prep)` for the per-cell emitter.
- `migration.py` — `MIGRATED_VERBS: set[str]` gating the syntax-row dispatcher. Verbs in this set emit through `syntax_row.py.j2`; everything else uses the legacy per-verb-atom dispatcher. The module is removed in Phase 8 when the legacy path retires.
- `audit.py` — `RegenAudit` accumulator. The generator instantiates one per game, records every silently-dropped clause / rule / form during emission, and writes `coverage.json` next to the bootstrap output. `tests/test_translator_coverage.py` ratchets against `tests/_translator_coverage_baseline.json`.
- `verb_metadata.py` — small helpers for shebang-name alignment (used by `_emit_v_routine_helper` to seed alias lists from `the_player_verb == 'X'` literals).
- `game_config.py` — per-game knobs (banner, dataset name, NPC atom map). The default `ZORK1_CONFIG` configures Zork 1; HHG runs `HHG_CONFIG` from the same module.
- `translator/` — IR → Python verb-source translation. Split across `__init__.py` (main driver), `stmt_handlers.py`, `expr_handlers.py`, `daemon_modes.py`, `identifiers.py`, and `constants.py`. Game-neutral by construction; reads NPC atom mappings from the active `GameConfig`.
- `generator/` — drives translator output into a complete `moo/bootstrap/<dataset>/` tree (rooms, objects, exits, tables, verbs). `__init__.py` is the driver; `config.py` holds shared paths/constants. Banner / dataset-name strings come from `GameConfig`.
- `templates/syntax_row.py.j2` — Jinja template for per-cell syntax-row runners; emits the dobj/iobj OBJECT-FUNCTION → ROOM-FUNCTION M-BEG → substrate V-* → ROOM-FUNCTION M-END action chain.
- `verbs/` — static templates copied verbatim into generated `verbs/`:
  - `verbs/root/`, `verbs/thing/helpers/`, `verbs/system/` — runtime shim layer (flag/zstate/table primitives, queue/scheduler, parser helpers) that the translator emits calls to. Game-neutral.
  - `verbs/system/`, `verbs/{root,thing,container,room,actor,actor_npc,exit}/`, `verbs/PREFIX.py`, `verbs/SUFFIX.py` — System Object verbs and substrate-class shims. Game-neutral.
  - `verbs/room/dispatch_room_function.py` — Phase-3 stub for ROOM-FUNCTION dispatch from a syntax-row runner (always returns `False` today; Phase 7 grows it into a real router).
  - `verbs/thing/dispatch_object_function.py` — looks up `obj.action` and invokes the combined OBJECT-FUNCTION callback emitted by `translate_object_function_combined`. Live; routes Stage-3/Stage-4 (PRSI/PRSO) calls from `perform.py`.
  - `verbs/thing/helpers/d_apply.py` — M-Beg lifecycle router for ROOM-FUNCTION callbacks. Replaces ZIL's Python-2 `apply()` builtin.
  - `verbs/zork1/`, `verbs/hhg/` — game-specific overrides. New game-specific verbs land in their own `verbs/<dataset_name>/` subdir; templates outside these subdirs must stay neutral.
- The generator's regen also writes these directories *into the bootstrap output* (not as source templates):
  - `verbs/syntax_rows/<verb>[_<particle>][_<iobj_prep>].py` — one runner per `(verb, particle, iobj_prep, arity)` cell for verbs in `MIGRATED_VERBS`.
  - `verbs/thing/v_routines/v_<routine>.py` — one passive helper per V-* routine, registered with `--dspec none` so only the syntax-row runner calls it.
- `scripts/zork1_smoke.py` — end-to-end smoke driving the live `zork1.local` universe over SSH.
- `scripts/zork1_spot.py` — quick spot-test that runs a short command sequence (skips the slow reset by default).
- `tests/` — translator unit tests + Z-machine-leakage regression + coverage baseline ratchet + bootstrap-consistency baseline ratchet.

## Syntax-row dispatcher refactor

The translator-generator pipeline has two coexisting emission paths gated by `MIGRATED_VERBS`:

- **Legacy path** — one big `<verb>_dispatcher.py` per verb atom routes player input to the correct V-* substrate via arity / preposition.
- **Syntax-row path** — one file per `ZilSyntaxRule` cell. The runner is parser-inert except for its own `(verb, particle?, iobj_prep?)` shape, which means the parser disambiguates without an in-body switch.

Adding a verb to `MIGRATED_VERBS` flips emission for that verb:

1. Generator emits `verbs/syntax_rows/<verb>[_<particle>][_<iobj_prep>].py` runners (one per SYNTAX rule).
2. Generator mutes the substrate's `--dspec` from `this`/`either` to `none` via a post-emission shebang rewrite, so the runner is the only parser entry point.
3. The runner calls the substrate programmatically as `_.thing.v_<routine>()`, preserving hand-written per-object pre-action logic.

`verbs/thing/v_routines/v_<routine>.py` is always emitted, even for non-migrated verbs (the legacy dispatcher still goes through the substrate file, not the helper). When a verb migrates, only the substrate's parser dispatch flips off.

## Combined M-/F-clause emission

`ZilTranslator.translate_combined_clauses(skip_constants=None)` collapses per-clause files (`preturnfunc.py` + `turnfunc.py` + …) into a single `<routine_atom>.py` whose body is an `if rarg == "M-BEG": … elif rarg == "M-END": …` ladder.

- The shebang aliases every clause-role name handled (so `do_command`'s `loc.invoke_verb("preturnfunc", "M-BEG", …)` still resolves) plus the routine atom itself.
- `skip_constants` drops a clause's body *and* its role-name alias when a hand-written file at `verbs/.../{role}.py` overrides it. The only hand-written override today is `verbs/rooms/living_room/turnfunc.py` (LIVING-ROOM-FCN's M-END), and the generator detects it by file existence at emission time.
- A `_force_parser_safe_hoist` flag (try/finally-scoped to the combined emission only) makes prso/prsi hoists guard against `context.parser is None`, so daemon-invoked branches (M-ENTER from `schedule_realtime`) don't crash on `None.has_dobj_str()`.
- AND-wrapped clause tests (`<AND <EQUAL? .RARG ,M-X> <other-cond>>`) are recognised by `_match_m_clause_cond` and `_extract_clause_with_extras`; the residual cond is preserved as an inner `if <translated-rest>:` wrapper inside the branch body. Anchor caveat: at least one bare-EQUAL? clause must exist in the COND for `_find_dispatch` to locate the dispatcher form.

## Coverage audit

`RegenAudit` (in `audit.py`) tracks per-routine drops at decision points where a clause / rule / form is silently skipped:

- `m_clause_dropped` / `f_clause_dropped` — clause couldn't be extracted or translates to a no-op.
- `verb_clause_dropped` — VERB? splitter bailed out on overlap.
- `syntax_rule_dropped` — rule's V-routine is in `_SKIP_ROUTINES`.

The generator writes `coverage.json` into the bootstrap output dir at the end of every regen. `tests/test_translator_coverage.py` ratchets it against `_translator_coverage_baseline.json`:

- **New drop** (in live but not baseline) → test fails as a translator regression.
- **Healed drop** (in baseline but not live) → test fails so the baseline gets re-collected via `_collect_coverage_baseline.py`.
- **Missing `coverage.json`** → `test_coverage_json_present` fails fast, so a fresh checkout that hasn't regenerated doesn't silently pass the parametrized ratchet.

## `context.caller` is the verb OWNER (matters for privileged SDK calls)

On every verb invocation the engine sets `context.caller` to the **owner of the
verb being executed** (`Verb.__call__` → `override_caller(self.owner, …)`), and it
re-shifts on each nested call. It is **not** `this`, **not** `context.player`, and
**never** the System Object (`_` owns no verbs). See `django-moo/moo/AGENTS.md`
("`context.caller` is the verb's OWNER") for the full treatment.

Why this matters here: **all generated and substrate verbs are Wizard-owned**, so
inside them `context.caller.is_wizard()` is `True`. That is exactly why the
wizard-only SDK surface — `write()` and the entire windowed display
(`open_window`/`window_split`/`window_cursor`/`window_emit`/…) — works during
ordinary gameplay even though the acting avatar (e.g. the Adventurer) is a
non-wizard. When emitting calls to those SDK functions, you do **not** need to
gate on the player; the owner identity carries the privilege.

Pitfall when debugging: testing one of those SDK calls by invoking it directly in
a bare `ContextManager` (caller = the player) raises `UserError` — that is a
test-harness artifact, not a gameplay bug. Reproduce through a real verb call (or
`ContextManager.override_caller(<wizard>, …)`) to see true behaviour.

## Game-agnosticism

`moo/zil_import/` must work for *any* ZIL game — not just Zork 1. Don't store Zork-specific verb tables, object names, or workarounds here. Game-specific logic belongs in the generated `moo/bootstrap/zork1/` output (which is checked in but conceptually disposable).

## Memory entries that govern this work

- `feedback_zil_translator_no_core_changes` — the rule above, in memory form.
- `feedback_zil_importer_game_agnostic` — keep `moo/zil_import/` game-neutral.
- `feedback_zork1_all_generated` — `moo/bootstrap/zork1/` is 100% translator output; fix bugs in `moo/zil_import/` then regenerate.
- `feedback_zil_no_system_aliases_for_on` — don't pollute `$/_` with per-object aliases just to support `--on`.
- `feedback_zil_verbs_organized_by_owner` — verb-tree layout convention.
