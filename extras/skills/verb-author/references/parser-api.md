# Parser API Reference

`context.parser` is the active parser for the current task. It is available in virtually all verb invocations — including synchronous sub-verb calls (`obj.verb_name()`) — because those inherit the calling task's context.

The only case where `context.parser` is `None` is when the verb is invoked by a Celery task that was scheduled *without* a parser (e.g., via `invoke()` with a delay). In those cases the verb is re-entered outside any player command session.

To distinguish "was this verb triggered directly by a player command vs. called as a sub-verb or method", check `args` and `kwargs`, or give the verb multiple aliases and branch on `verb_name`. Do not use `context.parser is None` as a proxy for "called as a method".

## Direct Object Methods

| Method | Returns | Raises | Use when |
|--------|---------|--------|----------|
| `get_dobj()` | Object | `NoSuchObjectError` | You expect the dobj to be an existing game object (local area only) |
| `get_dobj(lookup=True)` | Object | `NoSuchObjectError` | Same, but resolves globally by name/alias/ID anywhere in the database |
| `get_dobj_str()` | str | `NoSuchObjectError` if missing | You want the raw string (a message, a name to create, etc.) |
| `has_dobj()` | bool | — | Check if dobj resolved to an Object |
| `has_dobj_str()` | bool | — | Check if any dobj string was typed |

**Local vs Global Lookup:**

- Without `lookup=True`: searches only the player's inventory and current room
- With `lookup=True`: searches the entire database by name, alias, or `#N` object ID reference
- Use global lookup for admin commands that need to reference objects anywhere (e.g., `@alias #45 as "thing"`)

## Indirect Object Methods

| Method | Returns | Raises | Use when |
|--------|---------|--------|----------|
| `get_pobj(prep)` | Object | `NoSuchObjectError`, `NoSuchPrepositionError` | You expect the iobj to be an existing game object |
| `get_pobj(prep, lookup=True)` | Object | same | Same, resolves globally by name/alias |
| `get_pobj_str(prep)` | str | `NoSuchObjectError` if missing | You want the raw string |
| `has_pobj(prep)` | bool | — | Check if iobj resolved to an Object |
| `has_pobj_str(prep)` | bool | — | Check if any iobj string was typed for this prep |

**There are no `…_string` variants.** The suffix is `_str`, not `_string`. Using `get_pobj_string()` will raise `AttributeError`.

## Other Parser Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `words` | list[str] | All words in the command as typed |
| `verb` | str | The verb name that was matched |
| `command` | str | The full raw command string exactly as the player typed it |

## The `_str` vs Object Distinction

`get_dobj()` and `get_pobj(prep)` perform a database lookup. They resolve the string the player typed into a game Object. If the string does not match any real object, they raise `NoSuchObjectError`.

`get_dobj_str()` and `get_pobj_str(prep)` return the raw string exactly as typed. They never perform a DB lookup. Use these when:

- The argument is a message (`say Hello there`)
- The argument is a name for a new object (`@create My Widget`)
- The argument is a numeric value or any plain text

```python
# WRONG — say's argument is a message string, not an object reference
msg = context.parser.get_dobj()       # raises NoSuchObjectError

# RIGHT
msg = context.parser.get_dobj_str()   # returns "Hello there"
```

## Letting Errors Propagate to the Player

`NoSuchObjectError` and other `UserError` subclasses are automatically caught by the task runner and displayed to the player as a readable red error message. Verbs do not need to wrap parser calls in `try/except` just to handle bad input.

Calling `get_dobj()` when the player typed a non-existent name is intentionally correct — the player sees `"There is no 'widget' here."` with no extra handling in the verb:

```python
#!moo verb unlock --on $thing --dspec this --ispec with:any

from moo.sdk import context

# If the player typed "unlock chest with banana" and there's no banana,
# get_pobj raises NoSuchObjectError and the player sees a sensible message.
key = context.parser.get_pobj("with")

if this.is_unlocked_for(key):
    this.set_property("locked", False)
    print(f"You unlock {this.title()}.")
else:
    print("That doesn't seem to work.")
```

Only catch these exceptions when you need to provide a different message or fall back to alternative logic.

## Preposition Names and Synonyms

Prepositions are defined in `settings.PREPOSITIONS` as a list of synonym groups. Words in the same group are interchangeable — the parser normalises them all to the first word in the group before storing the result. This means:

- A player typing `take sword using tongs` is treated the same as `take sword with tongs`
- `get_pobj_str("with")` and `get_pobj_str("using")` both work regardless of which word the player typed

The synonym groups are:

| Canonical (use in code) | Synonyms |
|-------------------------|----------|
| `with` | `using` |
| `at` | `to` |
| `in front of` | |
| `in` | `inside`, `into`, `within` |
| `on top of` | `on`, `onto`, `upon`, `above` |
| `out of` | `from inside`, `from` |
| `over` | |
| `through` | |
| `under` | `underneath`, `beneath`, `below` |
| `around` | `round` |
| `between` | `among` |
| `behind` | `past` |
| `beside` | `by`, `near`, `next to`, `along` |
| `for` | `about` |
| `is` | |
| `as` | |
| `off` | `off of` |

**Use the canonical (first) form** when calling parser methods or writing `--ispec` lines — this is the form stored in the parser after normalisation. All synonyms also work transparently if passed to `get_pobj_str`, `has_pobj_str`, `get_pobj`, or `has_pobj`.

The most common ones in default verbs are `in`, `on`, `with`, `at`, `from`, `to`.

## Multi-Preposition Verbs

```python
#!moo verb put --on $thing --dspec this --ispec on:any in:any

from moo.sdk import context

if context.parser.has_pobj_str("on"):
    container = context.parser.get_pobj("on")
elif context.parser.has_pobj_str("in"):
    container = context.parser.get_pobj("in")
else:
    print("Put it where?")
    return

if not this.moveto(container):
    print(f"You can't put {this.title()} there.")
```

## $do_command Hook

If the system object (#1) defines a verb named `do_command`, `interpret()` calls it before normal dispatch, passing the tokenised command words as positional `args`. The raw line is `context.parser.command`.

- Return a **truthy** value → command is fully handled; normal dispatch skipped.
- Return a **falsy** value (or verb absent) → parsing continues normally.

```python
#!moo verb do_command --on $system_object

# Log every command and let normal dispatch continue.
from moo.sdk import context

print(f"[log] {context.player.name}: {context.parser.command}")
return False
```

## Accessing Raw Words

`context.parser.words` gives the full command as a list, with `words[0]` being the verb name. This is useful for verbs that take a free-form string argument:

```python
#!moo verb say --on $room --dspec any

from moo.sdk import context

if context.parser.words:
    message = " ".join(context.parser.words[1:])
else:
    message = " ".join(str(a) for a in args)
```
