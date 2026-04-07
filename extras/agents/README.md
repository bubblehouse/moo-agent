# Autonomous Agents

This directory contains config directories for autonomous agents that connect to a
DjangoMOO server as persistent players and act independently. Each agent is operated
via the `moo-agent` CLI.

## Agents

The Tradesmen are five specialized agents that work together on the same MOO instance.
Foreman orchestrates the token chain; the four workers execute in order.

| Agent | What it does |
|-------|-------------|
| [foreman](foreman/README.md) | Holds the master token, dispatches it in order, detects stalls, loops automatically |
| [mason](mason/README.md) | Digs rooms, writes descriptions, wires exits |
| [tinker](tinker/README.md) | Creates interactive `$thing` objects and secret exits via verbs |
| [joiner](joiner/README.md) | Creates `$furniture` and `$container` objects |
| [harbinger](harbinger/README.md) | Creates one NPC per room |

**Run order:** Start Foreman first (or alongside the workers). Foreman pages Mason to
begin and orchestrates the full chain: Mason → Tinker → Joiner → Harbinger → Mason (loop).

The original [builder](builder/README.md) agent (monolithic, all domains) is kept for
reference and can be removed once the Tradesmen are validated.

## Shared baseline

`baseline.md` is loaded for every agent before its own `SOUL.md`. It provides:
sandbox rules, `@eval` pre-imports, the parent class quick reference,
`#N` object reference rules, and the `SCRIPT:`/`COMMAND:`/`DONE:`/`PLAN:` response format.

Agent-specific knowledge lives in each agent's own `SOUL.md`:

- `@tunnel` syntax → Mason
- Verb dispatch (`--dspec`, `--iobj`) and verb testing → Tinker
- NPC `tell` verb pattern and `announce_all_but` → Harbinger

Agents that include a `## Tools` section in their `SOUL.md` additionally use the
typed tool harness (`moo/agent/tools.py`), which translates structured LLM tool calls
to correct MOO commands automatically. `baseline.md` covers the fallback text format
for commands the tool harness doesn't cover.

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
