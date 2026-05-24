---
name: game-designer
description: Design and build themed multi-room environments in DjangoMOO via SSH wizard commands. Triggered by: "build a MOO environment", "create rooms for X", "design a location based on Y", "add NPCs for Z", "write a test verb for", "set up a MOO area", "implement a themed space in MOO".
compatibility: DjangoMOO project (django-moo). Requires a wizard SSH session.
---

# Game Designer Skill

You are designing and building a themed multi-room environment in DjangoMOO. Follow this 5-phase workflow.

## Phase 1: Research

Before writing any commands, research the theme thoroughly:

- Physical layout: How many rooms? What are their names and spatial relationships?
- Objects: What items are present? Which are interactive vs. decorative?
- Characters: Who lives here? What do they say or do?
- Signature interactions: What verbs make this space feel alive? (sit, drink, order, throw, play)
- Atmosphere: What descriptions capture the feel of each room?

Use web research for real-world locations. Aim for specificity — generic descriptions produce generic spaces.

### Native commands vs. YAML build

The default bootstrap now ships native wizard commands that cover the
common build motions: `@dig` / `@tunnel` / `@burrow` for rooms and exits,
`@create` / `@describe` / `@alias` / `@obvious` for objects, and
`@npc` / `@daemon` for autonomous actors. For *interactive* sessions —
prototyping a single room, dropping an NPC in, sketching a corridor — go
straight to those commands; you'll see each result immediately and can
adjust as you go.

For *batched, repeatable* builds — a multi-room area you want to be
able to rebuild from scratch — the YAML build pipeline below is still
the right tool. The YAML captures the design as a single artifact,
makes review/diffs possible, and runs deterministically against any
fresh world.

Rule of thumb: if you'd write a doc to remember what you built, write
the YAML. If you're iterating on shape, use the native commands and
freeze the YAML at the end.

## Phase 2: Design - Generate YAML Environment File

### Single-file vs. directory layout

Small environments (≤10 rooms, ≤30 objects) can live in a single YAML file:

```
extras/skills/game-designer/environments/<name>.yaml
```

Larger environments should be split into a directory of section files. The build script detects directories automatically and merges all `*.yaml` files found inside:

```
extras/skills/game-designer/environments/<name>/
  metadata.yaml   # name, version, hash setting, parent defaults
  rooms.yaml      # room definitions + exits
  objects.yaml    # objects keyed by room name
  npcs.yaml       # NPC definitions
  verbs.yaml      # verb definitions with code blocks
```

Each section file uses the same top-level keys as the single-file format. Since the keys are distinct (`metadata`, `rooms`, `objects`, `npcs`, `verbs`), the files merge without conflicts.

### YAML structure

```yaml
metadata:
  name: "Environment Name"
  description: "Brief description"
  author: "game-designer"
  version: "1.0"
  base_parent: "$thing"    # Default parent for objects
  npc_parent: "$player"    # Default parent for NPCs
  use_hash_suffix: true    # Enable hash suffixes for testing

rooms:
  - name: "Room Name __hash_suffix__"
    description: "Detailed room description..."
    exits:
      - direction: north
        to: "Other Room"       # Clean name — no __hash_suffix__ in exits
      - direction: south
        to: "External Room"    # Exits to rooms outside this environment also use clean names

objects:
  "Room Name":                 # Section key is clean room name — no __hash_suffix__
    - name: "object name __hash_suffix__"
      description: "Object description..."
      aliases: ["alias1", "alias2"]
      obvious: true            # Appears in room listing when players look (default: false)
      quantity: 4              # Create 4 identical objects

npcs:
  - name: "NPC Name __hash_suffix__"
    description: "NPC description..."
    aliases: ["alias"]
    room: "Room Name"          # Clean name — no __hash_suffix__ in room references

verbs:
  - verb: "verb_name"
    object: "object name __hash_suffix__"   # Has __hash_suffix__ for test verb lookup
    room: "Room Name"                        # Clean name — no __hash_suffix__
    code: |
      #!moo verb verb_name alias --on "object name __hash_suffix__" --dspec either
      from moo.sdk import context, lookup, NoSuchObjectError
      target = lookup("Target Room __hash_suffix__")   # lookup() calls use __hash_suffix__
      context.player.moveto(target)
```

