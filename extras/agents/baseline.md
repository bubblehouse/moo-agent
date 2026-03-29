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

## $furniture Placement Gotcha

`$furniture`'s `moveto` verb returns `False` — so `@move` silently fails.
Place furniture with direct field assignment via `@eval`:

```
@eval "obj = lookup(42); room = lookup(\"Room Name\"); obj.location = room; obj.save()"
```

## World Inspection

Prefer these over `@eval` database queries:

- `@show here` / `@show "<obj>"` — properties, parents, verbs
- `@realm $room` — list all rooms in the database
- `@audit` — list objects you own
- `@who` — connected players
