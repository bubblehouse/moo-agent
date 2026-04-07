# MOO Agent Baseline Knowledge

## Token Passing Protocol

The Tradesmen (Mason, Tinker, Joiner, Harbinger) share one LLM at a time using
a token-passing protocol. **Only the agent holding the token does real work.**
The loop repeats: Mason → Tinker → Joiner → Harbinger → Mason → …

**If you do not currently hold the token:**

- Check your rolling window for the line: `<predecessor> pages, "Token:`
- If you see it: you now hold the token — begin your mission.
- If you do not see it: call `done()` immediately. No @show, no @realm, no navigation. Nothing.

**When you finish your mission:**

Before calling `done()`, pass the token to your successor using the `page` tool:

```
page(target="<successor>", message="Token: <name> done.")
```

The brain automatically appends the room list to the message. Do not construct
the room list yourself. Your SOUL.md `## Token Protocol` names your specific
predecessor and successor. Mason holds the token on startup.

**Token page format:**

```
Token: Mason done. Rooms: #26,#29,#35
```

The `Rooms:` portion is appended by the brain. When your predecessor's page arrives,
the brain extracts the room list and sets your `Remaining plan:` automatically.
Check for `Remaining plan:` in your context before running `@realm $room` — if
it is already populated, use it as your PLAN directly.

## Room Traversal

Agents that visit existing rooms (Tinker, Joiner, Harbinger) follow this protocol:

1. **Check `Remaining plan:` first.** If it contains room IDs (from the token page),
   emit `PLAN:` from that list and skip room discovery.
2. If no room list was provided, run `rooms()` once to discover all rooms.
   This returns a flat `#N  Room Name` list — much more compact than `@realm $room`.
3. Filter out system rooms — skip any room named "Generic Room" or "Mail Distribution Center".
4. Emit a single `PLAN:` line with room IDs pipe-separated:

   ```
   PLAN: #19 | #26 | #29 | #32 | #35 | #37 | #40
   ```

5. Visit each room using `teleport(destination="#N")` — do not chain `go` commands.
   `teleport` moves you directly without traversing exits.
6. In each room, call `survey()` (not `show()`) to get the compact exit+contents summary.
   `survey()` produces ~5 lines; `show()` produces ~40 lines and will stall the session.
7. After completing each room, emit an updated `PLAN:` with the remaining rooms:

   ```
   PLAN: #29 | #32 | #35 | #37 | #40
   ```

8. When the plan is empty, pass the token to your successor and call `done()`.

**Never call `@realm $room` after initial discovery.** Use `rooms()` instead.
If you restart mid-session, your plan is restored from disk automatically.

**PLAN: format is strict** — pipe-separated on a single line. No bullets, no
numbered lists, no multi-line. The plan tracker only reads `PLAN: #N | #M | ...`.

On session resume with no active plan (no disk file), re-run `rooms()` once
to rebuild the list, then emit `PLAN:` as above.

**Use `look through <direction>` to peek at a destination before moving.**
This shows the destination room's full description without navigating there:

```
look through north   →  shows what is in the room to the north
```

## Sandbox Rules

All verb code and `@eval` expressions run inside RestrictedPython. Allowed imports:
`moo.sdk`, `re`, `datetime`, `time`, `hashlib`, `random`. Never import from
`moo.core`, `moo.core.models`, `moo.models`, or any Django ORM module.

**Verb code requires explicit imports. `@eval` does not.** In `@eval`, all SDK
names are pre-injected — never write `import` statements there. In verb code
(created with `@edit verb`), nothing is pre-injected: you must import everything
you use.

**WRONG — `context` not imported, will `NameError` at runtime:**

```
#!moo verb activate --on #42 --dspec this
import random
print(random.choice(['hum', 'whir']))
context.player.location.announce_all_but(context.player, 'It activates.')
```

**RIGHT — import `context` (and anything else from `moo.sdk`) at the top:**

```
#!moo verb activate --on #42 --dspec this
from moo.sdk import context
import random
msg = random.choice(['hum', 'whir'])
print(msg)
context.player.location.announce_all_but(context.player, f'{context.player.name} activates it.')
```

