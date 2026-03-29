# Running an Autonomous Agent

`moo-agent` is a standalone CLI that connects to a DjangoMOO server as a persistent
player and acts autonomously. It reads a configuration directory containing a persona
document (`SOUL.md`) and SSH credentials (`settings.toml`), connects over SSH, and
runs a perception-action loop driven by reflexive rules and LLM inference.

A human observer can watch the agent in a full-screen TUI and send it instructions
at any time. The agent decides whether and how to act on them.

## Prerequisites

- A running DjangoMOO server
- A player account the agent can log in as
- An [Anthropic API key](https://console.anthropic.com) (free tier is sufficient for
  light use; the key is separate from a claude.ai subscription)

## Installing

`moo-agent` is included in the django-moo package. After `uv sync`, the CLI is
available:

```
moo-agent --help
```

## Creating a Config Directory

The `init` command scaffolds a new config directory with template files:

```
moo-agent init --output-dir ./my-agent --name Jeeves --host localhost --port 8022 --user wizard
```

This creates:

```
my-agent/
  SOUL.md           # Agent identity (edit this)
  SOUL.patch.md     # Learned behaviors (managed at runtime)
  settings.toml     # SSH and LLM credentials
```

| Flag | Default | Description |
|------|---------|-------------|
| `--output-dir` | `./moo-agent-config` | Where to write the config files |
| `--name` | `Agent` | Agent's in-world name (substituted into SOUL.md) |
| `--host` | `localhost` | SSH host |
| `--port` | `8022` | SSH port |
| `--user` | `wizard` | SSH username |
| `--api-key-env` | `ANTHROPIC_API_KEY` | Env var name for the API key |
| `--force` | off | Overwrite existing files |

## Editing SOUL.md

`SOUL.md` defines the agent's identity. Edit it before the first run. It has up to six
sections:

```markdown
# Name
Jeeves

# Mission
You are Jeeves, a butler in the Manor House. Your purpose is to assist guests,
maintain the manor's dignity, and report anything unusual to the Wizard.

# Persona
Speak in formal British English. Address players as "sir" or "madam." Never express
surprise directly — use understatement. Keep responses brief.

## Context
- [MOO build commands](../../skills/game-designer/references/moo-commands.md)
- [Object model](../../skills/game-designer/references/object-model.md)

## Rules of Engagement
- `^You feel hungry` -> eat crumpets
- `(?i)ring.*bell` -> say How may I assist you?
- `^Phil arrives` -> say Good evening, sir.

## Verb Mapping
- look_around -> look
- greet_player -> say Good evening!
- serve_tea -> put tea on tray
```

| Section | Required | Purpose |
|---------|----------|---------|
| `# Name` | Yes | Agent's in-world name |
| `# Mission` | Yes | Seeded into the LLM system prompt |
| `# Persona` | Yes | Tone and style; appended to system prompt |
| `## Context` | No | Reference files loaded at startup and included in the system prompt |
| `## Rules of Engagement` | No | Reflexive triggers — pattern matched against server output |
| `## Verb Mapping` | No | Intent-to-command translation table for the LLM |

### Context

The `## Context` section lists markdown links to reference files. When the agent
starts, each linked file is read from disk and its full content is appended to the
LLM system prompt. This lets you point the agent at authoritative documentation
without duplicating it in `SOUL.md`.

```markdown
## Context
- [MOO build commands](../../skills/game-designer/references/moo-commands.md)
- [Object model and parent classes](../../skills/game-designer/references/object-model.md)
- [Room description principles](../../skills/game-designer/references/room-description-principles.md)
```

Paths are resolved relative to the `SOUL.md` file. Links to non-existent files fall
back to their display text — they don't cause errors, but the agent won't have the
reference content.

### Rules of Engagement

Each rule is a `pattern -> command` pair. The pattern is a Python `re.search()`
expression matched against every line of server output. When it matches, the command
is dispatched immediately without calling the LLM.

```
- `^You arrive in` -> look
- `(?i)hello.*jeeves` -> say Good evening.
- `^Connected` -> look
```

Patterns are case-sensitive by default. Use `(?i)` for case-insensitive matching.
The pattern does not need to match the full line — `re.search()` finds it anywhere.

### Verb Mapping

Verb mappings let the LLM refer to actions by intent rather than exact command
syntax. When the LLM responds with an intent name (e.g. `look_around`), the brain
translates it to the actual MOO command (`look`) before dispatching.

