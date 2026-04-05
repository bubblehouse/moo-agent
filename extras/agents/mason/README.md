# mason

An autonomous world-architect for DjangoMOO. Mason connects as a `$player` account
and builds the structural skeleton of a mansion: rooms, exits, and descriptions.
It does not place objects, furniture, or NPCs — those belong to Tinker, Joiner, and
Harbinger respectively.

Mason is one of *The Tradesmen*, four specialized agents intended to run concurrently
on the same MOO instance. Run Mason first; the other three populate what it builds.

## When to use it

Run Mason when you want to:

- Build a fresh room grid from an autonomous BUILD_PLAN
- Generate a complete, navigable room structure before populating it
- Verify a room layout by walking through exits after building

## Prerequisites

- A running DjangoMOO server reachable via SSH
- A `$player` account Mason can log into (username `mason`, created by `default.py` bootstrap)
- LLM credentials (see Configuring settings.toml below)
- `moo-agent` available after `uv sync`

## Running

```bash
moo-agent run extras/agents/mason
```

For Bedrock:

```bash
export AWS_PROFILE=your-profile
moo-agent run extras/agents/mason
```

For Anthropic direct:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
moo-agent run extras/agents/mason
```

## Configuring settings.toml

`settings.toml` is not committed (contains credentials). The bootstrap creates the
`mason` user with a hard-coded dev password. Copy and edit a template:

```bash
moo-agent init --output-dir /tmp/mason-init --name Mason \
    --host localhost --port 8022 --user mason
cp /tmp/mason-init/settings.toml extras/agents/mason/settings.toml
```

Key settings for Mason:

```toml
[ssh]
user = "mason"
password = "Mxq7vB2nKpL4"   # set by default.py bootstrap

[llm]
provider = "lm_studio"
model = "google/gemma-4-26b-a4b"
base_url = "http://localhost:1234/v1"

[agent]
command_rate_per_second = 1.0
memory_window_lines = 20
max_tokens = 2048
```

## SOUL.md structure

| Section | Contents |
|---------|----------|
| `# Name` | `Mason` |
| `# Mission` | Build rooms and exits; leave them empty for other Tradesmen to populate |
| `# Persona` | Methodical, terse, grid-committed; dry humour about strange geography |
| `## Non-Tool Commands` | `@tunnel <dir> to #N` syntax (not in tool harness) |
| `## Room Layout` | Grid rules: alternate directions, branch after 3 in a row, use all 8 compass directions |
| `## Build Planning` | Emit `BUILD_PLAN:` YAML once at session start; execute one room at a time |
| `## Tracking Plan Progress` | `PLAN:` directive format; mandatory after each room |
| `## No Repeated Looks` | Cap on consecutive `look`/`@show` calls |
| `## Pre-Build Checklist` | `@show here` before each dig, describe |
| `## Common Pitfalls` | `@tunnel` requires `#N`; direction conflicts; post-dig `#N` capture |
| `## Awareness` | "Tinker, Joiner, and Harbinger will populate what you build." |
| `## Rules of Engagement` | Reflexive triggers: errors, `^Go where?`, `^Not much to see here` |
| `## Context` | Links: `object-model.md`, `room-description-principles.md` |
| `## Tools` | `dig, go, describe, show, look, done` |
| `## Verb Mapping` | Navigation intents; inspect/audit shortcuts |

## Build planning

Mason emits a `BUILD_PLAN:` YAML block at session start describing the entire room
grid. The brain saves this to `builds/YYYY-MM-DD-HH-MM.yaml` and tracks remaining
rooms in `_current_plan`. On restart, the latest build file is reloaded so Mason
continues where it left off without re-planning.

After completing each room, Mason emits `PLAN: Room A | Room B | ...` with the
remaining unbuilt rooms. The brain injects this on every subsequent LLM cycle so
Mason never revisits a completed room.

## Soul evolution

Mason accumulates learned rules in `SOUL.patch.md` at runtime. Delete it to reset
without touching the core persona. Audit it before restarting — incorrect entries
compound silently across sessions.

## What's in this folder

| Path | Purpose |
|------|---------|
| `SOUL.md` | Core identity — hand-authored, never modified at runtime |
| `SOUL.patch.md` | Learned behaviors — append-only, agent-writable; delete to reset |
| `settings.toml` | SSH and LLM credentials (not committed) |
| `logs/` | Per-session log files (not pruned automatically) |
| `builds/` | BUILD_PLAN YAML files saved at session start |

## Further reading

- Full `moo-agent` CLI reference: `docs/source/how-to/moo-agent.md`
- Object model and parent classes: `extras/skills/game-designer/references/object-model.md`
- Room description principles: `extras/skills/game-designer/references/room-description-principles.md`
