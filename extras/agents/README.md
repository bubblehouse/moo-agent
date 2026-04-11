# Autonomous Agents

This directory contains config directories for autonomous agents that connect to a
DjangoMOO server as persistent players and act independently. Each agent is operated
via the `moo-agent` CLI.

## Agents

### The Tradesmen — World Builders

The Tradesmen are six specialized agents that work together on the same MOO instance.
Foreman orchestrates the token chain; the five workers execute in fixed order.

| Agent | What it does |
|-------|-------------|
| [foreman](foreman/README.md) | Holds the master token, dispatches it in order, detects stalls, loops automatically |
| [mason](mason/README.md) | Digs rooms, writes descriptions, wires exits (`$player`) |
| [tinker](tinker/README.md) | Creates interactive `$thing` objects and secret exits via verbs (`$programmer`) |
| [joiner](joiner/README.md) | Creates `$furniture` and `$container` objects (`$player`) |
| [harbinger](harbinger/README.md) | Creates one NPC per ~10% of rooms (`$programmer`) |
| [stocker](stocker/README.md) | Stocks containers with consumables and dispensers (`$programmer`) |

**Run order:** Start Foreman first (or alongside all workers). Foreman pages Mason to
begin and orchestrates the full chain:

```
Mason → Tinker → Joiner → Harbinger → Stocker → (back to Mason)
```

To launch all six at once, use the `groups/` config:

```bash
extras/skills/agent-trainer/scripts/agentmux start groups/tradesmen.conf
extras/skills/agent-trainer/scripts/agentmux restart mason  # restart one agent
extras/skills/agent-trainer/scripts/agentmux stop groups/tradesmen.conf
```

### The Mailmen — Mail System Load Agents

Two character-driven agents that stress-test the mail system (`@mail`, `@send`,
`@reply`, pagination, `Message`/`MessageRecipient` models) under sustained use.
They do not build or explore — they sit at their desks and exchange letters indefinitely.

| Agent | What it does |
|-------|-------------|
| [cliff](cliff/README.md) | Pompous postal worker; delivers "little-known facts" (subtly wrong) |
| [newman](newman/README.md) | Theatrical wronged visionary; escalating grievances and failed schemes |

To launch both at once:

```bash
extras/skills/agent-trainer/scripts/agentmux start groups/mailmen.conf
```

The Mailmen use `idle_wakeup_seconds > 0` (periodic autonomous action) rather than
the token-protocol agents which use `idle_wakeup_seconds = 0` (page-triggered only).

### The Inspectors — Verb Coverage Agents

Sequential token-chain agents that exercise verb paths untouched by the Tradesmen:
containers, exit locks, notes/letters, and gender/pronoun substitution.

| Agent | What it tests |
|-------|--------------|
| [foreman](foreman/README.md) | Coordinates the Inspectors token chain (same Foreman, different `MOO_TOKEN_CHAIN`) |
| [quartermaster](quartermaster/) | Container open/close/take/put, opacity, `@lock_for_open` |
| [warden](warden/) | Exit `@lock`/`@unlock`, key-based traversal |
| [archivist](archivist/) | Note/letter create, read, `@lock_for_read`, erase, burn |
| [tailor](tailor/) | `@gender`, pronoun substitution in messages, `@messages`, `@check` |

```bash
MOO_TOKEN_CHAIN=quartermaster,warden,archivist,tailor agentmux --group inspectors start
```

### The Neighbours — Social System Agents

Two simultaneous timer-based agents in The Neighborhood that exercise whisper,
emote, gag, ungag, listgag, and paranoid mode.

| Agent | Persona | What it tests |
|-------|---------|--------------|
| [gossip](gossip/) | Mrs. Helen Lovejoy | `whisper`, `emote`, `say` |
| [prude](prude/) | Mrs. Agnes Skinner | `@gag`, `@ungag`, `@listgag`, `@paranoid` |

```bash
agentmux --group neighbours start
```

### The Wanderer — World Explorer

Standalone autonomous agent that maps the world and exercises discovery verbs.

| Agent | What it tests |
|-------|--------------|
| [cartographer](cartographer/) | `@who`, `@whereis`, `@rooms`, `@survey`, `@audit`, `look`, exit traversal |

```bash
agentmux --group wanderer start
```

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