### The `__hash_suffix__` placeholder system

In hash mode (`use_hash_suffix: true`), the build script generates a unique 6-character hash per run (e.g., `[1e8372]`) and substitutes it for `__hash_suffix__` everywhere. This lets you rebuild repeatedly without name collisions.

**Where to use `__hash_suffix__`:**

- Room `name:` fields — the names sent to `@create`
- Object `name:` fields — the names sent to `@create`
- NPC `name:` fields — the names sent to `@create`
- Verb `object:` fields — so the test verb can look up the hashed object
- `lookup()` calls inside verb code — build script replaces before sending via `@edit`
- The `--on "..."` argument inside verb shebang lines

**Where NOT to use `__hash_suffix__` (internal YAML references):**

- Exit `to:` fields
- NPC `room:` fields
- Verb `room:` fields
- Object section dict keys (the room-name keys under `objects:`)

The `room_map`, `obj_refs`, and `npc_refs` dictionaries inside the build script are all keyed by clean (stripped) names, so internal references resolve correctly regardless of hash mode.

**Clean-name aliases:** In hash mode, the build script automatically adds the clean (unhashed) name as an alias to every room, object, and NPC it creates. So `lookup("Room Name")` works alongside `lookup("Room Name [1e8372]")`, and players can refer to objects by plain names in-game.

**Hash mode usage:**

- `use_hash_suffix: true` — development mode, allows repeated builds without cleanup
- `use_hash_suffix: false` — production mode, clean names
- `--hash` / `--no-hash` CLI flags override the YAML setting

### Verb shebang syntax

Every verb code block must start with a shebang line that registers the verb:

```python
#!moo verb verb_name1 [verb_name2 ...] --on "Object Name __hash_suffix__" [--dspec SPEC] [--ispec PREP:SPEC ...]
```

**Multiple verb names:** Space-separated. All names are registered as aliases for the same verb:

```python
#!moo verb talk speak --on "Professor Farnsworth __hash_suffix__" --dspec either --ispec to:any
#!moo verb punch kick hit --on "punching bag __hash_suffix__" --dspec either --ispec at:this
#!moo verb enter board --on "Planet Express Ship __hash_suffix__" --dspec either
```

**`--dspec` values:**

- `--dspec this` — verb only matches when the object it's on is the direct object (`verb object`)
- `--dspec any` — verb matches any direct object
- `--dspec either` — direct object is optional; supports both `verb object` and `verb prep object` forms
- omit — verb takes no direct object

**`--ispec PREP:SPEC`** — indirect object via preposition. `SPEC` is `this`, `any`, or `none`:

- `--ispec to:any` — matches `talk to Farnsworth` (iobj can be anything)
- `--ispec on:this` — matches `sit on couch` (iobj must be the object the verb is on)
- `--ispec into:any` — matches `crawl into dumpster`
- `--ispec from:this` — matches `drink from machine`
- `--ispec through:any` — matches `peer through scope`
- `--ispec at:this` — matches `punch at bag`

Use `--dspec either` with `--ispec` to support both `verb object` and `verb prep object` in a single verb. The verb code doesn't need to branch — `this` is set to the matched object in both dispatch paths.

**Hidden room access pattern:** Place a movement verb on a physical object in a room. The verb calls `context.player.moveto(lookup("Hidden Room __hash_suffix__"))`. The hidden room needs a normal directional exit back.

```python
#!moo verb pull yank --on "laboratory bookcase __hash_suffix__" --dspec this
from moo.sdk import context, lookup, NoSuchObjectError
print("The bookcase swings outward on hidden hinges...")
try:
    context.player.moveto(lookup("Secret Sub-Lab __hash_suffix__"))
except NoSuchObjectError:
    print("The passage appears to be sealed.")
```

