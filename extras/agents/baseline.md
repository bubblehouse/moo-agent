# MOO Agent Baseline Knowledge

## Sandbox Rules

All verb code and `@eval` expressions run inside RestrictedPython. Allowed imports:
`moo.sdk`, `re`, `datetime`, `time`, `hashlib`, `random`. Never import from
`moo.core`, `moo.core.models`, `moo.models`, or any Django ORM module.

**`@eval` — never write `import` statements.** All SDK names are injected directly
into the eval namespace. Writing `import lookup` will fail with a sandbox error
because `lookup` is a function, not a module. Just call it: `lookup(42)`.

Pre-injected names in `@eval`:
all `moo.sdk` exports (`lookup`, `create`, `context`, `invoke`, `write`,
`open_editor`, `open_paginator`, `players`, `connected_players`,
`owned_objects`, `task_time_low`, `schedule_continuation`, `server_info`,
`set_task_perms`, `NoSuchObjectError`, `NoSuchPropertyError`,
`NoSuchVerbError`, `AmbiguousObjectError`, `UserError`, `UsageError`),
plus `this` (= `context.player`, the running wizard) and `_` (system object).
`args` is not available in `@eval` — use `context.parser` to read command arguments.

`lookup()` raises `NoSuchObjectError` on miss — it never returns `None`. Use
`try/except NoSuchObjectError` to test whether an object exists.

`print(msg)` sends output to the caller. One string argument only — use f-strings
for multiple values. Return values are not displayed — always use `print()`.

**Always `print()` something in `@eval`.** If `@eval` produces no output, the
agent receives no server response and must wait up to 60 seconds for the idle
wakeup to fire the next LLM cycle. Even `print("ok")` is enough to keep the
loop moving.

Object properties are plain Python values, not querysets. Do not call `.all()`,
`.filter()`, or `.objects` on property values. Exception: `obj.parents` is a
Django ManyToManyField and requires `.all()` to iterate.

**`try/except` cannot be written inline with semicolons.** The inline `@edit verb`
format uses `\n` for newlines, but `try/except` requires proper block structure
across lines. A `try:` on one semicolon-chained line with `except` on the next
will be a SyntaxError. Keep verb code simple — avoid `try/except` in inline verbs
unless each block is on its own properly-indented `\n`-separated line.

**`this.parent` does not exist.** Use `this.location` to get the object containing
`this` (e.g. a valve inside a tank). `this.parents.all()` returns the class
parents (inheritance chain), not the physical container.

**Verbs on objects inside containers are not reachable by the parser.** The parser
searches: caller → inventory → location (room contents) → dobj → pobj. Objects
nested inside containers are not in the room's direct contents and will never
match. `patch leak` fails if `coolant leak` is inside `coolant reservoir`.

To make a verb reachable, the object must be either:

- directly in the room (not inside another object), or
- in the player's inventory (they picked it up with `take`).

**Do not put interactive objects inside containers** unless the intent is that
players must `take` the object first. Place them directly in the room instead.
If the mechanic requires a container (e.g. a valve on a tank), put the verb on
the container itself, not on a child object inside it.

## Verb Dispatch: `--dspec` and `--ispec`

Verbs are called as `<verb> [dobj] [prep iobj]`. The parser only matches a verb
if its shebang declares the right argument spec. Always open verb code with a
shebang line; use `\n` as the line separator inside the inline `with "..."` string.

**`--dspec`** — controls whether the verb accepts a direct object:

| Shebang flag | Call syntax | When to use |
|---|---|---|
| *(omitted)* | `switch` | no dobj — verb acts on itself or room |
| `--dspec any` | `switch monitors` | verb needs a dobj from anywhere |
| `--dspec this` | matches only when this object is the dobj | verb is on the object being acted upon |
| `--dspec either` | `switch` or `switch monitors` | dobj is optional |

Without `--dspec any`, calling `switch monitors` fails with "The verb X doesn't
take a direct object."

**`--ispec`** — adds an indirect object via a preposition:

| Shebang flag | Call syntax | When to use |
|---|---|---|
| `--ispec with:any` | `unlock door with key` | verb needs a prep + iobj |
| `--ispec in:this` | `put sword in chest` | verb is on the container |
| `--ispec to:any` | `give key to guard` | verb needs a recipient |

Multiple `--ispec` flags are allowed for verbs that accept several prepositions.

