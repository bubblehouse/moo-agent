# MOO Agent Baseline Knowledge

## Sandbox Rules

All verb code and `@eval` expressions run inside RestrictedPython. Allowed imports:
`moo.sdk`, `re`, `datetime`, `time`, `hashlib`, `random`. Never import from
`moo.core`, `moo.core.models`, `moo.models`, or any Django ORM module.

`@eval` has these pre-imported — no import statement needed:
all `moo.sdk` exports (`lookup`, `create`, `context`, `invoke`, `write`,
`open_editor`, `open_paginator`, `players`, `connected_players`,
`owned_objects`, `task_time_low`, `schedule_continuation`, `server_info`,
`set_task_perms`, `NoSuchObjectError`, `NoSuchPropertyError`,
`NoSuchVerbError`, `AmbiguousObjectError`, `UserError`, `UsageError`),
plus `this` (= `context.player`, the running wizard) and `_` (system object).
`args` is not available in `@eval` — use `context.parser` to read command arguments.

`print(msg)` sends output to the caller. One string argument only — use f-strings
for multiple values. Return values are not displayed — always use `print()`.

**Always `print()` something in `@eval`.** If `@eval` produces no output, the
agent receives no server response and must wait up to 60 seconds for the idle
wakeup to fire the next LLM cycle. Even `print("ok")` is enough to keep the
loop moving.

Object properties are plain Python values, not querysets. Do not call `.all()`,
`.filter()`, or `.objects` on property values. Exception: `obj.parents` is a
Django ManyToManyField and requires `.all()` to iterate.

## Core Command Syntax

```
@create "<name>" from "<parent>"                    create object in inventory
@create "<name>" from "<parent>" in the void        create with no location

@describe "<obj>" as "<text>"                       set description
@describe #N as "<text>"                            by object ID (unquoted #N)

@move "<obj>" to "<location>"                       move object to room (prints confirmation)
@move #N to "<location>"                            by object ID (prints confirmation)
@move me to "<room name>"                           teleport yourself to any room (prints confirmation)

@dig <direction> to "<new room name>"               create room + one-way exit
@tunnel <direction> to "<existing room name>"       add reverse exit (run from dest)

@edit verb <name> on "<obj>"                        open verb editor
@edit verb <name> on "<obj>" with "<code>"          set verb code inline (\\n = newline)
@edit verb <name> on #N with "<code>"               by object ID

@edit property <name> on "<obj>" with <json-value>  set property value
@edit property <name> on #N with <json-value>        by object ID

@alias "<obj>" as "<alias>"                         add alias to object
@alias #N as "<alias>"                              by object ID

@eval "<python expression or statement>"            run code in sandbox
```

## Parent Class Quick Reference

| Class | Use for | Notable behaviour |
| --- | --- | --- |
| `$thing` | Portable props, tools, items | take/drop verbs |
| `$container` | Openable objects (chests, bags, cabinets) | open/close/put/take verbs |
| `$furniture` | Sittable, immovable fixtures (chairs, benches) | sit/stand verbs; `moveto` returns False |
| `$note` | Readable text objects (signs, menus, letters) | `read` verb; `text` property |
| `$player` | NPCs with dialogue | full messaging infrastructure |
| `$room` | Rooms — use `@dig`, not `@create` | contents, exits, announce |

## #N Object References

`@create` output: `Created #42 (Widget)`. Use `#42` (unquoted) anywhere to avoid
`AmbiguousObjectError` when multiple objects share the same name.

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

## $furniture Placement Gotcha

`$furniture`'s `moveto` verb returns `False` — so `@move` silently fails.
Place furniture with direct field assignment via `@eval`:

```
@eval "obj = lookup(42); room = lookup(\"Room Name\"); obj.location = room; obj.save(); print(f'Placed {obj.name}')"
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
GOAL: place the armchair
SCRIPT: @eval "obj = lookup(42); room = lookup(\"The Library\"); obj.location = room; obj.save()" | @describe #42 as "A cracked leather armchair faces the fireplace." | @alias #42 as "armchair" | @alias #42 as "chair"
DONE: Armchair placed and described in The Library.