### Object visibility

**For each object, decide: `obvious: true` or `obvious: false`?**

- `obvious: true` — appears in the room listing when players `look`. Use for dominant furniture, interactive focal points, major props, anything a person would immediately notice walking in.
- `obvious: false` (default) — hidden from the listing, discovered by examining other objects or through narrative hints.

Objects marked `obvious: true` should be mentioned in the room description. Room descriptions should orient and evoke, not enumerate — the `obvious` listing handles inventory.

When creating descriptions, review `references/room-description-principles.md`. Key principle: room descriptions should be atmospheric, not inventories.

## Phase 3: Review YAML (User Approval Required)

After generating the YAML file or directory:

1. **Show the path** to the user: `extras/skills/game-designer/environments/<name>/` or `<name>.yaml`
2. **Summarize what will be created**:
   - X rooms with Y exits (note any hidden/restricted rooms)
   - Z objects across N rooms
   - M NPCs
   - P interactive verbs
3. **Ask the user to review** the YAML
4. **Wait for explicit approval** before proceeding to Phase 4
5. **Allow edits**: User can manually edit the YAML if needed
6. **Run `--dry-run`** to confirm counts before presenting the summary

**Do not proceed to Phase 4 until the user approves.**

## Phase 4: Build - Invoke Build Script

After user approval, execute the build script **in the background** — builds take 3-4 minutes and must not block the conversation:

```bash
python extras/skills/game-designer/tools/build_from_yaml.py \
    extras/skills/game-designer/environments/<name>/ \
    > /tmp/<name>-build.log 2>&1
```

The script accepts either a file path or a directory path.

**Options:**

- `--dry-run`: Parse YAML without connecting to MOO
- `--no-test`: Skip test verb creation
- `--hash`: Force hash suffix mode (override YAML setting)
- `--no-hash`: Force clean name mode (override YAML setting)
- `--host HOST --port PORT`: Custom SSH connection

**For local development**, a DB refresh and server restart before each build ensures a clean state. For production deploys, just run the build against the live server. If the server is unresponsive mid-build, you can restart it yourself with `docker compose restart webapp celery` — but tell the user first.

**Build process:**

1. **Phase 1: Rooms and exits** — Creates all rooms in the void, then DFS-traverses the exit graph from the first room: teleports to each room via `@move me to "<room>"`, describes it, wires all its exits, then recurses into unvisited neighbors. A `created_exits` set tracks `(room, direction)` pairs to detect and skip duplicates (which would otherwise fail silently inside `@tunnel`). Rooms unreachable from the first room are warned about and still built.
2. **Phase 2: Objects** — Creates objects in void, describes, adds aliases (including clean-name alias in hash mode), moves to rooms
3. **Phase 3: NPCs** — Creates NPCs, creates a Django `Player` record (no User) for each via `Player.objects.create()`, describes, adds aliases (including clean-name alias in hash mode), moves to rooms
4. **Phase 4: Verbs** — Applies `__hash_suffix__` substitution to verb code, attaches verbs to objects/NPCs using resolved references
5. **Phase 5: Test verb** — Generates test code, places on `$programmer`, runs verification

**Do not use `@reload`** — it creates duplicate verbs on a freshly-bootstrapped DB. The user handles verb state by refreshing the DB before each build.

**Build time**: ~3-4 minutes for typical environments (5 rooms, 30+ objects). Each command takes ~1.1s (automation mode: PREFIX/SUFFIX delimiters + `a11y quiet on`).

**Monitor the log** for errors. Watch for `WARNING: Could not resolve object` (verb attachment failure) and tracebacks.

## Phase 5: Verify - Auto-Generated Test Verb

The test verb is automatically generated and run by `build_from_yaml.py`.

**Test verb name:**

- With hash: `test-<env-name>-<hash>` (e.g., `test-planet-express-1e8372`)
- Without hash: `test-<env-name>` (e.g., `test-planet-express`)

