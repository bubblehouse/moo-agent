# Why the ZIL Importer Exists

The `zork1` dataset shipped with django-moo is the original Infocom
*Zork I: The Great Underground Empire*, translated into a DjangoMOO
bootstrap. This page explains how that translation works and the
trade-offs the importer makes. For function reference and the public
API surface, see {doc}`../reference/zil-importer`.

## The problem

In November 2025, Microsoft and Activision released the source code
for *Zork I*, *II*, and *III* under the MIT License. The source is
written in ZIL — Zork Implementation Language — an MDL/Lisp dialect
that compiles to Z-Machine bytecode. That bytecode runs on Z-Machine
interpreters like Frotz; it does *not* run on a multi-user persistent
world server.

Two paths are available for hosting the released source on DjangoMOO:

1. **Embed a Z-Machine.** Implement the Z-Machine in a verb and
   expose it as a player-controllable game session. Faithful, but
   conceptually a virtual machine running inside an unrelated runtime
   — none of the rooms, objects, or verbs participate in the MOO's
   object graph, the persistence layer, or the parser.
2. **Translate ZIL to MOO.** Compile the ZIL source into native MOO
   objects and verbs. The world becomes a first-class part of the
   MOO; rooms are real `Object` rows, exits are real `Exit` objects,
   and translated routines are real verbs that the parser can find.

The importer takes the second path. The bootstrap package it produces
uses the same `010_classes.py` / `030_rooms.py` / verb-file layout that
django-moo's `tutorials/custom-world` guide walks through.

## Bridging two semantic models

ZIL and Python have different semantic models, and the translator
spends most of its complexity bridging them. Concretely:

- **State versus objects.** ZIL globals serve dual purpose: some name
  in-game objects (`,LAMP` is the lamp object), some name flags
  (`,CYCLOPS-FLAG` is a state bit). The importer can't tell which is
  which from the form alone, so the converter enumerates rooms and
  objects up-front and passes that inventory to the translator. Atoms
  in the inventory translate to `lookup("name")`; atoms in
  `GLOBAL_MAP` (e.g. `WINNER`, `HERE`, `SCORE`) translate to their
  canonical Python expression; everything else routes through
  `context.player.zstate_get('NAME')`.
- **Implicit return.** ZIL routines return the value of their last
  expression. Python expression-statements are just discarded. The
  translator wraps the trailing expression of every routine in
  `return` so the implicit return becomes explicit.
- **Routine dispatch versus verb dispatch.** ZIL routines are first-
  class procedures called by name; MOO verbs are dispatched on a
  target object. The translator emits routine calls as
  `_.zork_thing.invoke_verb("name", *args)` so the dispatch ends up
  on the parent class that hosts the translated verb file. Routines
  with an `ACTION` owner emit `--on "<owner>"` shebangs instead, so
  the parser finds them via dobj search when a player command targets
  the owner.
- **The Z-Machine has no parser.** ZIL games dispatch through a
  hand-rolled grammar table; DjangoMOO has its own parser. The
  importer translates routines (the action handlers), not the
  command vocabulary. Player commands like `take`, `drop`, `examine`
  live on `Zork Actor` and route into the substrate via
  `_.zork_thing.<verb>()`. The dispatchers themselves are emitted by
  `_gen_syntax_dispatchers` from the ZIL `SYNTAX` table, but the
  command verbs they target are the static templates under
  `moo/zil_import/verbs/`.

## Pipeline shape

The pipeline is four single-responsibility stages, each tested
independently:

```text
*.zil  ──► parser ──► converter ──► translator ──► generator ──► moo/bootstrap/<name>/
         (tokens   (IR dataclasses)  (per-routine    (per-bootstrap
          + AST)                      Python text)    file emission)
```

Splitting the work this way isolates the parts that have to change
when the upstream source moves:

- A new ZIL idiom — a form the translator doesn't yet recognise —
  changes only the translator. Parser and converter are unchanged.
- A new IR field (e.g., room scenery, NPC schedule) changes the
  converter and the IR dataclass. Parser unchanged.
- A new file in the generated bootstrap (e.g., a separate
  `015_globals.py` for ZIL `<GLOBAL>` initial values) changes only
  the generator. Translator unchanged.
- A new ZIL syntax (improbable — ZIL hasn't moved in 40+ years —
  but, e.g., extending to ZIL 6 dialects) changes only the parser.

The translator and generator are now packages, not single files —
adding a new ZIL form-head is one dispatch-table entry plus a small
handler under `translator/{stmt,expr}_handlers.py`. See the reference
doc's "Translator package layout" for the file split.

This split also makes the importer reusable for non-Zork inputs.
Any text-adventure source that compiles to objects, rooms, exits,
and per-object handlers can be retargeted by writing a different
parser and converter; the translator and generator (with minor
adjustments to the recognised SDK call set) carry over.