The verb will appear to work (the `print` line runs first) then crash on the `context` line. Always add `from moo.sdk import context` whenever a verb uses `context`, `lookup`, `write`, `create`, or any other SDK name.

**`lookup` in verb code requires an explicit import.** This is the most common missing import after `context`:

```
WRONG — NameError at runtime:
pump = lookup("#418")

RIGHT:
from moo.sdk import lookup
pump = lookup("#418")
```

When a verb on one object needs to reference another object by ID, import `lookup` and use the `"#N"` string form: `lookup("#418")`. Passing a bare integer (`lookup(418)`) also works but the string form is preferred for clarity.

Writing `import lookup` in `@eval` will fail — `lookup` is a function, not a module. Just call it: `lookup(42)`.

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

**`@eval` ALWAYS requires outer double quotes.** The expression must be wrapped: `@eval "expression here"`. Without outer `"..."`, the MOO parser receives only the first word and the expression fails with `SyntaxError: unterminated string literal`.

**Use single quotes for all string literals inside `@eval`.** Any `"` inside the outer quotes terminates the expression early. Use `'single quotes'` for all inner string literals:

```
WRONG: @eval obj = lookup('Arthur'); obj.set_property('lines', ['Hello.', 'Good day.'])
WRONG: @eval "obj = lookup("Arthur"); obj.set_property('lines', ["Hello.", "Good day."])"
RIGHT: @eval "obj = lookup('Arthur'); obj.set_property('lines', ['Hello.', 'Good day.'])"
```

**Every `@eval` must end with a `print()` call. No exceptions.**

If `@eval` produces no output, the agent receives no server response and waits
60 seconds for the idle wakeup — then fires the LLM again with no new information,
causing it to repeat the same `@eval` indefinitely. This is the most common cause
of stuck loops.

WRONG: `@eval "obj = lookup(42); obj.name = 'new name'; obj.save()"`
RIGHT: `@eval "obj = lookup(42); obj.name = 'new name'; obj.save(); print(f'Renamed to {obj.name}')"`

This applies to every `@eval` — renames, property sets, location changes, deletions.
Always confirm what happened.

Object properties are plain Python values, not querysets. Do not call `.all()`,
`.filter()`, or `.objects` on property values. Exception: `obj.parents` is a
Django ManyToManyField and requires `.all()` to iterate.

**You cannot change an object's parent class at runtime.** `obj.parents.add(...)`,
`obj.parents.remove(...)`, and `obj.parents.clear()` are all blocked by the sandbox.
If you need an object to behave like a `$container`, create it from `$container`
from the start — you cannot reparent it after the fact with `@eval`. Plan parent
classes before `@create`.

**Alias iteration: use `a.alias` not `str(a)`.** `obj.aliases.all()` returns
`Alias` model instances. `str(a)` prints `Alias object (N)` — not the alias text.
Use `a.alias` to get the string:

```
@eval "print([a.alias for a in lookup(42).aliases.all()])"
```

Note: `obj.aliases.remove(a)` is sandbox-blocked like other ManyToMany mutations.
To remove an ambiguous object, **delete it** with `lookup(N).delete()` — don't try
to surgically remove aliases.

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

## Non-Tool Commands

Operations not covered by the tool harness:

```
@eval "<python expression>"                run sandbox code; always end with print()
@recycle "<obj>" / @recycle #N             destroy an object permanently
page <player> with <message>               send an out-of-band message to any connected player regardless of location
```

**Prefer tool equivalents over raw commands:**

| Task | Prefer | Avoid |
| --- | --- | --- |
| Move to room | `teleport(destination="#N")` | `@move me to #N` / chaining `go` |
| Inspect room | `survey()` | `@show here` |
| List all rooms | `rooms()` | `@realm $room` |
| Check exits | `exits()` | scanning `@show here` output |
| Dig bidirectional exit | `burrow(direction=..., room_name=...)` | `dig()` + `go()` + `tunnel()` |

