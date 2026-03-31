# Autonomous Agents

This directory contains config directories for autonomous agents that connect to a
DjangoMOO server as persistent players and act independently. Each agent is operated
via the `moo-agent` CLI.

## Agents

| Agent | What it does |
|-------|-------------|
| [builder](builder/README.md) | Builds rooms, objects, NPCs, and verbs; populates the MOO world |

## Shared baseline

`baseline.md` is loaded for every agent in this directory before its own `SOUL.md`.
It provides: sandbox rules, `@eval` pre-imports, the parent class quick reference,
and the `SCRIPT:`/`COMMAND:`/`DONE:` response format the brain expects.

Do not put agent-specific content in `baseline.md`. Edit an agent's `SOUL.md` instead.

## Directory structure

Each agent directory contains:

```
agent-name/
  SOUL.md           # Core identity (hand-authored, never modified at runtime)
  SOUL.patch.md     # Learned behaviors (append-only, agent-writable)
  settings.toml     # SSH and LLM credentials (not committed)
  logs/             # Per-session log files (created automatically)
  README.md         # Human-readable docs (this kind of file)
```

## Quick start

Install `moo-agent` (included in the django-moo package after `uv sync`), then:

```bash
# Scaffold a new agent config directory
moo-agent init --output-dir extras/agents/my-agent --name MyAgent \
    --host localhost --port 8022 --user wizard

# Edit SOUL.md and settings.toml, then run
moo-agent run extras/agents/my-agent
```

See `docs/source/how-to/moo-agent.md` for full CLI reference and architecture details.

## Adding a new agent

1. Run `moo-agent init` to scaffold the directory.
2. Edit `SOUL.md`: name, mission, persona, rules of engagement, context links, verb mapping.
3. Edit `settings.toml`: SSH host/port/credentials, LLM provider.
4. Create `README.md` documenting purpose, prerequisites, and SOUL.md structure.
5. Add the agent to the table above.
