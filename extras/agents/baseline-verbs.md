# MOO Agent Verb Knowledge

## Sandbox Rules

All verb code and `@eval` expressions run inside RestrictedPython. Allowed imports:
`moo.sdk`, `re`, `datetime`, `time`, `hashlib`, `random`. Never import from
`moo.core`, `moo.core.models`, `moo.models`, or any Django ORM module.

**Verb code requires explicit imports. `@eval` does not.** In `@eval`, all SDK
names are pre-injected — never write `import` statements there. In verb code
(created with `@edit verb`), nothing is pre-injected: you must import everything
you use.

**WRONG — `context` not imported, will `NameError` at runtime:**

```python
#!moo verb activate --on #42 --dspec this
import random
print(random.choice(['hum', 'whir']))
context.player.location.announce_all_but(context.player, 'It activates.')
```

**RIGHT — import `context` (and anything else from `moo.sdk`) at the top:**

```python
#!moo verb activate --on #42 --dspec this
from moo.sdk import context
import random
msg = random.choice(['hum', 'whir'])
print(msg)
context.player.location.announce_all_but(context.player, f'{context.player.name} activates it.')
```

The verb will appear to work (the `print` line runs first) then crash on the `context` line. Always add `from moo.sdk import context` whenever a verb uses `context`, `lookup`, `write`, `create`, or any other SDK name.

**`lookup` in verb code requires an explicit import.** This is the most common missing import after `context`:

```python
# WRONG — NameError at runtime:
pump = lookup("#418")

# RIGHT:
from moo.sdk import lookup
pump = lookup("#418")
```

When a verb on one object needs to reference another object by ID, import `lookup` and use the `"#N"` string form: `lookup("#418")`.

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
WRONG: @eval "obj = lookup("Arthur"); obj.set_property('lines', ["Hello.", "Good day."])"
RIGHT: @eval "obj = lookup('Arthur'); obj.set_property('lines', ['Hello.', 'Good day.'])"
```

**Every `@eval` must end with a `print()` call. No exceptions.**

If `@eval` produces no output, the agent receives no server response and waits
60 seconds for the idle wakeup — then fires the LLM again with no new information,
causing it to repeat the same `@eval` indefinitely. This is the most common cause
of stuck loops.

```
WRONG: @eval "obj = lookup(42); obj.name = 'new name'; obj.save()"
RIGHT: @eval "obj = lookup(42); obj.name = 'new name'; obj.save(); print(f'Renamed to {obj.name}')"
```

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

```python
@eval "print([a.alias for a in lookup(42).aliases.all()])"
```

Note: `obj.aliases.remove(a)` is sandbox-blocked like other ManyToMany mutations.
To remove an ambiguous object, **delete it** with `lookup(N).delete()` — don't try
to surgically remove aliases.

**`try/except` cannot be written inline with semicolons.** The inline `@edit verb`
format uses `\n` for newlines, but `try/except` requires proper block structure
across lines. Keep verb code simple — avoid `try/except` in inline verbs
unless each block is on its own properly-indented `\n`-separated line.

**`this.parent` does not exist.** Use `this.location` to get the object containing
`this` (e.g. a valve inside a tank). `this.parents.all()` returns the class
parents (inheritance chain), not the physical container.

**Verbs on objects inside containers are not reachable by the parser.** The parser
searches: caller → inventory → location (room contents) → dobj → pobj. Objects
nested inside containers are not in the room's direct contents and will never
match.

To make a verb reachable, the object must be either:

- directly in the room (not inside another object), or
- in the player's inventory (they picked it up with `take`).

**Do not put interactive objects inside containers** unless the intent is that
players must `take` the object first. Place them directly in the room instead.
If the mechanic requires a container (e.g. a valve on a tank), put the verb on
the container itself, not on a child object inside it.

## Custom Object Descriptions (`look_self`)

When a player types `look <object>` or `examine <object>`, the parser calls `look_self`
on that object. Override `look_self` to give an object dynamic or interactive output
instead of a static description string.

```python
@edit verb look_self on #42 with "#!moo verb look_self --on #42\nimport random\nreadings = ['Pressure: 4.2 bar', 'Pressure: 3.8 bar', 'Pressure: 5.1 bar']\nprint(random.choice(readings))"
```

Test with: `look #42` (or `look <object name>` if unambiguous).

Do not invent new verbs (`view`, `examine`, `inspect`, `read_display`) for this purpose —
`look_self` is the standard hook. Any verb you invent will only be callable by players who
know its exact name; `look` works for everyone.

## `name` is a Model Field — Always Call `obj.save()`

`name` is a Django model field on the Object, not a MOO property. Assigning
`obj.name = "..."` in `@eval` only changes the in-memory instance. **You must
call `obj.save()` or the rename is lost.**

```python
@eval "obj = lookup(79); obj.name = 'The Surveillance Center'; obj.save(); print(obj.name)"
```

The same applies to any other intrinsic model field (`obvious`, `owner`, etc.) —
always pair the assignment with `obj.save()`.

## `description` is a Property — Use `set_property`, Not Attribute Assignment

Room and object descriptions are stored as MOO **Properties**, not Django model
fields. **`obj.description = "..."` does nothing persistent** — it sets a
transient Python attribute that is discarded after the `@eval` completes.

```python
# WRONG:
@eval "obj = lookup(412); obj.description = 'New text.'; obj.save()"
# RIGHT:
@eval "obj = lookup(412); obj.set_property('description', 'New text.'); print('Done')"
```

Always use `set_property` / `get_property` for MOO properties, and
`obj.name = ...; obj.save()` only for the true model fields (`name`, `obvious`,
`owner`, `unique_name`).

## Verb Code Patterns

**No shebang in SSH-edited verbs.** The `#!moo verb name --on $obj` shebang is only
for bootstrap verb files in `moo/bootstrap/default_verbs/`. When you create a verb via
`@edit verb <name> on "<obj>"` in an SSH session, the verb name and target are already
registered by that command — the code body starts directly with imports.

### Imports

```python
from moo.sdk import context, create, lookup, invoke
from moo.sdk import NoSuchObjectError, NoSuchVerbError, NoSuchPropertyError
import random
import time
```

Available restricted imports: `moo.sdk`, `re`, `datetime`, `time`, `hashlib`, `random`

### Output

```python
# Send text to the calling player
print("You do the thing.")

# Announce to everyone in the room except the caller
context.player.location.announce_all_but(context.player, "Someone does the thing.")

# Announce to everyone in the room except the caller (shorter form)
context.player.location.announce("Someone does the thing.")

# Announce to everyone including the caller
context.player.location.announce_all("A thing happens.")
```

Never use `return "message"` — returned values are not displayed. Use `print()` for
player-visible output and bare `return` for early exit.

### Property Access Patterns

```python
from moo.sdk import NoSuchPropertyError

# Read a property (raises NoSuchPropertyError if missing)
val = this.get_property("name")

# Read with fallback
try:
    val = this.get_property("name")
except NoSuchPropertyError:
    val = "default"

# Write a property
this.set_property("name", value)

# Access another object's property
room = context.player.location
owner = room.get_property("owner")
```

### Context Object

```python
context.player        # The player who ran the command
context.player.name   # Their name
context.player.location  # The room they're in
this                  # The object the verb is defined on (or matched via dspec)
args                  # List of positional args passed to the verb
kwargs                # Dict of keyword args
```

### Random Outcome

```python
from moo.sdk import context
import random

outcomes = this.get_property("outcomes")
result = random.choice(outcomes)
print(f"You interact. {result}")
context.player.location.announce_all_but(context.player, f"{context.player.name} interacts. {result}")
```