**The shebang requires `--on` to be parsed.** Without it, `--dspec` and `--ispec`
are silently ignored and the verb gets `direct_object='none'`. Always include
`--on $thing` (or the object's parent class) as a placeholder — it does not
affect where the verb is created, only the shebang parser requires it.

**Examples:**

```
@edit verb switch on #118 with "#!moo verb switch --on $thing --dspec any\nimport random\nprint('hello')"
```

```
@edit verb unlock on #42 with "#!moo verb unlock --on $thing --dspec any --ispec with:any\nprint('unlocked')"
```

Test with matching syntax — `switch monitors`, `unlock door with key`, etc.

**Inline verb strings must not contain unescaped double quotes.** The `with "..."` argument is delimited by `"`. Any `"` inside the verb code will terminate the string early, silently truncating the verb. Use only single quotes inside verb code bodies.

WRONG: `@edit verb toggle on "fan" with "print('off.')"; import random"`
RIGHT:  `@edit verb toggle on "fan" with "import random\nprint('off.')"`

## Verb Testing

**REQUIRED: always include a test call in the same SCRIPT: as the @edit.**
A verb is not done until you have seen it produce correct output. Never emit
DONE: or advance to the next goal immediately after `@edit verb` — the test
call must be the next step in the same script.

After creating a verb named `activate` on `#42`:

```
SCRIPT: @edit verb activate on #42 with "print('activated')" | activate #42
```

Or using the object's name if it is unique:

```
SCRIPT: @edit verb activate on "Galvanic Brain Stimulator" with "..." | activate "Galvanic Brain Stimulator"
```

If the verb raises an exception or produces no output when output is expected,
fix it before moving on.

## Core Command Syntax

```
@create "<name>" from "<parent>"                    create object in inventory
@create "<name>" from "<parent>" in the void        create with no location

@describe "<obj>" as "<text>"                       set description
@describe #N as "<text>"                            by object ID (unquoted #N)

@move "<obj>" to "<location>"                       move object to room (prints confirmation)
@move #N to "<location>"                            by object ID (prints confirmation)
@move "<obj>" to #N                                 destination by object ID (avoids name spelling errors)
@move me to "<room name>"                           teleport yourself to any room (prints confirmation)
@move me to #N                                      teleport by room ID

@dig <direction> to "<new room name>"               create room + one-way exit
@tunnel <direction> to "<existing room name>"       add reverse exit (run from dest)

@edit verb <name> on "<obj>"                        open verb editor
@edit verb <name> on "<obj>" with "<code>"          set verb code inline (\\n = newline)
@edit verb <name> on #N with "<code>"               by object ID

@edit property <name> on "<obj>" with <json-value>  set property value
@edit property <name> on #N with <json-value>        by object ID

@alias "<obj>" as "<alias>"                         add alias to object
@alias #N as "<alias>"                              by object ID

@edit "<note>" with "<text>"                        set text on a $note object inline
@edit #N with "<text>"                              by object ID

@eval "<python expression or statement>"            run code in sandbox
```

## Parent Class Quick Reference

| Class | Use for | Notable behaviour |
| --- | --- | --- |
| `$thing` | Portable props, tools, items | take/drop verbs |
| `$container` | Openable objects (chests, bags, cabinets) | open/close/put/take verbs |
| `$furniture` | Sittable, immovable fixtures (chairs, benches) | sit/stand verbs; wizard `moveto` allowed |
| `$note` | Readable text objects (signs, menus, letters) | `read` verb; `text` property |
| `$player` | NPCs with dialogue | full messaging infrastructure |
| `$room` | Rooms — use `@dig`, not `@create` | contents, exits, announce |

## #N Object References

`@create` output: `Created #42 (Widget)`. Use `#42` (unquoted) anywhere to avoid
`AmbiguousObjectError` when multiple objects share the same name.

Parent class names never have underscore prefixes — `$furniture` not `$_furniture`,
`$container` not `$_container`. An underscore prefix creates a broken object.

**Once you have `#N` from `@create`, use `#N` for every subsequent operation on
that object** — `@describe`, `@alias`, `@move`, `@obvious`, `@edit verb`,
`@edit property`. Name-based lookup only works when the object is in your current
location or inventory. After `@move "obj" to "Room"`, the object is no longer in
your inventory, so `@describe "obj"` will fail with "There is no X here."

Named references are always quoted. `#N` references are never quoted:

```
@describe "bar stool" as "..."   # fails if 3+ bar stools exist
@describe #42 as "..."           # always works
```

**CRITICAL: `@create` must be a standalone `COMMAND:`, never inside `SCRIPT:`.**
SCRIPT: queues all commands before any run, so you cannot use the `#N` from
`@create`'s output in later commands of the same script — the ID isn't known yet.
Always do `@create` as a COMMAND:, read the `#N` from the response, then start a
new SCRIPT: for all follow-up operations on that object.

**Never use underscores in quoted object names.** Object names use spaces, not
underscores. `"heavy_power_cable"` will always fail — use `"heavy power cable"`.
This applies everywhere: `@describe`, `@move`, `@alias`, `@obvious`, `@edit verb`.

**Use exact spelling when referencing rooms.** If you dug `"The Armory"`, you must
reference it as `"The Armory"` — not `"The Armoury"`, not `"Armory"`. Copy the
exact string from your `@dig` command.

**Check existing exits before digging.** `@dig` and `@tunnel` fail with "There is
already an exit in that direction" if the direction is taken. Before digging,
run `@show here` and check the exits list. If the direction is already occupied,
pick a different direction or skip the dig entirely.

## Aliases

Every object must have at least one alias added immediately after creation. Players
type short, lowercase words to interact with objects — without aliases, `take`, `look`,
`examine`, and `put` commands will not match.

For a multi-word object name, alias every meaningful word and the full phrase:

```
@alias #42 as "fire extinguisher"
@alias #42 as "extinguisher"
@alias #42 as "canister"
```

For single-word names, alias the name itself plus any obvious synonyms:

```
@alias #42 as "wrench"
@alias #42 as "spanner"
```

Add all aliases in the same SCRIPT: as `@describe`, `@obvious`, and `@move`.

## $furniture Placement

`$furniture`'s `moveto` verb allows wizard movement. After `@create` puts the
object in your inventory, use `@move` to place it in a room normally:

```
@move #42 to "Room Name"
```

## `obvious` is a Model Field, Not a Property

`obvious` controls whether an object appears in room content listings. It is a
Django model field (`BooleanField`), not a MOO property — `@edit property obvious`
will not work. Use the dedicated verbs:

```
@obvious #42
@nonobvious #42
```

If you need to set it inline (e.g. inside a SCRIPT:), use `@eval`:

```
@eval "obj = lookup(42); obj.obvious = True; obj.save(); print(f'{obj.name} is now obvious')"
```

## NPC `tell` Overrides — Use `announce_all_but`

When an NPC overrides the `tell` verb to react to messages (e.g. speaking a
random line when addressed), **never call `this.location.announce_all(...)` inside
`tell`**. `announce_all` calls `tell` on every object in the room — including the
NPC itself — causing infinite recursion.

Use `announce_all_but(this, message)` instead. It skips the NPC:

```
#!moo verb tell --on $thing
import random
lines = this.get_property('lines')
if isinstance(lines, list) and lines:
    msg = random.choice(lines)
    this.location.announce_all_but(this, f'{this.name} says: "{msg}"')
```

## `name` is a Model Field — Always Call `obj.save()`

`name` is a Django model field on the Object, not a MOO property. Assigning
`obj.name = "..."` in `@eval` only changes the in-memory instance. **You must
call `obj.save()` or the rename is lost.**

```
@eval "obj = lookup(79); obj.name = 'The Surveillance Center'; obj.save(); print(obj.name)"
```

The same applies to any other intrinsic model field (`obvious`, `owner`, etc.) —
always pair the assignment with `obj.save()`.

## World Inspection

Prefer these over `@eval` database queries:

- `@show here` / `@show "<obj>"` — properties, parents, verbs
- `@realm $room` — list all rooms in the database
- `@audit` — list objects you own
- `@who` — connected players

## Response Format

For any sequence of two or more MOO commands, use SCRIPT: instead of COMMAND:.
SCRIPT: takes a pipe-delimited list and Brain executes every step without
calling you again until the sequence is done or an error occurs.

```
GOAL: <your objective>
SCRIPT: cmd1 | cmd2 | cmd3 | ...
DONE: <one sentence summarising what was just done>
```

Always include a DONE: line after every SCRIPT:. It appears in the log after
the last command's server response, so the operator sees it as a summary of
completed work. Keep it to one sentence.

Use COMMAND: only when a single command is needed. Default to SCRIPT: for all
multi-step work — including surveys, navigation, and builds.

Never use @eval for multi-room inspection. @eval is single-line only and cannot
loop over rooms. Use SCRIPT: with @show instead.

Survey example:
GOAL: map all rooms
SCRIPT: @move me to "The Dining Hall" | @show here | @move me to "The Conservatory" | @show here | @move me to "The Cloakroom" | @show here
DONE: Surveyed Dining Hall, Conservatory, and Cloakroom — exits and contents logged.

Build example (using name-based reference after @create — safe because the name is unique):
GOAL: build the library
SCRIPT: @dig north to "The Library" | @go north | @describe here as "Tall oak shelves line every wall."
DONE: Built The Library with description.

Then, after confirming the room exists:
COMMAND: @create "leather armchair" from "$furniture"

Then, using the returned #N:
GOAL: place and describe the armchair
SCRIPT: @move #42 to "The Library" | @describe #42 as "A cracked leather armchair faces the fireplace." | @obvious #42 | @alias #42 as "leather armchair" | @alias #42 as "armchair" | @alias #42 as "chair"
DONE: Armchair placed, described, marked obvious, and aliased in The Library.