## Game-agnosticism

The translator and generator are game-agnostic by design. Every
Zork-specific string — banner text, dataset name, NPC atom map,
license blurb — flows through a `GameConfig` instance constructed
in `moo/zil_import/game_config.py`. `ZORK1_CONFIG` is the default;
a second game lands its own `GameConfig` and passes it to
`generate_all` and `ZilTranslator` without touching the engines.

Static templates that *are* game-specific (Zork's `pot of gold`
override, for instance) live under `moo/zil_import/verbs/zork1/`.
Anything outside that directory must stay neutral; the
`tests/test_no_zmachine_leakage.py` regression test enforces this by
scanning the importer for ZIL primitive names and Zork-specific
class strings.

## Why distinguish strings from atoms

A subtle parser detail worth calling out: ZIL has no type-level
distinction between `"hello"` (a string literal) and `HELLO` (an
atom). Both lex to the same Python `str`. The translator absolutely
needs to tell them apart — `<TELL "ALL CAPS">` emits a Python string
literal, but `<COND (,ALL-CAPS …)>` emits a state read.

The fix is a `Str` subclass of `str` that the parser tags string
literals with. `isinstance(node, str)` keeps working everywhere; only
the translator looks at `isinstance(node, Str)` to discriminate.
This is a small change that prevents a class of bug where all-caps
prose (which is common in interactive fiction) gets misinterpreted
as a globally-scoped lookup key.

## Why predicate atoms parse as one token

Another tokenizer detail: ZIL uses `?` as a predicate suffix — `LIT?`,
`STOLE-LIGHT?`, `0?`, `1?`. The bare-number forms (`0?`, `1?`) are
the ones that bite a naive tokenizer, because the regex for numbers
matches greedily before the regex for atoms gets a chance. The fix
is a negative lookahead on the number regex:

```python
r"(?P<number>-?\d+(?![A-Za-z0-9_.?!*#+\-]))"
```

so `0?` lexes as one atom (the head of `<0? .WD>`) rather than as
`0` followed by `?` followed by `.WD`. Without this, the form's head
is no longer a string and translation degenerates to a Python list
literal that pylint flags as a constant-test.

## Regeneration as a development workflow

For users of django-moo, the importer is invisible — `moo/bootstrap/zork1/`
is committed to the repo and loads the same way `default` does. The
importer only re-runs when the importer itself is being changed (a new
ZIL idiom, a translator bug fix, an upstream source bump). The
edit-compile cycle is:

1. Edit `moo/zil_import/{translator,generator}/` (packages),
   `parser.py`, `converter.py`, or any of the static verb templates
   under `verbs/`.
2. Run `uv run python -m moo.zil_import …` to regenerate.
3. Sync the database with `manage.py moo_init --bootstrap zork1 --sync`.
4. Run `uv run pytest -n auto moo/zil_import/tests/` to verify the
   importer's own unit tests.
5. Run the smoke (`uv run python -m moo.zil_import.scripts.zork1_smoke`)
   to verify the end-to-end translation still drives the game to its
   conclusion.

## Translator notes

This section collects the design decisions that the translator and
generator carry as inline comments. Each note's anchor is referenced
from the source so a future maintainer reading the code can find the
full reasoning here without it bloating the file.

### Pylint disables on generated verbs

The generator emits two pylint-disable shapes. `DISABLE_INTRINSIC`
covers `return-outside-function` and `undefined-variable`, both of
which are inherent to the DjangoMOO verb-file format (verbs use
module-level `return`; `context`, `passthrough`, `verb_name`, and
`args` are injected at execution time). `DISABLE_FULL` is the
tolerant set used when the operator regenerates without `--lint`,
absorbing translator-emitted patterns (`unnecessary-pass`,
`pointless-statement`, `no-else-return`, …) that an opt-in lint run
would surface as actionable issues. With `--lint` active, only
`DISABLE_INTRINSIC` is emitted.

### Direction-token (`P?`) atoms

ZIL stores direction codes in PRSO when the player types `go east`.
DjangoMOO carries the direction as the dobj string instead, so an
`<EQUAL? ,PRSO ,P?EAST>` form compiles to
`context.parser.get_dobj_str() == "east"`. The full mapping lives in
`DIRECTION_ATOMS` in `translator/constants.py`.

### `,ADVENTURER` resolves to the live player

`,ADVENTURER` was the canonical single-player avatar atom in ZIL —
every comparison or operation that targets ADVENTURER means "the
current player". Mapping the atom to `context.player` makes the
translated routines do the right thing for any avatar (Wizard for an
admin session, not just the bootstrap-created adventurer Object), and
prevents the contents-listing loop in `print_cont` from showing the
player's own avatar as a separate occupant of the room.

### PRSO / PRSI no-raise guard

