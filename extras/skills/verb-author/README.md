# verb-author

A Claude Code skill for writing, reviewing, and debugging verb files in the DjangoMOO project.

## When to use it

Invoke this skill when working on anything in `moo/bootstrap/default/verbs/` or any task involving:

- Creating or modifying verb files with the `#!moo` shebang syntax
- Debugging RestrictedPython sandbox errors
- Using the `moo.sdk` API (lookups, creates, invocations, exceptions)
- Writing or reading verb tests

## How to invoke

Claude Code picks this skill up automatically when the task matches the triggers above. You can also invoke it explicitly:

```
/verb-author write a take verb for $thing
/verb-author why is my verb silently doing nothing
```

## What it covers

The skill knows about:

- **Shebang syntax** — `--on`, `--dspec`, `--ispec` options and their interactions with the parser
- **Execution environment** — injected variables (`this`, `passthrough`, `_`, `args`, `kwargs`, `verb_name`), sandbox restrictions, allowed imports
- **Output mechanisms** — `print()`, `obj.tell()`, `write()`, and why `return "..."` is invisible to players
- **Object API** — property access, navigation, verb dispatch, room broadcasts
- **Parser methods** — `get_dobj()`, `get_dobj_str()`, `has_dobj_str()`, `get_pobj_str()`, etc.
- **Performance rules** — avoid redundant property lookups, pre-fetch querysets, pass cached values to sub-verbs
- **SDK functions** — `lookup()`, `create()`, `invoke()`, `open_editor()`, `open_paginator()`, `set_task_perms()`
- **Error handling** — `UserError` hierarchy, when to raise vs. catch
- **Time-aware continuation** — handing off long loops to fresh Celery tasks
- **Pitfalls** — common bugs that are easy to hit (wrong method names, augmented assignment in dicts, `this` vs `context.player`)

## Reference files

| File | Contents |
|------|----------|
| `references/sdk.md` | Full `moo.sdk` API including `$string_utils` verbs (`rewrap`, `pronoun_sub`) |
| `references/dispatch.md` | Verb search order; `this` vs `context.player` in depth |
| `references/parser-api.md` | Complete Parser method table and preposition synonym groups |
| `references/testing.md` | Test fixtures, helpers, and example tests |

## Verb files live here

`moo/bootstrap/default/verbs/` — organized by the object class the verb belongs to (`room/`, `thing/`, `player/`, `exit/`, `string_utils/`, etc.)

Tests live in `moo/bootstrap/default/verbs/tests/`.
