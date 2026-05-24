---
name: verb-author
description: Write and review DjangoMOO verb files. Use when asked to create, modify, or debug verbs in moo/bootstrap/default/verbs/ or for any task involving the `#!moo` shebang syntax, RestrictedPython verb execution, the moo.sdk API, or verb testing.
---

# Verb Author

This skill covers writing verb files for the DjangoMOO project.

## Shebang Syntax

Every verb file must start with a shebang line:

```
#!moo verb name1 [name2 ...] --on $object [--dspec SPEC] [--ispec PREP:SPEC ...]
```

**`name1 [name2 ...]`** — space-separated verb names (aliases). Example: `take get`

**`--on $object`** — the object to attach the verb to, using `$name` syntax to reference a property on the system object (#1). Common targets:

- `$root_class` — all objects
- `$room` — room commands
- `$player` — player commands
- `$thing` — generic thing
- `$exit` — exit objects
- `$container` — container objects

Although there hasn't been a need yet, you could also target arbitrary objects by name, e.g., `--on "magic wand"`. This is a global lookup, so it's important to ensure the name is unique and doesn't cause conflicts.

**`--dspec SPEC`** — direct object specifier:

- omitted — verb will not match if a dobj is typed
- `any` — verb requires a dobj string
- `this` — dobj must resolve to the object the verb is on
- `none` - (uncommon) dobj must not be provided, useful when a verb supports a preposition (e.g., `crawl --ispec under:any`), but not a direct object (e.g., `crawl` to crawl without a target)
- `either` — dobj is optional

**`--ispec PREP:SPEC`** — indirect object specifiers (repeatable). PREP is a preposition from `settings.PREPOSITIONS` (e.g., `in`, `on`, `with`, `at`, `from`, `to`). Use the **canonical** (first) form from each synonym group — see [parser-api.md](references/parser-api.md) for the full synonym table. SPEC is `any`, `this`, or `none`.

Prepositions within a synonym group are interchangeable: a verb defined with `--ispec with:any` will also match commands typed with `using`. Always use the canonical form in `--ispec` and in parser method calls; the parser normalises all synonyms to it automatically.

Indirect object specifiers can seem like they are optional, but they help the parser distinguish between different prepositions and ensure the correct parsing of commands.

### Parser Behavior and Quoted Arguments

The parser automatically scans for prepositions (from `settings.PREPOSITIONS`: `in`, `on`, `with`, `at`, `from`, `to`, `under`, `behind`, `through`, etc.) and splits commands at these boundaries. This means:

**If your verb needs arguments containing preposition keywords, you MUST use quoted strings:**

```python
# WRONG - parser splits at "from"
@eval from moo.sdk import lookup

# CORRECT - quotes protect the argument
@eval "from moo.sdk import lookup"
```

**Why this matters:**

- `@eval from moo.sdk import lookup` → Parser treats "from" as a preposition, creates pobj instead of dobj
- `@eval "from moo.sdk import lookup"` → Parser treats the whole thing as a single dobj string
- With `--dspec any`, the verb won't match without a dobj, so unquoted prepositions cause lookup failures

**Parser methods handle quoted strings correctly:**

- `parser.words` — tokenized list with quotes removed: `['@eval', 'from moo.sdk import lookup']`
- `parser.get_dobj_str()` — returns the dobj with quotes removed: `'from moo.sdk import lookup'`
- `parser.command` — raw command string: `'@eval "from moo.sdk import lookup"'`

Examples:

```python
#!moo verb accept --on $room
#!moo verb drop --on $thing --dspec this
#!moo verb look inspect --on $room --dspec either --ispec at:any
#!moo verb put give --on $thing --dspec this --ispec on:this in:this
#!moo verb page --on $player --dspec any --ispec with:any
```

## Execution Environment

Every verb file body is compiled as the body of this function — do **not** redeclare it:

```python
def verb(this, passthrough, _, *args, **kwargs):
    ...
```

Injected variables (always available, no import needed):

| Variable | Type | Meaning |
|----------|------|---------|
| `this` | Object | Object where verb was found (last match in dispatch order) |
| `passthrough` | callable | Invoke the verb on parent objects (`super()` equivalent) |
| `_` | Object | System object (#1) |
| `args` | tuple | Positional arguments when called as a method |
| `kwargs` | dict | Keyword arguments when called as a method |
| `verb_name` | str | The specific alias used to invoke this verb |

Include this pylint comment at the top of every verb file:

```python
# pylint: disable=return-outside-function,undefined-variable
```

### Sandbox Restrictions

Allowed imports: `moo.sdk`, `hashlib`, `re`, `datetime`, `time`, `random`

Allowed builtins: `dict`, `enumerate`, `getattr`, `hasattr`, `list`, `set`, `sorted`

Verbs cannot: import arbitrary modules, access the filesystem, open network connections, use `__import__`, `exec`, or `eval`.

**RestrictedPython Naming Restrictions:**

- Cannot use `eval` as a function name (it's blocked as the built-in)
- Cannot access dunder attributes: `obj.__class__`, `obj.__name__`, etc.
- `type()` builtin is not available
- Cannot use underscore-prefixed helper function names
- For error handling, use `str(exception)` instead of `exception.__class__.__name__`

## Output to Players

| Method | Who sees it | Notes |
|--------|-------------|-------|
| `print(msg)` | Caller only | Direct to initiator's console |
| `obj.tell(msg)` | `obj` | Goes through tell verb chain (gag/paranoia filtering) |
| `write(obj, msg)` | `obj` | Low-level, bypasses filtering; wizard-owned verbs only |

**`return "..."` does NOT display anything.** It merely returns the value to whatever called the verb. Always use `print()` or `write()` (or `obj.tell()`) for user-visible output.

## Object API Quick Reference

```python
# Properties
obj.get_property(name)    # raises NoSuchPropertyError if missing
obj.set_property(name, value)
obj.has_property(name)    # avoid — prefer try/except pattern below

# Prefer this pattern (1 query) over has+get (2 queries):
try:
    value = obj.get_property("key")
except NoSuchPropertyError:
    value = default

# Navigation
obj.location                             # ForeignKey to container
obj.contents.all()                       # direct contents QuerySet
obj.find(name)                           # find contents by name
obj.moveto(destination)                  # move object (triggers accept/enter/exit hooks)
obj.parents.all()                        # ManyToMany parents — always call .all()

# Identity
obj.title()                              # display name
obj.is_player()
obj.is_wizard()
obj.is_connected()

# Aliases
obj.add_alias(alias)                     # add an alias (handles duplicates)
obj.aliases.all()                        # QuerySet of ObjectAlias instances
obj.aliases.filter(alias="name").exists() # check if alias exists

# Verb dispatch
obj.invoke_verb(name, *args)             # works for any verb name, including hyphens
obj.has_verb(name)
# obj.foo_bar(...)                       # attribute-style only for valid Python identifiers
# obj.invoke_verb("foo-bar", ...)        # use invoke_verb for hyphenated/non-Python names

# Room broadcast
room.announce(msg)                       # all occupants except caller
room.announce_all(msg)                   # all occupants including caller
room.announce_all_but(obj, msg)          # all occupants except obj
```

## Performance Rules

1. Assign to a local when a property or method result is used more than once:

   ```python
   title = this.title()   # one query; reuse title below
   print(f"You take {title}.")
   ```

2. Use `try/except NoSuchPropertyError` instead of `has_property` + `get_property`:

   ```python
   try:
       free_entry = dest.get_property("free_entry")
   except NoSuchPropertyError:
       free_entry = False
   ```

3. Pre-fetch `contents.all()` before multiple announce calls:

   ```python
   source_contents = list(source.contents.all())
   dest_contents = list(dest.contents.all())
   source.announce_all_but(thing, msg, source_contents)
   dest.announce_all_but(thing, msg, dest_contents)
   ```

4. Sub-verbs that need the same properties (e.g., source/dest) should accept them as `args[0]`/`args[1]` with a `NoSuchPropertyError` fallback for standalone calls.

## SDK Functions for Privileged Operations

When a verb needs to access restricted functionality (compilation, wizard-only modules, etc.), create a function in the appropriate `moo/sdk/*.py` submodule (`output.py`, `objects.py`, `tasks.py`, `admin.py`, `mail.py`, `password.py`, `ssh_keys.py`) and re-export it from `moo/sdk/__init__.py`. Do not try to import from `moo.core.*` in verb code.

**Pattern for SDK functions:**

```python
# In moo/sdk/<submodule>.py
def privileged_operation(args):
    """Does something that requires restricted access."""
    from moo.core import restricted_module  # Import at function level

    # Privilege checks if needed
    if context.caller and not context.caller.is_wizard():
        raise UserError("Only wizards can...")

    # Do the privileged operation
    return restricted_module.do_thing(args)

# In verb file
from moo.sdk import privileged_operation
result = privileged_operation(data)
```

**Examples in the codebase:**

- `write(obj, msg)` — bypasses filtering, requires wizard permissions
- `open_editor(obj, ...)` — publishes editor events, requires wizard permissions
- `moo_eval(code)` — compiles and executes code in RestrictedPython sandbox

**Why this pattern:**

- SDK functions can import from `moo.core.*` modules
- Verbs can only import from `moo.sdk` and a few allowed modules
- Centralizes privilege checks and error handling
- Follows the same pattern as `write()`, `open_editor()`, `open_paginator()`

## Imports Reference

See [sdk.md](references/sdk.md) for the full `moo.sdk` API.

Common import lines:

```python
from moo.sdk import context
from moo.sdk import context, lookup, create, invoke, write
from moo.sdk import context, NoSuchPropertyError
from moo.sdk import NoSuchObjectError, NoSuchVerbError, NoSuchPropertyError
```

## Annotated Examples

### take.py — `--dspec this` verb

```python
#!moo verb take get --on $thing --dspec this

# pylint: disable=return-outside-function,undefined-variable

from moo.sdk import context

title = this.title()                        # cache — used 3+ times below
if this.location == context.player:
    print(f"You already have {title} in your inventory.")
elif this.moveto(context.player):           # moveto returns True on success
    print(this.take_succeeded_msg(title))
    if msg := this.otake_succeeded_msg(title):
        this.location.announce(msg)         # tell others in the room
else:
    print(this.take_failed_msg(title))
    if msg := this.otake_failed_msg(title):
        this.location.announce(msg)
```

Key points: `--dspec this` means the dobj must resolve to `this`. `context.player` is the initiator.

### look.py — optional dobj with preposition

```python
#!moo verb look inspect --on $room --dspec either --ispec at:any

# pylint: disable=return-outside-function,undefined-variable

from moo.sdk import context

if context.parser.has_pobj_str("in"):
    container = context.parser.get_pobj("in")   # returns Object
else:
    container = None

if context.parser.has_dobj() and container is None:
    obj = context.parser.get_dobj()
elif context.parser.has_dobj_str():
    dobj_str = context.parser.get_dobj_str()
    qs = context.player.find(dobj_str) or context.player.location.find(dobj_str)
    if not qs:
        print(f"There is no '{dobj_str}' here.")
        return
    obj = qs[0]
else:
    obj = context.player.location

obj.look_self()
```

Key points: `has_pobj_str` / `get_pobj_str` — not `…_string`. `get_pobj` returns an Object; `get_pobj_str` returns a raw string.

### exit/move.py — method verb with args

```python
#!moo verb move --on $exit

# pylint: disable=return-outside-function,undefined-variable,no-name-in-module

from moo.sdk import context, NoSuchPropertyError

thing = args[0]
source = this.get_property("source")
dest = this.get_property("dest")

try:
    free_entry = dest.get_property("free_entry")
except NoSuchPropertyError:
    free_entry = False

if free_entry:
    accepted = True
else:
    dest.bless_for_entry(context.caller)
    accepted = dest.accept(thing)

source_contents = list(source.contents.all())
dest_contents = list(dest.contents.all())

if accepted:
    thing.tell(this.leave_msg(source, dest))
    source.announce_all_but(thing, this.oleave_msg(source, dest), source_contents)
    thing.moveto(dest)
    thing.tell(this.arrive_msg(source, dest))
    dest.announce_all_but(thing, this.oarrive_msg(source, dest), dest_contents)
else:
    thing.tell(this.nogo_msg(source, dest))
    source.announce_all_but(thing, this.onogo_msg(source, dest), source_contents)
```

Key points: `args[0]` for the first method argument. `NoSuchPropertyError` import for optional property check. Pre-fetch contents once per room.

### @eval.py — REPL-like evaluation with quoted arguments

```python
#!moo verb @eval --on $programmer --dspec any

# pylint: disable=return-outside-function,undefined-variable

"""
Evaluate arbitrary Python code in the RestrictedPython sandbox.

Usage:
    @eval "<python-code>"

The code must be enclosed in quotes to avoid parser interference.
"""

from moo.sdk import moo_eval, context

# Get the dobj string (which should be the quoted code)
code_to_eval = context.parser.get_dobj_str()

# Execute the code with error handling
try:
    result = moo_eval(code_to_eval)
    # Print the result (REPL-like behavior)
    if result is not None:
        print(repr(result))
except Exception as e:
    # Just stringify - will include exception type automatically
    print(f"Error: {e}")
```

Key points:

- `--dspec any` required so verb matches when dobj present
- Quotes required to protect code from parser's preposition scanning
- Error handling catches all exceptions (can't use `e.__class__.__name__` in RestrictedPython)
- `moo_eval()` is an SDK function that handles compilation and execution
- Only prints non-None results (REPL-like behavior)
- All `moo.sdk` names (`lookup`, `create`, `context`, etc.) are pre-imported into `@eval`'s execution environment — no `from moo.sdk import ...` needed inside the evaluated code
- The `;` key in the interactive shell expands to `@eval` — useful for quick REPL-style testing

### @alias.py — global lookup with preposition

```python
#!moo verb @alias add --on $player --dspec any --ispec as:any

# pylint: disable=return-outside-function,undefined-variable

"""
Add an alias to an object.

Usage:
    @alias <object> as "<alias>"
    @alias #N as "alias"

The object can be specified by name (quoted if it contains spaces) or by
object ID (#N). Multiple aliases can be added to the same object by running
the command multiple times.

Examples:
    @alias "pool table" as "table"
    @alias #45 as "stool"
    @alias jukebox as "juke"

Permissions are enforced by the object model - you can only add aliases to
objects you own or have appropriate permissions for.
"""

from moo.sdk import context

# Get the target object (supports both names and #N IDs)
obj = context.parser.get_dobj(lookup=True)

# Get the alias string
alias = context.parser.get_pobj_str("as")

# Add the alias - permissions are checked by the object model
obj.add_alias(alias)

print(f"[yellow]Added alias '{alias}' to {obj}[/yellow]")
```

Key points:

- `get_dobj(lookup=True)` performs global lookup (not just local area)
- Supports both object names and `#N` object ID references
- `get_pobj_str("as")` extracts the string after the preposition
- Delegates permission checks to the object model (`add_alias()` method)
- Simple, focused verb that does one thing well

## Error Handling

`UserError` and all its subclasses (`NoSuchObjectError`, `NoSuchVerbError`, `NoSuchPropertyError`, `UsageError`, `QuotaError`, etc.) are automatically caught by the task runner and displayed to the player as a bold red message. Verbs do not need to catch these to report errors — raising them is the correct and idiomatic pattern.

Letting `get_dobj()` raise `NoSuchObjectError` is intentional: if the player typed a name that doesn't exist, they will see `"There is no 'X' here."` with no extra code in the verb.

Use `UsageError` to signal bad syntax or missing arguments:

```python
from moo.sdk import UsageError

if not context.parser.has_dobj_str():
    raise UsageError(f"Usage: {verb_name} <target>")
```

Only catch `UserError` subclasses when you need different behaviour from the default message:

```python
try:
    target = context.parser.get_dobj()
except NoSuchObjectError:
    print("You'll need to be more specific.")
    return
```

Any uncaught exception that is not a `UserError` shows a generic error to regular players and a full traceback to wizards.

## Time-Aware Continuation

Verbs that iterate over many objects must hand off remaining work before the task time limit hits. Use `task_time_low()` to check remaining time and `schedule_continuation()` to hand off, both from `moo.sdk`.

```python
from moo.sdk import context, task_time_low, schedule_continuation

def do_process_batch(items):
    count = 0
    for i, item in enumerate(items):
        if task_time_low():
            schedule_continuation(items[i:], this.get_verb("my_batch"))
            return True, count
        context.player.tell(f"  Processing {item}...")
        item.do_work()
        count += 1
    return False, count

# Detect continuation: args[0] is a list of PKs from a prior batch
if verb_name == "my_batch":
    items = list(MyModel.objects.filter(pk__in=args[0]))
    continued, count = do_process_batch(items)
    if not continued:
        context.player.tell(f"Done. Processed {count}.")
else:
    items = list(MyModel.objects.filter(...))
    continued, count = do_process_batch(items)
    if not continued:
        context.player.tell(f"Done. Processed {count}.")
```

Rules:

- `task_time_low(threshold=0.5)` returns `True` when `context.task_time.remaining <= threshold`. Returns `False` in test environments (no time limit). No manual guard needed.
- `schedule_continuation(remaining_items, verb, msg=None)` extracts PKs from the items, calls `invoke()`, and tells the player. Replaces the three-line inline boilerplate.
- Use a separate verb alias (e.g. `reload_batch`) as the continuation entry point, dispatched via `verb_name == "reload_batch"` at the top of the verb. Do NOT assign to `verb_name` anywhere in the verb body — see Pitfalls.
- Pass only `args[0] = list[int]` of remaining PKs to the continuation — no accumulated counts or error strings.
- Use `context.player.tell()` inside the loop, not `print()`. `tell()` writes immediately; `print()` buffers until the verb returns.
- Materialize querysets to `list()` before the loop so the DB cursor doesn't span the time check.
- Helper function names must not start with `_` — RestrictedPython blocks underscore-prefixed names.
- Reference implementation: `moo/bootstrap/default/verbs/programmer/at_reload.py`.

## Pitfalls

- `get_pobj_string()` / `has_pobj_string()` do not exist. Use `get_pobj_str()` / `has_pobj_str()`.
- `if player != this:` breaks on any verb with a dspec. `this` is the last matched object in dispatch order, not the caller. Use `context.player` for the initiator.
- `obj.parents` is a ManyRelatedManager. Always call `.all()` to iterate.
- `obj.aliases` is a RelatedManager. Check with `obj.aliases.filter(alias="name").exists()`, not `"name" in obj.aliases`.
- `has_property(x)` + `get_property(x)` is 2 queries. Use `try: get_property() except NoSuchPropertyError`.
- Verbs on `$player` with `--dspec any`: when dobj and caller both inherit the verb, the dobj wins — `this` = dobj, `context.player` = caller.
- **Parser preposition scanning:** Words like `from`, `to`, `with`, `in`, `on` are automatically treated as prepositions. Use quoted strings when these keywords appear in arguments: `@eval "from moo.sdk import lookup"` not `@eval from moo.sdk import lookup`.
- **`--dspec any` is required for verbs that need a dobj:** Without it, the verb won't match commands with direct objects. The verb will never be invoked if a dobj is typed.
- **`get_dobj()` vs `get_dobj(lookup=True)`:** By default, `get_dobj()` only searches the player's inventory and current room. Use `lookup=True` for global lookups (e.g., `@alias #45 as "thing"` needs global lookup to work with object IDs).
- **`eval` is a reserved name:** Can't name SDK functions or variables `eval` — RestrictedPython blocks it. Use alternatives like `moo_eval`.
- **Can't import from `moo.core.*` in verb code:** These modules aren't in `ALLOWED_MODULES`. Create SDK functions in the appropriate `moo/sdk/*.py` submodule and re-export from `moo/sdk/__init__.py` for privileged operations instead.
- **Exception handling limitations:** Can't use `e.__class__.__name__` or `type(e)` in verb error handlers. Use `str(e)` or just stringify: `print(f"Error: {e}")`.
- **`verb_name` shadowing causes `UnboundLocalError`:** `verb_name` is injected into the verb's local scope. If you assign to a variable named `verb_name` *anywhere* in the verb body (even after the first read), Python treats it as a local for the entire function — including lines before the assignment. Any read of `verb_name` before that assignment raises `UnboundLocalError`. Use a different name (e.g. `the_verb_name`, `current_verb`) for any local variable that would shadow it.
- **Hyphenated verb names need `invoke_verb`:** A verb declared `#!moo verb foo-bar --on $thing` is dispatchable via `obj.invoke_verb("foo-bar", *args)` but not `obj.foo_bar(*args)` — Python attribute access only resolves to the verb when the verb name is a valid Python identifier. Either keep verb names underscore-only or call them through `invoke_verb` from other verbs.
- **Parser dispatch (`parse.interpret`) requires the default LambdaCore verbs.** The parser calls `caller.set_parser(...)` and consults `do_command` on the system object — both ship in the `default` bootstrap. Datasets that don't pull `default` in cannot be tested with `parse.interpret`; call `obj.invoke_verb(...)` directly from the test instead.
- **Pre-declare locals that branch-bind.** When a verb assigns to a variable inside one branch of an `if/elif/else` and reads it later, pylint and the runtime will both flag uses-before-assignment. Set `var = None` (or a sensible default) at the top of the verb so every path has a binding.

## Patterns When Generating Verbs Programmatically

These notes apply when emitting verb files from another tool (transpilers,
scaffolders, code generators); they don't change anything for hand-authored
verbs.

- **Translate identifiers, don't echo them.** Atoms from the source language
  may contain characters Python disallows (`-`, `?`, `!`). Map `-` → `_`,
  predicate suffix `?` → `_p`, and reject leading digits. Suffix names that
  collide with Python keywords (`def`, `class`, `if`) or shadow common
  builtins (`set`, `list`, `dict`) so the generated body still calls
  `set()` etc. unambiguously.
- **Inline annotations break nested expressions.** Comments survive at the
  end of a complete statement but not inside an expression that may later
  be embedded in `if`, `and`, or function arguments. Emit `# ZIL:`-style
  trail comments on their own line before/after the statement, not inside
  the expression text.
- **Atoms used with attribute access need `lookup()`.** Source-language
  references like `THIEF` are usually object names. The translator must
  emit `lookup("thief")` when the atom appears as the operand of
  `.location`, `.set_property`, etc. — bare quoted atoms are str literals
  and `str.location` does not exist.
- **Implicit returns must become explicit.** Languages where the last
  expression of a block is the return value need explicit `return` in
  Python; otherwise pylint flags the trailing comparison/arithmetic as
  expression-not-assigned.
- **Skip empty event-handler clauses.** Don't register a verb file whose
  body is only `pass` — it adds dispatch cost and clutter without changing
  behaviour.
- **Pre-declare aux/local variables.** Emit `var = None` at the top of the
  body for every variable a branch can bind, so static analysis sees a
  consistent binding.

## Further Reference

- [dispatch.md](references/dispatch.md) — verb search order, `this` vs `context.player` in depth
- [parser-api.md](references/parser-api.md) — complete Parser method table
- [sdk.md](references/sdk.md) — full `moo.sdk` function reference
- [testing.md](references/testing.md) — test patterns, fixtures, and examples
