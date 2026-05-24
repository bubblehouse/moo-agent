# MOO Wizard Build Commands

## Room and Exit Commands

### `@dig`

```
@dig <direction> to "<room name>"
```

Creates a new room and a one-way exit from the current location in `<direction>`. The new room becomes accessible via that exit. Returns the name of the new exit object.

Example:

```
@dig north to "The Bar"
@dig south to "The Dartboard Corner"
```

### `@tunnel`

```
@tunnel <direction> to "<room name>"
```

Creates an exit from the current location to an *existing* room. Use this for reverse exits after `@dig`.

**Silent failure:** `@tunnel` checks whether an exit in the given direction already exists in the current room (`source.match_exit(direction)`). If one does, it prints a red error message and returns without creating anything. The build script does not inspect command output, so this failure is completely silent — the exit is simply absent with no warning.

This means:

- `@tunnel` must always be run from the intended source room (teleport first)
- The same `(room, direction)` pair must never be tunnelled twice — the second call is silently dropped
- Build scripts should track which `(room, direction)` pairs have been created and skip duplicates

Example:

```
# After digging north to "The Bar", go to The Bar and run:
@tunnel south to "The Main Room"
```

## Object Commands

### `@create`

```
@create "<name>" from "<parent>"
@create "<name>" from "<parent>" in "<room>"
@create "<name>" from "<parent>" in the void
```

Creates a new object instance with the given parent. By default places it in the **player's inventory**. Placement is done via ORM directly (bypassing `moveto` permission checks) so parents like `$note` and `$furniture` — which have restrictive `moveto` verbs — can be created without a `PermissionError`.