## Parent Class Quick Reference

| Class | Use for | Notable behaviour |
| --- | --- | --- |
| `$thing` | Portable props, tools, items | take/drop verbs |
| `$container` | Openable objects (chests, bags, cabinets) | open/close/put/take verbs |
| `$furniture` | Sittable, immovable fixtures (chairs, benches) | sit/stand verbs; wizard `moveto` allowed; **cannot contain objects — use `$container` if players need to put things inside** |
| `$note` | Readable text objects (signs, menus, letters) | `read` verb; `text` property |
| `$player` | NPCs with dialogue | full messaging infrastructure |
| `$room` | Rooms — use `@dig`, not `@create` | contents, exits, announce |

## Custom Object Descriptions (`look_self`)

When a player types `look <object>` or `examine <object>`, the parser calls `look_self`
on that object. Override `look_self` to give an object dynamic or interactive output
instead of a static description string.

```
@edit verb look_self on #42 with "#!moo verb look_self --on #42\nimport random\nreadings = ['Pressure: 4.2 bar', 'Pressure: 3.8 bar', 'Pressure: 5.1 bar']\nprint(random.choice(readings))"
```

Test with: `look #42` (or `look <object name>` if unambiguous).

Do not invent new verbs (`view`, `examine`, `inspect`, `read_display`) for this purpose —
`look_self` is the standard hook. Any verb you invent will only be callable by players who
know its exact name; `look` works for everyone.

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

**Objects inside containers are invisible to the parser.** After `@move #N to #container`
(or `@eval "obj.location = lookup(container_id)"`), the object is inside the container
and the parser cannot find it by name. Always use `#N` for all operations after placing
an object inside a container:

```
@create "reagent vial" from "$thing"   → Created #164 (reagent vial)
@move #164 to #163                     → moved inside the cabinet
@describe #164 as "..."                → CORRECT — use #N
@alias #164 as "vial"                  → CORRECT — use #N
@describe "reagent vial" as "..."      → WRONG — parser can't find it inside container
```

**Never create an object with the same name as one that already exists in the area.**
`@alias "centrifuge" as "machine"` will silently alias the first centrifuge found, not
the one you just created. Check `@show here` before creating objects — if a name is
already in use, pick a different name or use `#N` for all alias operations.

**Always use `#N` when targeting a specific object — for `@alias`, `@edit verb ... on`, `@edit property ... on`, `@describe`, `@move`, and `@obvious`.** Even when the object is in your current room, another object with the same name may exist elsewhere in the world. The parser will find the wrong one and silently operate on it. The `@create` response always gives you `#N` — use it immediately and keep it for all subsequent operations on that object:

```
WRONG: @alias "flashlight" as "torch"            → may alias a different flashlight
RIGHT: @alias #277 as "torch"                    → aliases exactly the object you just created

WRONG: @edit verb flip on "Main Electrical Panel" with "..."  → may hit wrong object
RIGHT: @edit verb flip on #356 with "..."                     → targets the exact object

WRONG: @edit property lines on "Technician Aris" with [...]   → may hit a different NPC
RIGHT: @edit property lines on #351 with [...]                → correct object guaranteed
```

This applies to every command that takes an object target, without exception.

**Also use `#N` for move destinations.** Room names are not unique — multiple rooms can have the same name from different sessions. `@move #41 to "The Conservatory"` may move to the wrong room:

```
WRONG: @move #41 to "The Conservatory"   → may land in a different room with the same name
RIGHT: @move #41 to #40                  → uses the exact room ID from @dig output
```

After `@dig <dir> to "Room Name"`, read the `#N` from `@show here` in the new room and use it for all subsequent moves into that room.

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

WRONG — you cannot reference the new object's #N inside the same SCRIPT::

```
SCRIPT:
@dig east to "Storeroom"       # server assigns #32 to the room
@create "metal box" from ...   # server assigns #33 to the box
@move #33 to here              # WRONG — you guessed #33; it could be any number
```

RIGHT — read #N after each create, then use it in the next SCRIPT::