The test verb name is printed at the end of build output. If the SSH connection drops while the test verb is running, the build still succeeded — run the test verb manually in-world.

**Test verb verifies:**

- All rooms exist and are accessible (looked up by hashed name)
- All objects are in correct rooms
- All NPCs are present (looked up by hashed name)
- All verbs are attached to correct objects

**Manual re-run:**

```
test-<env-name>-<hash>
```

## Best Practices & Tips

### YAML Authoring

1. **Use directory layout for large environments**: Split rooms/objects/npcs/verbs into separate files when the environment is large enough that scrolling becomes painful. Planet Express (26 rooms, 76 objects) is the threshold — use a directory.
2. **Use `quantity` for duplicates**: `quantity: 4` creates multiple identical objects without repeating the definition.
3. **`__hash_suffix__` placement**: Add to all `name:` fields that get created in MOO, and to all `lookup()` calls and shebang `--on` arguments in verb code. Leave internal references (exits, room refs, section keys) clean.
4. **Mark obvious objects explicitly**: Every object that should appear in the room listing needs `obvious: true`. Think: what would someone notice immediately walking in?
5. **Write descriptions for atmosphere, not inventory**: `obvious` objects appear in the room listing automatically. Room descriptions should orient and evoke, not enumerate.
6. **Break descriptions into paragraphs**: Use `\n\n` (blank line in YAML block scalars) to split descriptions by topic. One paragraph per idea — overall atmosphere, focal object, secondary details. A single long block of text is hard to read. This applies to room descriptions, object descriptions, and `$note` text equally.
7. **Comment liberally**: YAML supports comments — explain non-obvious design decisions.

### Choosing a Parent Class

- `$thing` — portable props with no special behavior (decorative items, tools, sealed objects)
- `$container` — anything that opens, closes, and holds objects (chests, cabinets, safes, bags). Add a `moveto` verb returning `False` to keep it fixed in place — you keep all the open/close behavior
- `$furniture` — anything players sit on (chairs, benches, couches). Immovable by default. Do not use for containers
- `$note` — anything with readable text (signs, menus, letters, plaques, books, bulletin boards). Add a `moveto` verb returning `False` for fixed signs
- `$player` — NPCs with dialogue but no scheduled behaviour
- `$daemon` — invisible scheduled actors (a chime that fires on the hour, a restocker that refills inventory every five minutes). Override `on_tick` to define the per-cycle behaviour
- `$npc` — multi-parent of `$player` + `$daemon`: parser-visible AND scheduled. Override `act` to define the per-tick personality (move, speak, attack, idle)
- `$wanderer` — `$npc` subclass that already moves between rooms each tick. Set `wander_rooms` to a list of room PKs and the inherited `act` does the rest

When in doubt between `$thing` and `$container`: if a player might ever want to put something inside it or take something out, use `$container`. When in doubt between `$thing` and `$note`: if there's text a player would want to read, use `$note`. When in doubt between `$player` and `$npc`: if the character should *do* something on its own (move, speak periodically), use `$npc`; if it's a quiet presence that only reacts to player commands, plain `$player` is enough.

### Signs and Room Descriptions

When a room has a sign, plaque, menu, or other readable object, put its text in the `$note`'s `text` property — not in the room description. The room description should only say the sign is there. Players read it themselves.

The exception is when the text is essential to understanding the space (a single carved word, a room name, a critical warning) — in that case it can appear in the description. When uncertain, default to `$note`.

Give every `$note` object specific aliases so `read sign` is never ambiguous. Include the generic type word (`sign`, `menu`, `letter`) and at least one more specific alias (`chalkboard`, `notice`, `plaque`).

### Verb Design