Use `in "<room>"` to create the object in a specific room. Use `in the void` to create an object with `location=None` (exists but isn't in any room). Useful for avoiding race conditions with `enterfunc` and for staging objects before placement.

Examples:

```
@create "Generic Tavern NPC" from "$player"
@create "Generic Beer Glass" from "$thing"
@create "Moe" from "Generic Tavern NPC"
@create "a pint of Duff" from "Generic Beer Glass"
@create "Moe's Tavern - Main Bar" from "$room" in the void
@create "welcome sign" from "$note"
```

**Parser Ambiguity Issue**: When creating the 3rd+ object with the same name, the parser raises `AmbiguousObjectError` because it tries to resolve the name string *before* running the verb. Use `@eval` with SDK `create()` to bypass parser resolution (see Advanced Techniques below).

### `@describe`

```
@describe "<object>" as "<text>"
@describe #N as "<text>"
```

Sets the description property. Use `here` for the current room.

When multiple objects share the same name, use the `#N` object ID reference (unquoted) to avoid `AmbiguousObjectError`. Capture `#N` from `@create` output (e.g. `Created #34 (bar stool)`).

Examples:

```
@describe here as "A dimly lit bar with sticky floors and neon signs."
@describe "Moe" as "A surly bartender with a perpetual scowl."
@describe #34 as "Wobbly bar stool with cracked red vinyl padding."
```

### `@move`

```
@move "<object>" to "<location>"
@move #N to "<location>"
@move "<object>" to #N
@move me to "<location>"
@move me to #N
```

Moves an object to a room or container. Use `#N` (unquoted) for either the object or the destination to avoid ambiguity and name spelling errors. Use `me` to teleport yourself directly to any room — by name or by ID.

Prints a confirmation line on success: `Moved <object> to <location>.` Use this to verify the move in build scripts.

Examples:

```
@move "Moe" to "Moe's Tavern"
@move "the jukebox" to "Moe's Tavern"
@move #34 to "Moe's Tavern - Main Bar"
@move #34 to #28
@move me to "The Laboratory"
@move me to #28
```

### `@gender`

```
@gender as <gender>
```

Sets the caller's own pronouns. Options: `male`, `female`, `neuter`, `either`, `royal`.

**Important**: `@gender` only modifies the player who runs the command (i.e., `context.player`). It cannot be used to set another object's gender. Attempting `@gender "Moe" as male` will set your own gender to `#N` (the object ID), not Moe's.

To set an NPC's gender, you must set the `gender` property directly on the object and also set the individual pronoun properties (`her`, `him`, `his`, `herself`, `himself`, `they`, etc.) — or use a wizard utility verb if one is available (e.g. `_.gender_utils.set(npc, gender)`).

Example (sets caller's gender):

```
@gender as male
```

### `@alias`

```
@alias "<object>" as "<alias>"
@alias #N as "<alias>"
```

Adds an alias to an object. Supports both object names and `#N` ID references with global lookup (can reference objects anywhere in the database).

Use `#N` (unquoted) when multiple objects share the same name to avoid `AmbiguousObjectError`. Permissions are enforced by the object model — you can only add aliases to objects you own or have appropriate permissions for.

Examples:

```
@alias "pool table" as "table"
@alias #34 as "stool"
@alias "jukebox" as "juke"
```

Multiple aliases can be added to the same object by running the command multiple times.

### `@obvious` / `@nonobvious`

```
@obvious "<object>"
@nonobvious "<object>"
```

Controls whether an object appears in the room contents listing when a player types `look`.
`obvious` is a model attribute — **do not use `@edit property obvious`**, it will have no effect.

```
@obvious "brass desk lamp"      — lamp now shows up in look output
@nonobvious "hidden lever"      — lever is invisible until interacted with directly
```

### `place`

```
place <object> on/under/behind/before/beside/over <target>
```

Positions `<object>` in a spatial relationship to `<target>` in the same room. Both
objects must be in the current room. The placed object stays in the room — placement
is stored as metadata (`placement_prep` + `placement_target`).

Visible prepositions (`on`, `before`, `beside`, `over`) group the object under its
surface in the room listing:

```
On the desk: a coffee cup.
```

Hidden prepositions (`under`, `behind`) suppress the object from all room listings
and make it unreachable by name in the parser. It can only be found with
`look under <target>` or `look behind <target>`.

Placement is cleared when the object is taken, dropped, or moved.

**Restricting valid prepositions on a surface:** Set the `surface_types` property on
the target to limit which prepositions are accepted. When absent, all six are valid:

```
@eval "lookup('writing desk').set_property('surface_types', ['on', 'beside'])"
```

Examples:

```
place book on desk
place key under rug
place coin behind painting
```

Only `obvious` objects are shown in the surface grouping — non-obvious placed objects
are invisible even with a visible preposition.

### `@lock`

```
@lock "<exit>" with <key-expression>
```

Locks an exit. The key expression is evaluated as a boolean.

Example:

```
@lock "the back door" with $wizard
```

## Property and Verb Editing

### `@edit verb`

```
@edit verb <name> on "<object>"
@edit verb <name> on #N
@edit verb <name> on "<object>" with "<code>"
@edit verb <name> on #N with "<code>"
```

Opens the verb editor for a named verb on an object, creating it if it doesn't exist. When multiple objects share the same name, use the `#N` form (unquoted).

The `with` form sets code inline without opening the editor. It supports multi-line code using `\n` escape sequences — the verb stores them as real newlines. Long verb bodies should use the interactive editor; the `with` form is most practical for one-liners or build-script automation where the code is passed as a pre-escaped string.

**Disambiguation**: `#N` refs are never quoted. Named refs are always quoted.

Examples:

```
@edit verb drink on "Generic Beer Glass"
@edit verb speak on "Moe" with "print('Moe grunts at you.')"
@edit verb drink on #43 with "print('You drink it.')\nthis.delete()"
```

### `@reload`

```
@reload <verb-name> on <object>
```

Reloads a bootstrap verb from its source file into the database. Necessary after a DB reset if the source file was changed since the last `moo_init`.

Example:

```
@reload @edit on $programmer
```

### `@edit property`

```
@edit property <name> on "<object>"
@edit property <name> on "<object>" with <json-value>
```

Opens the property editor, creating the property if it doesn't exist. The `with` form sets a JSON-encoded value inline.

Examples:

```
@edit property lines on "Moe" with ["Yeah?", "What'll it be?", "We're closing."]
@edit property full on "Generic Beer Glass" with true
@edit property brand on "Generic Beer Glass" with "Duff"
```

## Inspection Commands

### `@show`

```
@show "<object>"
```

Lists all verbs and properties defined directly on an object.

### `@messages`

```
@messages "<object>"
```

Lists all `_msg` properties (take/drop/look messages) on an object and its parents.

### `@eval`

```
@eval "<python-code>"
```

Evaluates Python code directly using the RestrictedPython sandbox. All `moo.sdk` exports are pre-imported — no import statement needed. Also has access to `this` (= `context.player`) and `_` (system object). `args` is not available. Useful for operations that don't have dedicated commands.

**Single-line only.** `@eval` does not support multi-line Python. Do not use `\n` in the code string — it is not processed as a newline and causes a `SyntaxError`. For multi-step inspection, use `SCRIPT:` with individual `@show` commands instead.

Examples:

```
@eval "print(context.player.location)"
@eval "obj = lookup('Moe'); print(obj.name)"
```

To inspect multiple rooms in sequence, use SCRIPT: with @show:

```
SCRIPT: @move me to "Room A" | @show here | @move me to "Room B" | @show here
```

### Test Verbs

```
test-<name>
```

Runs the environment verification verb. Must be placed on `$programmer`.

**Note**: Test verbs on `$programmer` are in-world verbs, not administrative commands. Invoke them **without** the `@` prefix. The `@` prefix is only for administrative/world-building commands like `@create`, `@edit`, `@describe`.

## Advanced Techniques

### Creating Objects with @eval (Bypassing Parser Ambiguity)

When creating 3+ objects with the same name, `@create` fails with `AmbiguousObjectError` because the parser resolves names *before* the verb runs. Use `@eval` with the SDK `create()` function instead:

```
@eval "obj = create(\"bar stool\", parents=[lookup(\"$thing\")], location=None); print(f\"Created {obj}\"); obj"
```

This bypasses parser name resolution and always succeeds. The `location=None` parameter avoids race conditions with `enterfunc`. Capture the returned `#N` object ID from the output (e.g., `Created #45 (bar stool)`).

### Moving Objects from the Void

Objects created with `location=None` exist in the void and won't appear in any room. Move them using `moveto()`:

```
@eval "lookup(45).moveto(lookup(\"Moe's Tavern - Main Bar\"))"
```

The `@move` command won't work on objects in the void because it tries to look them up via `context.parser`, which only searches the local area.

### Adding Aliases

Use the `@alias` command (see Object Commands section above):

```
@alias #45 as "stool"
@alias "pool table" as "table"
```

For programmatic access in build scripts, you can also use `@eval`:

```
@eval "lookup(45).add_alias('stool')"
```

### Setting Player Location Directly

When creating rooms in the void, you can't navigate to them with normal movement commands. Use `@move me to`:

```
@move me to "Moe's Tavern - Main Bar"
```

This works for any room in the database, not just rooms reachable by exits. It is the preferred approach — cleaner than `@eval` and no `.save()` required.

If the room was just created in the void and `@move` can't find it by name (e.g., due to hash suffix ambiguity), fall back to `@eval`:

```
@eval "context.player.location = lookup(\"Moe's Tavern - Main Bar\"); context.player.save()"
```

Must call `.save()` after setting `.location` because it's a Django model field.

## Session Commands

### `@quit`

```
@quit
```

Disconnects from the MOO server cleanly. Prints a goodbye message and closes the SSH session. This is the canonical way to exit.

### `QUIT`

```
QUIT
```

Legacy disconnect command. If the current room defines a `QUIT` verb (e.g., inside an editor), it is called instead. Otherwise prints a message redirecting to `@quit`. Use `@quit` in automation scripts.

## Agent-Optimized Navigation Verbs

These verbs replace multi-step navigation patterns with single atomic operations. They are primarily designed for autonomous agents but work for any `$player`.

### `@burrow`

```
@burrow <direction> to "<room name>"
```

Atomic bidirectional dig. In one command: creates the forward exit, creates the new room, moves the caller into it, and wires the return exit automatically (using the opposite direction). Replaces the three-step `@dig` + `go` + `@tunnel` sequence and eliminates the most common source of one-way exits.

The return direction is inferred automatically (`north` ↔ `south`, `east` ↔ `west`, `up` ↔ `down`, diagonal pairs). For non-standard directions with no obvious opposite, the return exit is skipped with a warning.

**Check before digging:** `@burrow` returns an error if an exit already exists in the given direction. Use `@survey` or `@exits` first to see which directions are taken.

Examples:

```
@burrow north to "The Watchtower"
@burrow east to "The Cloister"
```

### `teleport`

```
teleport #N
teleport "<room name>"
```

Teleport directly to any room by object ID or name without following exit chains. Replaces `go north | go east | go south` navigation chains with a single command.

Examples:

```
teleport #32
teleport "The Grand Gallery"
```

### `@survey`

```
@survey
@survey here
@survey #N
```

Lightweight room inspector. Returns only the room name, exits with `#N` destination IDs, and a flat contents list (~5 lines). Use instead of `@show here` to avoid context overload in long sessions or automation scripts.

Examples:

```
@survey           ← current room
@survey here      ← same as above
@survey #35       ← survey a specific room by ID
```

### `@rooms`

```
@rooms
```

Lists every room instance in the world as a flat `#N / name` list. Useful for building a traversal plan at the start of a session. Filters out abstract class objects and returns only actual room instances.

## NPC and Daemon Commands

These wizard commands wrap the `$npc`/`$daemon` lifecycle so you don't have to drive `@create` + `ensure_player_record` + `enable` by hand.

### `@npc create`

```
@npc create <name>
@npc create <name> from $wanderer
@npc create <name> from "Generic Bartender"
```

Synchronously creates an NPC in the current room and assigns a `Player` record so `is_player()` returns `True` immediately. Default parent is `$npc`; `from <parent>` accepts any `$npc` descendant. The NPC is *not* enabled (no scheduled ticks) — run `@daemon enable <name>` next.

### `@npc destinations`

```
@npc destinations <name>
@npc destinations <name> #N #M #P
```

With no PK list, prints the `wander_rooms` setting on a `$wanderer` (silently a no-op if the destination list is empty). With a list of room PKs, replaces `wander_rooms`. PKs may be bare numbers or `#N`-style.

### `@daemon list`

```
@daemon list
```

Prints every `$daemon` descendant (including `$npc` instances) in a table: PK, name, interval, tick count, last tick time, target, status (`enabled` / `disabled` / `off` / `orphan`).

### `@daemon enable`, `@daemon disable`, `@daemon trigger`, `@daemon kill`

```
@daemon enable <name|#N>
@daemon disable <name|#N>
@daemon trigger <name|#N>
@daemon kill <name|#N>
```

- `enable` schedules the daemon (creates a `django_celery_beat.PeriodicTask`)
- `disable` cancels the scheduled task (no-op if not enabled)
- `trigger` fires `tick()` once synchronously — bypasses the schedule, useful for verifying a new `on_tick` override
- `kill` calls `disable()` then `delete()` — the inherited `$daemon.recycle` also calls `disable`, so direct `@recycle` works too

Each command needs the daemon's name or `#N`. Names are unique per object so this matches the canonical name from `@daemon list`.

## Navigation Tip

After `@dig`, you remain in the original room. Use `go <direction>` to enter the new room, then `@tunnel` to add the return exit.

For agent sessions, prefer `@burrow` — it combines all three steps into one command and moves you into the new room automatically. Call `@describe here` immediately after `@burrow` without any additional navigation step.