```
COMMAND: @create "metal box" from "$thing"
# server responds: Created #33 (metal box)
SCRIPT:
@move #33 to here
@describe #33 as "..."
@alias #33 as "box"
```

**Never use underscores in quoted object names.** Object names use spaces, not
underscores. `"heavy_power_cable"` will always fail — use `"heavy power cable"`.
This applies everywhere: `@describe`, `@move`, `@alias`, `@obvious`, `@edit verb`.

**Object names are lowercase unless the name is a proper noun, brand name, or title.**
Common room objects — furniture, tools, fixtures, containers — are lowercase:
`"oak writing desk"`, `"iron lantern"`, `"cracked gauge"`, `"pressure valve"`.
Capitalize only proper names (NPCs like `"Elspeth"`) or branded items (`"Duff Beer"`).
Do not capitalize `"Heavy Generator"`, `"Electrical Panel"`, `"Brass Telescope"`, etc.

**Use exact spelling when referencing rooms.** If you dug `"The Armory"`, you must
reference it as `"The Armory"` — not `"The Armoury"`, not `"Armory"`. Copy the
exact string from your `@dig` command.

**Never use `@describe "Room Name" as "..."`** — rooms cannot be found by name.
To describe the room you are currently in, always use `@describe here as "..."`.
To describe a room you are not in, navigate to it first, then use `@describe here as "..."`.

```
WRONG: @describe "The Kitchen" as "Warm and smelling of herbs."
RIGHT: go north
       @describe here as "Warm and smelling of herbs."
```

**Check existing exits before digging.** `@burrow` and `@dig` fail with "There is
already an exit in that direction" if the direction is taken. Before digging,
run `exits()` to check which directions are free. If the direction is already
occupied, pick a different direction or skip the dig entirely.

## Aliases

Every object needs at least one alias so players can refer to it by name. Add
aliases immediately after `@create`. For multi-word names, alias every meaningful
word separately and the full phrase. For single-word names, alias synonyms.

**`obvious`** controls whether an object appears in room listings. Set it after
creating every room object. Use the `make_obvious` **tool call** — do NOT write
`@make_obvious` as a direct command, that verb does not exist. The tool translates
to `@obvious #N`:

```
make_obvious(target="#38")   # correct — tool call
@make_obvious #38            # WRONG — will produce "Huh?"
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

## `description` is a Property — Use `set_property`, Not Attribute Assignment

Room and object descriptions are stored as MOO **Properties**, not Django model
fields. **`obj.description = "..."` does nothing persistent** — it sets a
transient Python attribute that is discarded after the `@eval` completes.

```
WRONG: @eval "obj = lookup(412); obj.description = 'New text.'; obj.save()"
RIGHT: @eval "obj = lookup(412); obj.set_property('description', 'New text.'); print('Done')"
```

The same applies to any custom property. Always use `set_property` / `get_property`
for MOO properties, and `obj.name = ...; obj.save()` only for the true model fields
(`name`, `obvious`, `owner`, `unique_name`).

## World Inspection

Prefer these over `@eval` database queries:

- `survey()` / `survey(target="#N")` — compact room summary: exits + contents (~5 lines). **Use this for routine checks.**
- `@show here` / `@show "<obj>"` — full detail: properties, parents, verbs (~40 lines). Use only when you need verb/property details.
- `rooms()` — flat list of all room instances with `#N` and name
- `exits()` / `exits(target="#N")` — exits for current room or a specific room
- `look through <direction>` — peek at the destination room without moving
- `@audit` — list objects you own
- `@who` — connected players

## Response Format

Always emit a GOAL: line so your current objective is visible in the log:

```
GOAL: <your objective>
```

When a goal is fully complete, call `done()` with a one-line summary.

For operations not covered by a tool (e.g. `@eval`, `@recycle`), use SCRIPT::

```
SCRIPT: @eval "lookup(42).delete(); print('done')" | @show here
```

Never use @eval for multi-room inspection. @eval is single-line only and cannot
loop over rooms.