1. **Support both `verb obj` and `verb prep obj`**: Use `--dspec either --ispec PREP:any` to handle both forms with one verb. No branching needed in the code — `this` is set correctly in both cases.
2. **Multiple verb names**: Space-separate them in the shebang: `talk speak` registers both `talk` and `speak`.
3. **Hidden rooms**: Place a movement verb on a physical object. The verb calls `context.player.moveto(lookup("Hidden Room __hash_suffix__"))`. The hidden room should have a normal exit back.
4. **Preposition choices**: Use prepositions players will naturally type — `to:any` for talking, `on:this` for sitting, `into:any` for entering containers, `from:this` for taking/drinking, `at:this` for attacking.
5. **Stateful verbs**: Use `this.get_property()` / `this.set_property()` with a `NoSuchPropertyError` fallback to track object state between uses (e.g., sit/stand toggle, Slurm consumption counter).

### Build Process

1. **Always run `--dry-run` first**: Validate YAML syntax and confirm counts before committing to a 3-4 minute build.
2. **Local development**: DB refresh + server restart before each build keeps state clean.
3. **One build at a time**: Don't run multiple builds simultaneously — the Wizard moves between rooms.
4. **Run in background**: Redirect to a log file and monitor it every 90 seconds.
5. **Do not use `@reload`**: Creates duplicate verbs — user manages verb state via DB refresh.

### Multiline Descriptions

YAML block scalars (`|` or `>`) work correctly. The `describe()` function escapes `\n` as `\\n` before sending via SSH, and `at_describe.py` unescapes when storing. Write descriptions as block scalars freely.

Use blank lines between paragraphs to create `\n\n` breaks in the stored text. Split by topic — one idea per paragraph. A single wall of text is hard to read in-game. Aim for 2–3 short paragraphs for room descriptions; 1–2 for object descriptions. The same applies to `$note` text properties.

### RestrictedPython Gotchas in Verb Code

Subscript augmented assignment is blocked inside the sandbox:

```python
# BLOCKED — silent RestrictedPython compilation failure
results["passed"] += 1

# CORRECT — use plain variables
passed += 1
failed += 1
```

If a verb silently fails with `TypeError: exec() arg 1 must be a string, bytes or code object`, it means RestrictedPython couldn't compile it. Check for `dict["key"] += value` patterns.

### Performance

- Each SSH command takes ~1.1s (0.1s execution + 1s settle delay)
- 26-room environment with 76 objects, 8 NPCs, 20 verbs: ~3-4 minutes
- Hash mode adds minimal overhead (suffix generation is fast)

### Troubleshooting

- **`WARNING: Could not resolve object '...' for verb '...'`**: The verb's `object:` or `room:` doesn't match any entry in `obj_refs` or `npc_refs`. Check spelling and that the room key in `objects:` matches the verb's `room:` field exactly.
- **Ambiguous object errors**: Use `room:` in verb definitions to disambiguate when multiple objects share a name.
- **Test verb failures**: Check that `__hash_suffix__` is present in the verb `object:` field — the test verb uses it to build the lookup name.
- **`TypeError: exec() arg 1 must be a string, bytes or code object`**: RestrictedPython compilation failure — check for `dict["key"] += value` patterns in verb code.
- **SSH disconnects mid-build**: Run `docker compose restart webapp celery` to restore, then re-run the build script (tell the user first).
- **Test verb output truncated**: The SSH connection dropped while printing. The build still succeeded. Run the test verb manually in-world.
- **`$furniture` objects stuck in the void (silent `False` in build log)**: `$furniture`'s `moveto` verb returns `False` to block player takes — this also blocks admin `moveto()` calls. The current `build_from_yaml.py` uses `obj.location = room; obj.save()` to bypass this. If you see `False` in the log after move commands, you are running an old version. Manual fix: `@eval "obj = lookup(N); room = lookup(\"Room [hash]\"); obj.location = room; obj.save()"` for each stranded object.
- **NPCs missing player infrastructure**: `@create "NPC" from "$player"` creates the MOO Object but not the Django `Player` model record. The build script calls `Player.objects.create(); p.avatar = obj; p.save()` after each NPC. If NPCs were created by hand or with an older script, add the record via: `@eval "from moo.core.models import Player; obj = lookup(N); p = Player.objects.create(); p.avatar = obj; p.save()"`
- **Missing or incorrect room connections**: `@tunnel` silently fails if the current room already has an exit in the requested direction — it prints a red message but the build script never sees it. The build script uses DFS to wire exits, tracking `(room, direction)` pairs in a `created_exits` set. If you see `SKIP duplicate exit` lines in the build log, there is a duplicate exit declaration in the YAML (two exits with the same direction on the same room). If rooms are missing connections after a build, check whether any prior build run left stale exits behind — a fresh DB reset before rebuilding is the cleanest fix.