`,PRSO` and `,PRSI` translate to a guarded call —
`(context.parser.get_dobj() if context.parser.has_dobj_str() else None)` —
so a verb body that references PRSO when the player typed bare
`disembark` (no dobj) gets `None` instead of an unhandled
`NoSuchObjectError`. `P-PRSO` / `P-PRSI` ZIL-side parser-state slots
are synonyms for the live values; DjangoMOO does not maintain a
separate "last parsed" cache.

### M-* lifecycle hooks

ZIL action M-* constants are lifecycle hooks fired by `APPLY`. The
canonical set is `M-LOOK`, `M-BEG`, `M-END`, `M-ENTER`, `M-LEAVE`,
`M-FLASH`, `M-OBJDESC`. M-FLASH ("you've been here before") and
M-OBJDESC ("describe object") rarely have widely-used clauses, but
APPLY may invoke them on objects that have no handler — the
`has_verb` guard at the call site makes those a no-op.

### F-* combat dispatch

Per-villain ACTION routines (TROLL-FCN, THIEF-FCN, CYCLOPS-FCN) test
`.MODE` against `F-DEAD`, `F-UNCONSCIOUS`, `F-CONSCIOUS`, `F-BUSY?`,
`F-FIRST?`. The translator splits these into per-mode files keyed by
`M_TO_VERB` so each branch's side effects fire on combat dispatch.

### Substrate dispatch via `_.zork_thing`

`zork_thing` is the only substrate handle that lives on the System
Object — translated routines invoke cross-class verbs via
`_.zork_thing.foo()` for predicates, dispatchers, and M-clause
splits. The remaining substrate classes (`Zork Actor`, `Zork Exit`,
`Zork Container`, `Zork Room`) are reachable via
`--on "<class display name>"` at verb-load time and need no
system-property alias.

### Zork Actor inherits Zork Thing

In canonical ZIL an actor IS a thing — V-EXAMINE / V-ATTACK / V-TAKE
all dispatch on actors via the same substrate routines as inert
objects, with per-object FCN handlers supplying the actor-specific
responses. Without `Zork Thing` in the parent chain, `passthrough()`
from a per-object actor handler walks `[Zork Actor]` only and never
finds the substrate, so a clause like the troll's `examine` handler
returning `passthrough()` emits a RuntimeWarning and the player
sees no body. The generator wires the parent in place so existing
actor objects bootstrapped before this fix pick up the substrate
verbs without a full reset.

### `accept` rebuild on each regen

The generator deletes any prior `accept` rows on `Zork Root` before
re-adding because `replace=True` only updates the first match.
Without the delete, every `--sync` left a leftover row from past
syncs accumulating until `add_verb` raised `AmbiguousVerbError` on
dispatch.

### REPEAT loop semantics

`<REPEAT … <RETURN>>` exits the loop, not the function. The
translator tracks `_repeat_depth` so the RETURN handler emits `break`
instead of `return None` when nested inside a REPEAT body.

### M-clause player-verb binding

Inside a translated M-clause the player verb is bound from
`args[1]` rather than `verb_name`, since the M-clause's
`verb_name` equals the routine name (e.g. `preturnfunc`) at the
point of dispatch. The residual god-verb instead reads
`context.parser.words[0]` so a sub-call from another verb still sees
the player's typed verb word.

### Aux-local default = 0

Z-machine semantics: aux locals reset to 0 on each routine call.
Translated bodies use these vars in arithmetic (`-count`, `count < 0`,
`count + 1`); pylint correctly flags `-None` as a real runtime
TypeError, so the translator emits `0` (not `None`) as the default
initialiser when no `<AUX (var <init>)>` value is given.

### `pre-X` substrate inlining

V-routines whose `PRE-X` handler exists get the pre-check inlined at
the top of the substrate body. PRE-X verbs are registered with the
snake-cased identifier (`pre_take` rather than `pre-take`) since
RestrictedPython forbids `-` in verb names — looking them up by their
actual registered name was previously a silent no-op.

### Parser-state SETG is a no-op

`<SETG ,PRSA ...>` (and the P-PRSA / P-PRSO / P-PRSI / P-LEXV slots)
are owned by DjangoMOO's parser. SETGing them in routines that set
up a follow-up PERFORM becomes a no-op, since `perform()` takes its
own arguments.

## See also

- {doc}`../reference/zil-importer` — the public API surface, IR
  dataclass fields, translation idioms, and CLI flags.
- django-moo's `reference/bootstrapping` — the contract the importer
  emits against (`initialize_dataset`, `get_or_create_object`,
  `load_verbs`).
- django-moo's `tutorials/custom-world` — the package layout the
  importer reproduces, with a step-by-step walkthrough.
- The upstream Zork I source, MIT-licensed:
  <https://github.com/the-infocom-files/zork1>
