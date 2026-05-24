# Build Automation

The build system uses YAML environment files and a generic Python script to build environments programmatically via SSH.

## Architecture

- **YAML files** (`environments/`): content definitions — rooms, objects, NPCs, verbs
- **`build_from_yaml.py`**: reads YAML, connects via SSH, executes wizard commands
- **`moo_ssh.py`**: SSH automation library with delimiter-based output capture

See `references/yaml-schema.md` for the full YAML schema.
See `references/build-script-internals.md` for Python implementation patterns.

## Running a Build

```bash
# Basic build
python extras/skills/game-designer/tools/build_from_yaml.py \
    extras/skills/game-designer/environments/moes-tavern.yaml

# Directory environment
python extras/skills/game-designer/tools/build_from_yaml.py \
    extras/skills/game-designer/environments/planet-express/

# Dry run — validate YAML without connecting
python build_from_yaml.py --dry-run environments/moes-tavern.yaml

# Force hash mode (override YAML setting)
python build_from_yaml.py --hash environments/moes-tavern.yaml

# Production mode — clean names, no hash
python build_from_yaml.py --no-hash environments/moes-tavern.yaml

# Skip test verb
python build_from_yaml.py --no-test environments/moes-tavern.yaml
```

**Always run `--dry-run` first** to validate YAML syntax and confirm counts before committing to a 3-4 minute build.

## Build Phases

1. **Rooms and exits** — Creates all rooms in the void, then DFS-traverses the exit graph from the first room: teleports to each room via `@move me to "<room>"`, describes it, wires exits, recurses into unvisited neighbors
2. **Objects** — Creates in void, describes, adds aliases, marks `obvious`, moves to rooms
3. **NPCs** — Creates objects, creates Django `Player` records, describes, adds aliases, moves to rooms
4. **Verbs** — Substitutes `__hash_suffix__` in verb code, attaches verbs via `@edit ... with`
5. **Test verb** — Generates verification code, places on `$programmer`, runs automatically

## Preparation

**Local development:** DB refresh + server restart before each build keeps state clean.

**Production:** Run directly against the live server — no restart needed.

Do **not** use `@reload` — it creates duplicate verbs on a freshly-bootstrapped DB.

If the server goes down mid-build:

```bash
docker compose restart webapp celery
```

## Performance

With automation mode active (the default), each command takes ~1.1s. A 150-command build takes ~3-4 minutes. Without automation mode, each command takes ~7.5s (~15-20 minutes for the same build).

Do not run multiple builds simultaneously — Wizard moves between rooms and the builds will conflict.

## Troubleshooting

**`WARNING: Could not resolve object '...' for verb '...'`**
The verb's `object:` or `room:` doesn't match any entry in `obj_refs`/`npc_refs`. Check spelling — the room key under `objects:` must exactly match the verb's `room:` field.

**`WARNING: could not get ID` for an object**
A description with unescaped newlines split the `@describe` command, causing output to appear in the wrong command's window. Fixed in current `describe()`. If it reappears, check that `\\`, `\n`, and `"` are all escaped in the right order.

**Stray `"` in Wizard output**
Same root cause as the missing-ID warning above.

**`TypeError: exec() arg 1 must be a string, bytes or code object` in test verb**
RestrictedPython silently failed to compile the verb. Look for `dict["key"] += value` patterns — use plain variables instead (`passed += 1`).

**`$furniture` objects stranded in the void**
`$furniture`'s `moveto` verb returns `False` to block player takes, which also blocks admin placement. Fixed in current `move_to_room()`. Manual recovery per object:

```text
@eval "obj = lookup(N); room = lookup(\"Room Name [hash]\"); obj.location = room; obj.save()"
```

**"Ambiguous object" error during build**
Multiple objects share a name. Add a `room:` field to the verb definition to disambiguate.

**SSH disconnects mid-build**
Restart the server (`docker compose restart webapp celery`), then re-run. Tell the user first.

**`disconnect()` hangs ~5 seconds**
The server's `@quit` verb is not loaded. Run `@reload @quit on $player` after a DB reset.

**Build seems stuck**
Each command takes ~1.1s in automation mode; 150 commands ≈ 3 minutes. The delimiter loop has a 6s timeout before giving up — check for SSH errors.

**Test verb output truncated**
SSH dropped while printing. The build still succeeded — run the test verb manually in-world.

**Duplicate exits after repeated builds**
`@tunnel` silently fails if a direction already exists. The build script tracks `(room, direction)` pairs in `created_exits` to skip duplicates. Stale exits from a prior build require a DB reset to clear cleanly.
