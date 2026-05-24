# game-designer

A Claude Code skill for designing and building themed multi-room environments in DjangoMOO via wizard SSH commands.

## When to use it

Invoke this skill when you want to:

- Build a new MOO environment (rooms, objects, NPCs, interactive verbs)
- Create rooms based on a real or fictional location
- Add NPCs with dialogue to an area
- Write custom verbs for objects in a space

Trigger phrases: "build a MOO environment", "create rooms for X", "design a location based on Y", "add NPCs for Z", "set up a MOO area".

## How to invoke

Claude Code picks this skill up automatically from the trigger phrases above. You can also invoke it explicitly:

```
/game-designer build a 1920s speakeasy
/game-designer add a talking parrot NPC to the existing bar
```

## What it does

The skill follows a 5-phase workflow:

1. **Research** — gathers theme details (layout, objects, characters, atmosphere) before writing any YAML
2. **Design** — generates a YAML environment file (or directory of files for large environments)
3. **Review** — shows you the YAML and a dry-run count; waits for your approval before building
4. **Build** — runs `build_from_yaml.py` in the background (3–4 minutes); outputs a log file
5. **Verify** — auto-generated test verb confirms all rooms, objects, NPCs, and verbs are in place

## Requirements

- A running DjangoMOO instance reachable via SSH
- Wizard credentials configured in the build script

## What's in this folder

| Path | Purpose |
|------|---------|
| `SKILL.md` | AI agent instructions (the skill prompt) |
| `tools/build_from_yaml.py` | Generic YAML-driven build script |
| `tools/moo_ssh.py` | SSH automation layer used by the build script |
| `environments/` | YAML files for built or in-progress environments |
| `snippets/` | Copy-paste YAML patterns for common verb types |
| `assets/test-verb-template.md` | Template for custom test verbs |
| `references/` | Supporting reference docs for the AI agent |

### Snippets

| File | Pattern |
|------|---------|
| `snippets/hidden-room.yaml` | Object teleports player to a hidden room |
| `snippets/stateful-counter.yaml` | Numeric counter with tiered output |
| `snippets/one-shot-state.yaml` | Boolean flag: full reveal once, summary on repeat |

### Reference files

| File | Contents |
|------|----------|
| `references/moo-commands.md` | Exact syntax for all wizard build commands |
| `references/verb-patterns.md` | RestrictedPython code patterns for interactive verbs |
| `references/object-model.md` | Parent classes (`$thing`, `$container`, `$furniture`, `$note`, `$player`), exits, NPCs |
| `references/room-description-principles.md` | Guidelines for writing effective room descriptions |
| `references/build-automation.md` | YAML schema details and advanced build patterns |

### Example environments

| Path | Description |
|------|-------------|
| `environments/burns-manor/` | 7 rooms, 34 objects, 2 NPCs, 12 verbs (directory layout) |
| `environments/planet-express/` | 26 rooms, 76 objects, 8 NPCs, 20 verbs (directory layout) |
| `environments/bag-end/` | Tolkien hobbit-hole environment |

## Running the build script directly

```bash
# Dry run — validate YAML without connecting
python extras/skills/game-designer/tools/build_from_yaml.py \
    --dry-run extras/skills/game-designer/environments/my-env/

# Full build
python extras/skills/game-designer/tools/build_from_yaml.py \
    extras/skills/game-designer/environments/my-env/ \
    > /tmp/my-env-build.log 2>&1
```

Options: `--dry-run`, `--no-test`, `--hash`, `--no-hash`, `--host HOST`, `--port PORT`
