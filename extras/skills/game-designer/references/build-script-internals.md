# Build Script Internals

Implementation patterns inside `build_from_yaml.py`. Relevant when modifying or debugging the script itself, not when writing YAML environments.

## Object Creation

The script uses `@eval` with the SDK `create()` function rather than `@create`:

```python
def create(moo, name, parent="$thing"):
    """Create an object via @eval and return its #N reference."""
    escaped_name = name.replace('"', '\\"')
    escaped_parent = parent.replace('"', '\\"')
    output = moo.run(
        f'@eval "'
        f'obj = create(\\"{escaped_name}\\", '
        f'parents=[lookup(\\"{escaped_parent}\\")], '
        f'location=None); '
        f'print(f\\"Created {{obj}}\\"); '
        f'obj"'
    )
    match = re.search(r"(#\d+)", output)
    return match.group(1) if match else None
```

`@create` fails with `AmbiguousObjectError` when 3+ objects share a name because the parser resolves names *before* verb execution. `create()` from `moo.sdk` bypasses the parser entirely. `location=None` avoids race conditions with `enterfunc` and allows batch creation before placement.

## Moving Objects to Rooms

**Use direct location assignment, not `moveto()`.**

`$furniture` objects have a `moveto` verb that returns `False` to block player takes. This also blocks `moveto()` from admin build code — objects silently end up stranded in the void. The fix bypasses the verb system:

```python
def move_to_room(moo, obj_ref, room_name):
    obj_id = obj_ref.replace('#', '')
    escaped_room = room_name.replace('"', '\\"')
    moo.run(
        f'@eval "'
        f'obj = lookup({obj_id}); '
        f'room = lookup(\\"{escaped_room}\\"); '
        f'obj.location = room; obj.save()"'
    )
```

The `@move` command also won't work on objects in the void — it uses `context.parser` which only searches the local area.

## Adding Aliases

Use `@alias` (not `@eval`):

```python
def add_aliases(moo, obj_ref, aliases):
    for alias in aliases:
        escaped_alias = alias.replace('"', '\\"')
        moo.run(f'@alias {obj_ref} as "{escaped_alias}"')
```

`@alias` supports both `#N` and name strings with global lookup. Using it instead of `@eval` reduces alias commands by ~64% in verbose output.

## NPC Player Records

`@create "NPC" from "$player"` creates the MOO Object but not the Django `Player` model record. Without it, the NPC is missing messaging infrastructure (`tell`, routing, connection tracking).

```python
def create_player_record(moo, ref):
    obj_id_num = ref.replace("#", "")
    moo.run(
        f'@eval "from moo.core.models import Player; '
        f'obj = lookup({obj_id_num}); p = Player.objects.create(); p.avatar = obj; p.save()"'
    )
```

`moo.core.models` is in `WIZARD_ALLOWED_MODULES`. Call this immediately after `create()` returns a ref, before describing or aliasing. The build script does this automatically for all NPCs.

## Describing Objects

Descriptions require `\`, `\n`, and `"` all escaped before being sent over SSH. YAML block scalars (`|`) produce strings with literal newlines — unescaped newlines cause pexpect to split the command, sending a malformed first line and a bare `"` as the second.

```python
def describe(moo, ref, desc):
    # Escape backslashes first, then newlines, then double-quotes
    escaped_desc = desc.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
    moo.run(f'@describe {ref} as "{escaped_desc}"')
```

`at_describe.py` unescapes `\\n` back to real newlines before storing. Symptom of missing `\n` escape: `WARNING: could not get ID` for the object described immediately before the next `@create`.

## Verb Creation

```python
def set_verb(moo, verb_name, obj_ref, code):
    escaped = (code.replace("\\", "\\\\")
                   .replace("\n", "\\n")
                   .replace('"', '\\"'))
    if str(obj_ref).startswith("#"):
        moo.run(f'@edit verb {verb_name} on {obj_ref} with "{escaped}"')
    else:
        moo.run(f'@edit verb {verb_name} on "{obj_ref}" with "{escaped}"')
```

`at_edit.py` unescapes `\\n` back to real newlines before storing.

## RestrictedPython Constraint in Generated Code

Subscript augmented assignment is blocked at compile time and fails silently (`.code = None`):

```python
# FAILS — causes TypeError: exec() arg 1 must be a string, bytes or code object
results["passed"] += 1

# CORRECT
passed += 1
failed += 1
```

This applies to both the auto-generated test verb and any verb code blocks in the YAML.

## Output Capture

Two modes:

**Delimiter mode** (default after `enable_automation_mode()`): The server emits PREFIX before output and SUFFIX after. The client polls for SUFFIX and returns as soon as it's seen (~100ms after the Celery task completes), then waits a 1-second settle delay. Total: ~1.1s per command.

**Timeout fallback** (used for setup commands before delimiters are active): Polls the PTY buffer for ~7.5s. Used automatically when delimiters aren't yet configured.

```python
with MooSSH() as moo:
    moo.enable_automation_mode()  # enables delimiters + `a11y quiet on`
    output = moo.run("look")      # ~1.1s instead of ~7.5s
```

## Async Output and `.flush`

Commands like `@create` and `@describe` fire confunc/disfunc verbs in the background via Celery. These can produce `tell()` output that arrives between commands, appearing in the pre-PREFIX buffer of the next `run()` call. For most builds this is harmless (output outside the PREFIX/SUFFIX window is discarded).

`.flush` drains the Kombu message queue and writes any pending async output immediately:

```python
moo.run(".flush")       # drain async tells from previous commands
output = moo.run("look")
```

`build_from_yaml.py` does not call `.flush` automatically, but add it if a build produces inconsistent output due to slow background tasks.

## SSH Connection

```python
MooSSH(
    host="localhost",
    port=8022,
    user="phil",
    password="qw12er34",
    timeout=6  # applies to delimiter wait loop; setup commands use timeout fallback
)
```

Connects with `TERM=xterm-256-basic`, which puts the server in raw mode with IAC subnegotiation enabled. Raw mode's line-oriented shell loop does not issue CPR (Cursor Position Request) queries, eliminating the ~2-3s timeout per command that prompt_toolkit's rich-mode loop incurs. `disconnect()` sends `@quit` for a clean server-side disconnect — `QUIT` (legacy) only prints "please use @quit" and does not close the connection.