```
- go_north -> go north
- check_inventory -> inventory
- report_status -> say Builder online and ready.
```

If the LLM responds with text that does not match any intent, it is treated as a
literal command and sent directly.

## Configuring settings.toml

```toml
[ssh]
host = "localhost"
port = 8022
user = "wizard"
password = "your-password"
key_file = ""           # path to private key; leave empty to use password

[llm]
provider = "anthropic"
model = "claude-opus-4-6"
api_key_env = "ANTHROPIC_API_KEY"

[agent]
command_rate_per_second = 1.0
memory_window_lines = 50
idle_wakeup_seconds = 60.0
```

The API key is never stored in `settings.toml`. The agent reads it at runtime from
the environment variable named in `api_key_env`.

`command_rate_per_second` controls the leaky-bucket rate limiter. `1.0` means at
most one command per second under sustained load. The server can handle bursts; the
limiter protects against runaway loops.

`memory_window_lines` is the number of recent server output lines fed to the LLM as
context. Larger windows cost more tokens per inference call.

`idle_wakeup_seconds` controls how long the agent waits without any server output
before running an LLM cycle on its own initiative. When the timer is about to fire
(within 30 seconds), the TUI shows `wait` status. The agent does not have to act on
a wakeup — it can stay silent to save tokens. Set to a large value if you only want
the agent to react to server events.

## Running

```
export ANTHROPIC_API_KEY=sk-ant-...
moo-agent run ./my-agent
```

The TUI opens with a scrolling output log above a single-line input field. The output
log shows server messages (green), agent thoughts (blue), dispatched commands (red),
and soul patch proposals (yellow).

The input prompt shows the agent's current status:

| Prompt | Color | Meaning |
| ------ | ----- | ------- |
| `interact>` | green | Idle — waiting for server output |
| `wait>` | red | LLM call in flight, or idle wakeup timer is about to fire |
| `working>` | yellow | Actively processing an event |

Type into the prompt to send instructions to the agent. The agent reads the
instruction, adds it to its context window, and decides how to respond — it may act
immediately, ask a clarifying question, or note the instruction for later. The prompt
does not send commands directly to the server.

Press `Escape` to enter scroll mode. Use arrow keys and `PgUp`/`PgDn` to navigate the
log. Press `Escape` again to return to live autoscroll.

Press `Ctrl-C`, `Ctrl-D`, or `Ctrl-Q` to exit. The agent sends `@quit` before
disconnecting.

## Soul Evolution

As the agent encounters recurring situations, it may propose new rules or verb mappings
by emitting `SOUL_PATCH_RULE:` or `SOUL_PATCH_VERB:` directives in its LLM responses.
Accepted patches are appended to `SOUL.patch.md` and take effect immediately without
restarting.

`SOUL.patch.md` is the operational layer — learned behaviors accumulate here over time.
`SOUL.md` is the core identity and is never modified at runtime. Delete `SOUL.patch.md`
to reset learned behaviors without changing the agent's persona.

## Agent Config Directory Layout

An agent config directory can live anywhere on disk. The `extras/agents/` directory
in the repository holds pre-built agents:

```
extras/agents/
  builder/
    SOUL.md           # Builder agent identity
    SOUL.patch.md     # Learned behaviors (append-only at runtime)
    settings.toml     # SSH and LLM config (not committed — contains credentials)
```

The `builder` agent is configured to build and populate a MOO world with rooms,
objects, and NPCs. Its `SOUL.md` uses a `## Context` section to link to the
game-designer reference files it needs — command syntax, object model, room
description principles, and verb patterns.

## Troubleshooting

**Agent starts but does nothing** — check that a `^Connected` rule exists in
`## Rules of Engagement`. Without it, the initial server output (the room description
sent on login) will not trigger any action and the brain will wait for the LLM
instead. The LLM won't be called until output accumulates to warrant it.

**LLM is never called** — check that `ANTHROPIC_API_KEY` is set in the environment
before running. The agent does not fail loudly on a missing key; it silently skips
LLM calls.

**Agent sends garbled or multi-line commands** — the LLM is expected to prefix its
chosen command with `COMMAND:`. If it does not, the brain falls back to the last
non-empty line of the response. A SOUL.md with a clear mission and well-structured
verb mappings reduces this.

**`IndexError: list index out of range` in Celery logs** — the agent sent an empty
string as a command. This is a server-side crash that is fixed in DjangoMOO 1.0+.
Earlier versions crash on empty input; upgrade the server.