## Available Build Commands

### `@alias` verb

```
@alias #N as "alias"
@alias "object name" as "alias"
```

Supports global lookup by name or #N ID. The build script uses this for all alias operations (clean, no `@eval` needed).

**Implementation:** `moo/bootstrap/default/verbs/player/at_alias.py`

## Build Automation

All environments are built using the generic `build_from_yaml.py` script.

**Scripts:**

- `build_from_yaml.py` — Generic YAML-driven builder (accepts file or directory)
- `build_moes_tavern.py` — Original monolithic script (reference only)

The `environments/` directory is gitignored — it holds local build artifacts that go stale between runs and are recreated fresh each build.

See `references/build-automation.md` for YAML schema details and advanced patterns.

## Snippets

`snippets/` contains copy-paste-ready YAML verb patterns extracted from real environments. Use these as starting points rather than writing from scratch.

| File | Pattern | Use when |
|------|---------|----------|
| `snippets/hidden-room.yaml` | Interactive object teleports player to a hidden room | Secret passages, concealed entrances, puzzle doors |
| `snippets/stateful-counter.yaml` | Numeric counter with different output per tier | Consumables, escalating effects, repeated actions that change over time |
| `snippets/one-shot-state.yaml` | Boolean flag: full reveal on first use, summary on repeat | Sealed documents, one-time discoveries, puzzle items that change permanently |

## Complete Workflow Example

```bash
# Phase 1: Research (manual web research)

# Phase 2: Generate YAML
# Large environment → use directory layout:
mkdir extras/skills/game-designer/environments/my-environment/
# Create metadata.yaml, rooms.yaml, objects.yaml, npcs.yaml, verbs.yaml

# Phase 3: Validate YAML
python extras/skills/game-designer/tools/build_from_yaml.py \
  --dry-run extras/skills/game-designer/environments/my-environment/
# Output:
#   Loaded environment: My Environment
#     Hash mode: enabled
#     Rooms: N
#     Objects: N
#     NPCs: N
#     Verbs: N

# Phase 4: User reviews YAML, approves build

# Phase 5: Execute build (in background)
python extras/skills/game-designer/tools/build_from_yaml.py \
  extras/skills/game-designer/environments/my-environment/ \
  > /tmp/my-environment-build.log 2>&1

# Monitor progress
tail -f /tmp/my-environment-build.log

# Phase 6: Verify in-game
# SSH to MOO, run the test verb printed at end of build output
test-my-environment-abc123
```

## Reference Files

- `references/moo-commands.md` — exact syntax for all build commands
- `references/verb-patterns.md` — RestrictedPython code patterns for interactive verbs
- `references/object-model.md` — parent classes, properties, exits, NPCs
- `references/room-description-principles.md` — guidelines for writing effective room descriptions
- `references/build-automation.md` — workflow guide: running builds, phases, troubleshooting
- `references/yaml-schema.md` — full YAML schema (metadata, rooms, objects, npcs, verbs)
- `references/build-script-internals.md` — Python implementation patterns for build_from_yaml.py
- `assets/test-verb-template.md` — custom test verb template
- `environments/burns-manor.yaml` — single-file example (7 rooms, 34 objects, 2 NPCs, 12 verbs)
- `environments/planet-express/` — directory example (26 rooms, 76 objects, 8 NPCs, 20 verbs)
