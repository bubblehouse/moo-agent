# MOO Agent Baseline Knowledge

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

## Verb Dispatch: `--dspec` and `--ispec`

Verbs are called as `<verb> [dobj] [prep iobj]`. The parser only matches a verb
if its shebang declares the right argument spec. Always open verb code with a
shebang line; use `\n` as the line separator inside the inline `with "..."` string.

**`--dspec` (alias: `--dobj`)** — controls whether the verb accepts a direct object:

| Shebang flag | Call syntax | When to use |
|---|---|---|
| *(omitted)* | `switch` | no dobj — verb acts on itself or room |
| `--dspec any` | `switch monitors` | verb needs a dobj from anywhere |
| `--dspec this` | matches only when this object is the dobj | verb is on the object being acted upon |
| `--dspec either` | `switch` or `switch monitors` | dobj is optional |

Without `--dspec any`, calling `switch monitors` fails with "The verb X doesn't
take a direct object."

**`--ispec` (alias: `--iobj`)** — adds an indirect object via a preposition:

| Shebang flag | Call syntax | When to use |
|---|---|---|
| `--iobj with:any` | `unlock door with key` | verb needs a prep + iobj |
| `--iobj in:this` | `put sword in chest` | verb is on the container |
| `--iobj to:any` | `give key to guard` | verb needs a recipient |

**Use `--iobj` not `--ispec`** — both work, but `--iobj` is shorter and harder to misspell. `--isppec`, `--ispec`, `--ispce` are all common typos that cause `malformed shebang` errors. Prefer `--iobj`.

Multiple `--ispec` flags are allowed for verbs that accept several prepositions.

**Reading the indirect object inside verb code — use `context.parser.get_pobj(prep)`.**
`args` does not contain the iobj. Use the parser to retrieve it:

```
#!moo verb use --on #209 --dspec either --ispec with:any
from moo.sdk import context
import random
iobj = context.parser.get_pobj("with")   # returns the Object, raises NoSuchObjectError if absent
sequences = ['ATGCGT...', 'TTAGCC...', 'GCTAAA...']
seq = random.choice(sequences)
print(f'You use the {iobj.name} on the terminal. The screen flickers: {seq}')
```

To check if the preposition was provided at all: `context.parser.has_pobj_str("with")`.
To get the iobj as a string (not an Object): `context.parser.get_pobj_str("with")`.

WRONG: `obj_name = args[0]` — `args` is empty; the iobj is never passed via `args`.
RIGHT: `iobj = context.parser.get_pobj("with")` — always use the parser.

**The shebang requires `--on` to be parsed.** Without it, `--dspec` and `--ispec`
are silently ignored and the verb gets `direct_object='none'`. Use the `#N` id
of the object you are editing — this is the most reliable form.

**The shebang line requires its own `\n` — just like every other line.** Missing
the `\n` immediately after the shebang merges it with the first import, causing
`ValueError: No escaped character` and a server traceback.

WRONG: `"#!moo verb foo --on #42 --dspec any\import random"` ← missing `\n`, causes `anyimport` parse error
RIGHT: `"#!moo verb foo --on #42 --dspec any\nimport random"` ← correct

This is especially common with `--iobj`: `--iobj with:any\nimport` is correct; `--iobj with:any\import` silently merges `any` with `import` into `anyimport`, which fails ispec validation.

```
@edit verb switch on #118 with "#!moo verb switch --on #118 --dspec any\nimport random\nprint('hello')"
```

```
@edit verb unlock on #42 with "#!moo verb unlock --on #42 --dspec any --ispec with:any\nprint('unlocked')"
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

@recycle "<obj>"                                    destroy an object permanently
@recycle #N                                         by object ID

```

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

**`@edit verb X on #N` fails if a `$note` object is in the current room.** `$note` has
its own `@edit` verb with `--dspec any` that intercepts the command and sets the note's
text instead of creating a verb on your target. To work around this, teleport away from
the note before editing: `@move me to #N` to a room with no notes, run your `@edit verb`
commands, then return. Alternatively, `@move` the note out of the room first.

**Always use `#N` when targeting a specific object — for `@alias`, `@edit verb ... on`, `@edit property ... on`, `@describe`, `@move`, and `@obvious`.** Even when the object is in your current room, another object with the same name may exist elsewhere in the world. The parser will find the wrong one and silently operate on it. The `@create` response always gives you `#N` — use it immediately and keep it for all subsequent operations on that object:

```
WRONG: @alias "flashlight" as "torch"            → may alias a different flashlight
RIGHT: @alias #277 as "torch"                    → aliases exactly the object you just created

WRONG: @edit verb flip on "Main Electrical Panel" with "..."  → may land on a $note
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
