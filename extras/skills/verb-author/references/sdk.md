# moo.sdk Reference

All public verb API is in `moo.sdk`. Only `moo.sdk`, `hashlib`, and `string` may be imported in verb code.

```python
from moo.sdk import context, lookup, create, invoke, write
from moo.sdk import NoSuchObjectError, NoSuchVerbError, NoSuchPropertyError, AmbiguousObjectError
```

## `context`

A read-only object exposing the current execution context. All attributes are read-only — attempting to set them raises `AttributeError`.

| Attribute | Type | Description |
|-----------|------|-------------|
| `context.caller` | Object | The object whose permissions are in effect (the verb's owner) |
| `context.player` | Object | The player who initiated the command session; use this for the "who typed this" identity |
| `context.parser` | Parser or None | Parser instance for the current task; inherited by synchronous sub-verb calls. `None` only when a Celery task re-invokes a verb outside any player command (e.g., scheduled `invoke()` calls) |
| `context.writer` | callable | Low-level write function for the current player's console |
| `context.task_id` | str | Celery task ID of the current execution |
| `context.task_time` | TaskTime or None | Timing info for the current task: `elapsed`, `time_limit`, `remaining` (all in seconds). `None` when no time limit is configured (e.g. in tests). |
| `context.caller_stack` | list | Stack of callers (for nested verb invocations) |

`context.player` is the right variable to use when you need to know who typed the command. `context.caller` reflects the verb's permission context and may differ when `set_task_perms` is used.

## `lookup(x)`

Find a game object globally.

```python
lookup(x: int | str) -> Object
```

- `lookup(1)` — returns the system object
- `lookup("Wizard")` — finds by name or alias (case-insensitive)
- `lookup("$thing")` — returns the value of property `thing` on the system object

Raises `NoSuchObjectError` if nothing matches. Never returns `None`.

## `create(name, *, parents=None, location=None, owner=None)`

Create and return a new Object.

```python
create("Widget", parents=[system.thing], location=t_wizard)
```

- `parents` defaults to `[system.root_class]` if omitted
- `location` defaults to the caller's location if omitted
- `owner` defaults to `context.caller` if omitted
- Calls the new object's `initialize` verb if one exists
- Decrements `ownership_quota` on the owner if it exists
- Raises `QuotaError` if the owner's quota is exhausted
- Raises `PermissionError` if the caller cannot `derive` from the parent

## `write(obj, message)`

Send a message directly to a player's console, bypassing the tell verb chain and all filtering.

```python
write(obj, "You have been teleported.")
```

- Only callable from wizard-owned verbs. Raises `UserError` otherwise.
- In tests (`CELERY_BROKER_URL = "memory://"`), emits `RuntimeWarning` instead of writing. Capture with `pytest.warns(RuntimeWarning)`.

For most cases, prefer `obj.tell(msg)` which goes through gag lists and paranoia filtering.

## `invoke(verb, *args, callback=None, delay=0, periodic=False, cron=None, **kwargs)`

Asynchronously execute a Verb in a separate Celery task with its own timeout.

```python
invoke("Task started.", verb=context.player.tell, delay=10)
invoke(verb=obj.some_verb, args=(arg1, arg2))
```

- `verb` — a Verb reference obtained via `obj.verb_name` attribute access
- `delay` — seconds to wait before executing (cannot combine with `cron`)
- `periodic=True` — repeat on the `delay` interval (wizard-owned verbs only)
- `cron` — crontab expression, e.g., `"0 * * * *"` (wizard-owned verbs only)
- `callback` — optional Verb to receive the result
- Returns a `PeriodicTask` instance for periodic/cron tasks, `None` for one-shots

Use `invoke` when a sub-verb would exceed the 3-second verb time limit, or when you want a delayed or recurring action.

### Scheduled-task lifecycle

`invoke(..., periodic=True)` creates a `django_celery_beat.PeriodicTask`
and returns its row. Two companion helpers manage that row from verb
code:

```python
from moo.sdk import cancel_scheduled_task, get_scheduled_task_info

# Inspect an existing PT (returns None if missing)
info = get_scheduled_task_info(pt_pk)
# {"enabled": True, "last_run_at": ..., "total_run_count": 12,
#  "interval_seconds": 60, "task": "moo.core.tasks.invoke_verb"}

# Cancel by PK (returns True if a row was deleted, False if not found)
cancel_scheduled_task(pt_pk)
```

Both helpers raise `UserError` when the current caller is not a wizard,
so a non-wizard verb should not call them directly — wrap with
`set_task_perms(this.owner)` if you need privileged behaviour. Used by
`$daemon.enable`/`disable`/`recycle` to manage their PTs.

### NPC `Player`-record helpers

When you create a `$npc` (or any `$player`-child object meant to be
parser-visible without a real `User`), an anonymous `Player` row needs
to exist so `is_player()` returns `True` while `is_connected()` stays
`False`:

```python
from moo.sdk import ensure_player_record, remove_player_record

# In an NPC's initialize verb:
ensure_player_record(this)

# In an NPC's recycle verb:
remove_player_record(this)
```

`ensure_player_record` is idempotent — calling it twice on the same
avatar returns the existing row. `remove_player_record` only deletes
rows with `user=None` (anonymous), so a row linked to a real Django
`User` is untouched.

### Discovering the typed verb name

```python
from moo.sdk import invoked_verb_name

name = invoked_verb_name(default=verb_name)
```

Returns the verb name as the player typed it (lowercased), or `default`
when there's no parser context (e.g. inside `invoke()` callbacks). The
sandbox-injected `verb_name` is the verb's *defined* name; pass it as
`default` so the helper falls back to it when the caller wasn't a player
command. Useful when a verb has multiple aliases and the body needs to
branch on which one the player invoked.

### Time-aware continuation pattern

For verbs that loop over many items, use `task_time_low()` and `schedule_continuation()` to hand off remaining work before the budget runs out:

```python
from moo.sdk import context, invoke, task_time_low, schedule_continuation

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

# Dispatch on verb_name — "my_batch" is the continuation alias
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

- `task_time_low(threshold=0.5)` — returns `True` when `remaining <= threshold`; returns `False` in tests (no limit). No manual guard needed.
- `schedule_continuation(remaining_items, verb, msg=None)` — extracts PKs, calls `invoke()`, tells the player. Replaces three-line inline boilerplate.
- Dispatch on `verb_name`, not `isinstance(args[0], list)` — more explicit and avoids confusion with other verbs that accept list args.
- Do NOT assign to `verb_name` anywhere in the verb body (see Pitfalls in SKILL.md).
- Helper function names must not start with `_` (RestrictedPython blocks them).
- Reference implementation: `moo/bootstrap/default/verbs/programmer/at_reload.py`

## `open_editor(obj, initial_content, callback_verb, *args, content_type="text")`

Open a full-screen text editor in the player's SSH terminal.

```python
open_editor(context.player, existing_text, obj.save_verb, content_type="python")
```

- `callback_verb` — Verb invoked with the saved text as `args[0]` followed by `*args`
- `content_type` — `"text"` (default), `"python"`, or `"json"` (controls syntax highlighting)
- Wizard-owned verbs only.

## `open_paginator(obj, content, content_type="text")`

Open a full-screen read-only paginator in the player's SSH terminal.

```python
open_paginator(context.player, long_text, content_type="python")
```

- Wizard-owned verbs only.

## `owned_objects(player_obj)`

Return a QuerySet of all Objects owned by `player_obj`, ordered by name.

```python
from moo.sdk import owned_objects

for obj in owned_objects(context.player):
    print(obj.title())
```

## `owned_objects_by_pks(pk_list)`

Return a QuerySet of Objects whose PKs are in `pk_list`, ordered by name.

Used in continuation verbs where the target player is not in scope but the
remaining PK list was passed as `args[0]`.

```python
from moo.sdk import owned_objects_by_pks

items = list(owned_objects_by_pks(args[0]))
```

## `task_time_low(threshold=0.5)`

Return `True` if the current task's remaining time is at or below `threshold`
seconds (default 0.5). Returns `False` when there is no configured time limit
(e.g. in tests).

```python
from moo.sdk import task_time_low

if task_time_low():
    # hand off remaining work
    ...
```

Replaces the manual `tt = context.task_time; if tt and tt.remaining is not None and tt.remaining <= 0.5` guard.

## `schedule_continuation(remaining_items, verb, msg=None)`

Schedule a continuation task with the PKs of `remaining_items` and notify the
current player.

```python
from moo.sdk import task_time_low, schedule_continuation

for i, item in enumerate(items):
    if task_time_low():
        schedule_continuation(items[i:], this.get_verb("my_batch"))
        return
    # process item
```

- `remaining_items` — iterable of Objects (or any model with `.pk`)
- `verb` — Verb instance to invoke for the continuation
- `msg` — optional override for the player notification message

The continuation verb receives `args[0]` as a list of integer PKs.

## `server_info()`

Return a dict with server version and process statistics.

```python
from moo.sdk import server_info

info = server_info()
# info["version"]   — e.g. "0.89.1"
# info["python"]    — Python version string
# info["pid"]       — process ID
# info["memory_mb"] — RSS memory in MB, or None if unavailable
```

Wizard-owned verbs only.

## `players()`

Return all player avatar Objects (connected or not).

```python
all_players = players()
```

## `connected_players(within=None)`

Return player avatar Objects whose `last_connected_time` was updated within the given window (default: 5 minutes).

```python
from datetime import timedelta
active = connected_players(within=timedelta(minutes=10))
```

## `set_task_perms(who)`

Context manager. Temporarily set the execution permissions to those of `who`.

```python
with set_task_perms(system):
    privileged_operation()
```

- Wizard-owned verbs only.

## `get_client_mode()`

Return `"rich"` (default, prompt_toolkit TUI) or `"raw"` (line-based I/O for MUD clients). Branch here to avoid opening full-screen TUIs on a client that cannot handle them.

```python
from moo.sdk import get_client_mode, open_editor

if get_client_mode() == "raw":
    print('Use: @edit description with "your text here"')
else:
    open_editor(context.player, existing_text, this.save_description)
```

## `get_wrap_column()`

Return the effective wrap width for the current player: their `wrap_column` property, or the session's `terminal_width` if set to `"auto"`, or 80 as final fallback.

```python
from moo.sdk import get_wrap_column
width = get_wrap_column()
```

## `get_session_setting(key, default=None)` / `set_session_setting(key, value)`

Read or write a per-session setting. Values cross the SSH-server / Celery-worker process boundary via the Django cache plus a `session_setting` Kombu event.

Known keys: `output_prefix`, `output_suffix`, `output_global_prefix`, `output_global_suffix`, `quiet_mode`, `osc133_mode`, `prefixes_mode`, `terminal_width`, `mode`.

```python
from moo.sdk import get_session_setting, set_session_setting

if get_session_setting("quiet_mode", False):
    print("terse mode on")

set_session_setting("output_prefix", ">>START<<")
```

All session settings clear automatically on disconnect.

## `boot_player(obj)`

Disconnect the given player. Publishes a `disconnect` event on the player's Kombu queue; the SSH server closes the channel. Only wizards can boot others; any player can boot themselves.

```python
from moo.sdk import boot_player, lookup
boot_player(lookup("Guest"))
```

## `send_gmcp(obj, module, data=None)` / `send_oob(obj, data)` / `play_sound(obj, name, volume=100, priority=10)`

Structured out-of-band channel for MUD clients. Emits GMCP / MSP frames to
the player's SSH channel when the connected client negotiated support for
the relevant option; silently no-ops otherwise, so adding these calls is
safe even when most users connect from plain SSH.

```python
from moo.sdk import send_gmcp, play_sound, lookup

# Update a Mudlet character panel after an HP change.
send_gmcp(player, "Char.Vitals", {"hp": 50, "maxhp": 100})

# Announce a room change so client-side maps can track the player.
send_gmcp(player, "Room.Info", {"num": room.pk, "name": room.name})

# Play a door-closing sound. Prefers GMCP Client.Media.Play; falls back to
# inline MSP !!SOUND(...) for clients that speak MSP but not GMCP.
play_sound(player, "door_close.wav", volume=70, priority=5)
```

`send_oob(obj, data)` is the low-level escape hatch — it publishes raw
pre-encoded IAC subnegotiation bytes. Use `send_gmcp` for normal GMCP
events; reach for `send_oob` only when you need a protocol the SDK does
not wrap.

All three are wizard-only (they share the same caller check as `write()`).
DjangoMOO does not bundle any sound assets; pack authors supply their own
filenames that the client can resolve.

## `PLACEMENT_PREPS` / `HIDDEN_PLACEMENT_PREPS`

Two constants for verbs that deal with spatial placement.

```python
from moo.sdk import PLACEMENT_PREPS, HIDDEN_PLACEMENT_PREPS
```

- `PLACEMENT_PREPS` — ordered list of all valid placement prepositions:
  `["on", "under", "behind", "before", "beside", "over"]`
- `HIDDEN_PLACEMENT_PREPS` — set of prepositions that hide the placed object from
  room listings and parser lookups: `{"under", "behind"}`

Use `PLACEMENT_PREPS` to iterate over supported prepositions in a verb rather than
hard-coding them:

```python
from moo.sdk import context, PLACEMENT_PREPS, UsageError

prep = None
for p in PLACEMENT_PREPS:
    if context.parser.has_pobj_str(p):
        prep = p
        break

if prep is None:
    raise UsageError(f"Usage: place <object> {'/'.join(PLACEMENT_PREPS)} <target>")
```

Object methods for placement (called on the placed object, not the target):

| Method | Description |
|--------|-------------|
| `obj.set_placement(prep, target)` | Set both fields atomically and save |
| `obj.clear_placement()` | Remove placement (sets both fields to null and saves) |
| `obj.is_placed()` | `True` if `placement_prep` and `placement_target` are set |
| `obj.is_hidden_placement()` | `True` if `placement_prep` is in `HIDDEN_PLACEMENT_PREPS` |
| `obj.placement` | Read-only property: `(prep, target)` tuple or `None` |

The `surface_types` property on the **target** restricts which prepositions are valid.
If not set, all `PLACEMENT_PREPS` values are accepted.

## Exceptions

All of these inherit from `UserError`. Any `UserError` (or subclass) raised inside a verb is automatically caught by the task runner and displayed to the player as a bold red message. Verbs do not need to wrap these in `try/except` just to report errors — raising them is the correct pattern.

For example, calling `context.parser.get_dobj()` when the player typed a non-existent object name will raise `NoSuchObjectError("widget")`, and the player will see: `There is no 'widget' here.`

All importable from `moo.sdk`:

| Exception | Message shown to player | When raised |
|-----------|------------------------|-------------|
| `NoSuchObjectError(name)` | `"There is no '<name>' here."` | `lookup()` finds nothing; `get_dobj()` / `get_pobj()` can't resolve |
| `NoSuchVerbError(name)` | `"I don't know how to do that."` | Verb not found on object or its parents |
| `NoSuchPropertyError(name)` | `"There is no '<name>' property defined."` | `get_property()` finds nothing |
| `AmbiguousObjectError(name, matches)` | `"When you say '<name>', do you mean …?"` | `lookup()` finds more than one match |
| `UsageError(message)` | The message string | Convenience for usage/validation errors |
| `QuotaError(message)` | The message string | Quota exceeded during `create()` |

`UsageError` is useful when a verb wants to exit cleanly with a usage message:

```python
from moo.sdk import UsageError

if not context.parser.has_dobj_str():
    raise UsageError("Usage: @create <name>")
```

Any other uncaught exception (not a `UserError`) shows `"An error occurred while executing the command."` to regular players, and a full traceback to wizards.

`NoSuchPropertyError` is also importable directly from `moo.core`:

```python
from moo.core import NoSuchPropertyError
```

## `$string_utils` Verbs

Two utility verbs live on the `$string_utils` object (accessed as `_.string_utils`).

### `rewrap(text)`

Reflows a block of text for terminal display.

```python
result = _.string_utils.rewrap(some_text)
```

- Normalizes line endings (`\r\n`, `\r` → `\n`)
- Collapses whitespace gremlins (tabs, non-breaking spaces) to single spaces
- Collapses runs of multiple spaces
- Splits on paragraph breaks (two or more newlines)
- Within each paragraph, collapses single newlines to spaces, then word-wraps to 80 characters
- Rejoins paragraphs with `\n\n`

`description` properties are passed through `rewrap` automatically before display (see `root_class/description.py`). You only need to call it manually when formatting multi-line text in other contexts.

### `pronoun_sub(text, who=None)`

Substitutes pronoun format codes in `text` using properties of `who` (defaults to `context.player`).

```python
result = _.string_utils.pronoun_sub("%N picks up %t.", actor)
```

| Code | Property | Default | Example |
|------|----------|---------|---------|
| `%%` | — | `%` | — |
| `%s` / `%S` | `who.ps` / `who.psc` | he/she/it | He |
| `%o` / `%O` | `who.po` / `who.poc` | him/her/it | Him |
| `%p` / `%P` | `who.pp` / `who.ppc` | his/her/its | His |
| `%r` / `%R` | `who.pr` / `who.prc` | himself/herself/itself | Himself |
| `%n` / `%N` | `who.name` | — | (capitalized for `%N`) |
| `%d` / `%D` | `dobj.name` (from parser) | unchanged | (capitalized for `%D`) |
| `%i(prep)` / `%I(prep)` | `pobj.name` for `prep` | unchanged | (capitalized for `%I`) |
| `%t` / `%T` | `parser.this.name` | unchanged | (capitalized for `%T`) |
| `%x(prop)` / `%X(prop)` | `who.prop` (any property) | unchanged | (capitalized for `%X`) |

Uppercase codes capitalize the result. Codes that require a parser context (`%d`, `%i`, `%t`) are left unchanged when `context.parser` is `None`.

`_msg` properties on `$furniture`, `$container`, `$thing`, and similar objects use these codes. Override them per-instance to customize flavor text.

## Connection and Movement Hooks

Override these verbs on `$room` or `$player` subclasses for custom behavior.

**Movement** (fired by `object.py` on every `moveto()`; `args[1]` = the moving object):

| Verb | `this` |
|------|--------|
| `$room:enterfunc` | destination room |
| `$room:exitfunc` | source room |

**Connection** (fired by `moo/shell/prompt.py` on SSH session start/end; no args):

| Verb | `this` | Call order |
|------|--------|-----------|
| `$player:confunc` | player | 1st on connect |
| `$room:confunc` | player's room | 2nd on connect |
| `$room:disfunc` | player's room | 1st on disconnect |
| `$player:disfunc` | player | 2nd on disconnect |

`context.player` is the connecting/disconnecting player in all four cases.
`$player:confunc` and `$player:disfunc` are no-op stubs — safe to override.

## Mail Functions

Available via `from moo.sdk import ...`. Use these for all mailbox operations
in player verbs. The underlying `Message` / `MessageRecipient` model objects are
not exposed to verb code.

```python
from moo.sdk import send_message, get_mailbox, get_message
from moo.sdk import mark_read, delete_message, undelete_message
from moo.sdk import count_unread, get_mail_stats
```

### `send_message(sender, recipients, subject, body)`

Create and deliver a message. Returns the `Message` instance (usually ignored).

- `sender` — sending Object (a player)
- `recipients` — list of recipient Objects (players)
- `subject` — subject line string
- `body` — message body string

### `get_mailbox(player, include_deleted=False)`

Return the player's received messages as a list of `MessageRecipient` objects,
newest first. `mr.message.sender` is pre-fetched — no extra query.

### `get_message(player, n)`

Return the nth message (1-based) from the player's non-deleted mailbox,
or `None` if `n` is out of range. Safe to call without bounds-checking.

### `mark_read(player, n)` / `delete_message(player, n)` / `undelete_message(player, n)`

Each returns `True` on success, `False` if `n` is out of range.

`delete_message` is a soft-delete (sets `deleted=True`). `undelete_message`
counts only among the deleted-only list (1-based within that list).

### `count_unread(player)`

Return the number of unread, non-deleted messages. Used in `confunc` to show
a login notification.

### `get_mail_stats(player)`

Return `{"total": int, "unread": int, "deleted": int}` in two queries.

### Patterns

**Login notification in `confunc`:**

```python
from moo.sdk import context, count_unread
unread = count_unread(context.player)
if unread:
    context.player.tell(f"You have {unread} unread message{'s' if unread != 1 else ''}. Type '@mail'.")
```

**Editor callback pattern (used by `@send`, `@reply`, `@forward`):**

```python
# Dispatcher verb: @send <player>
recipient = parse.get_dobj(lookup=True)
callback = context.player.get_verb("at_send_callback")
open_editor(context.player, "Subject: \n\n", callback, recipient.pk, content_type="text")

# Callback verb: at_send_callback (dispatched by verb_name)
text, recipient_pk = args[0], args[1]
lines = text.splitlines()
if lines and lines[0].lower().startswith("subject:"):
    subject = lines[0][8:].strip() or "(no subject)"
    body = "\n".join(lines[2:]).strip()
else:
    subject = "(no subject)"
    body = text.strip()
send_message(context.player, [lookup(recipient_pk)], subject, body)
```
