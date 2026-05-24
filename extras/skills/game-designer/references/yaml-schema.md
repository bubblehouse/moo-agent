# YAML Schema Reference

Full schema for environment files used by `build_from_yaml.py`.

See `references/build-automation.md` for how to run builds.
See `SKILL.md` for the `__hash_suffix__` placeholder system.

## metadata

```yaml
metadata:
  name: "Environment Name"          # Required
  description: "Brief description"  # Optional
  author: "game-designer"           # Optional
  version: "1.0"                    # Optional
  base_parent: "$thing"             # Default parent for objects (default: "$thing")
  npc_parent: "$player"             # Default parent for NPCs (default: "$player")
  use_hash_suffix: true             # Enable hash mode (default: true)
```

**Hash mode:** `true` appends `[abc123]` to all names (testing, repeatable builds). `false` uses clean names (production). Override with `--hash` / `--no-hash` CLI flags.

## rooms

```yaml
rooms:
  - name: "Room Name __hash_suffix__"
    description: "Detailed room description..."
    exits:
      - direction: north
        to: "Another Room"       # Clean name — no __hash_suffix__ in exit targets
      - direction: south
        to: "External Room"
```

Exit `to:` fields always use clean names — the build script resolves them via the internal `room_map` keyed by stripped names.

## objects

```yaml
objects:
  "Room Name":                      # Section key is clean room name — no __hash_suffix__
    - name: "object name __hash_suffix__"
      description: "Object description..."
      aliases: ["alias1", "alias2"]
      parent: "$thing"              # Optional; overrides metadata.base_parent
      obvious: true                 # Appears in room listing on `look` (default: false)
      quantity: 4                   # Create N identical objects
```

**`obvious` guidelines:** mark objects a player would immediately notice (dominant furniture, interactive focal points, major props). Leave small details, easter eggs, and items discovered by examining other objects as `obvious: false`.

## npcs

```yaml
npcs:
  - name: "NPC Name __hash_suffix__"
    description: "NPC description..."
    aliases: ["alias"]
    parent: "$player"               # Optional; overrides metadata.npc_parent
    room: "Room Name"               # Clean name — no __hash_suffix__
```

The build script creates a Django `Player` record (no User) for each NPC automatically. See `references/build-script-internals.md` for why this is required.

## verbs

```yaml
verbs:
  - verb: "verb_name"
    object: "object name __hash_suffix__"   # Has __hash_suffix__ for lookup
    room: "Room Name"                        # Clean name — for disambiguation
    code: |
      #!moo verb verb_name alias --on "object name __hash_suffix__" --dspec either
      from moo.sdk import context, lookup, NoSuchObjectError
      target = lookup("Target Room __hash_suffix__")
      context.player.moveto(target)
```

`__hash_suffix__` inside verb code (shebang `--on` argument and `lookup()` calls) is substituted by the build script before sending via `@edit`.

## test (optional)

```yaml
test:
  rooms: ["Room 1", "Room 2"]
  objects:
    "Room 1": ["object1", "object2"]
  npcs: ["NPC1", "NPC2"]
  verbs:
    - {object: "object1", verb: "verb1"}
```

If omitted, test expectations are auto-generated from the YAML structure.

## Single-file vs. directory layout

Small environments (≤10 rooms, ≤30 objects) can live in a single file. Larger ones use a directory:

```
environments/<name>/
  metadata.yaml
  rooms.yaml
  objects.yaml
  npcs.yaml
  verbs.yaml
```

The build script merges all `*.yaml` files in the directory. Keys are distinct so files merge without conflicts.
