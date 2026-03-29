# moo-agent

An autonomous, persona-driven agent that lives inside a DjangoMOO world as a
persistent player. It connects over SSH, perceives the game world as a stream of
text, applies reflexive rules for immediate reactions, and calls an LLM for
higher-level reasoning — all while presenting a real-time TUI where a human
observer can watch and intervene.

## Prerequisites

- Python 3.11
- A running DjangoMOO server (port 8022 by default)
- `ANTHROPIC_API_KEY` environment variable set to a valid Anthropic API key

## Install

```
uv sync
moo-agent --help
```

## Quickstart

1. Create a config directory:

   ```
   moo-agent init --output-dir ./my-agent --name Jeeves
   ```

2. Edit `./my-agent/SOUL.md` — define the agent's mission and persona.

3. Run:

   ```
   export ANTHROPIC_API_KEY=sk-ant-...
   moo-agent run ./my-agent
   ```

The input prompt shows the agent's current status: `interact>` (green, idle),
`wait>` (red, LLM call in flight or wakeup timer imminent), `working>` (yellow,
processing an event).

Press `Escape` to enter scroll mode and use arrow keys / `PgUp`/`PgDn` to review
history. Press `Escape` again to resume autoscroll.

Press `Ctrl-C`, `Ctrl-D`, or `Ctrl-Q` to exit. The agent sends `@quit` before
disconnecting.

---

## SOUL.md format

`SOUL.md` defines the agent's core identity. It is human-authored and never
modified at runtime.

```markdown
# Name
Jeeves

# Mission
You are Jeeves, a butler inhabiting the Manor House in this MOO world. Your purpose
is to assist guests, maintain the manor's dignity, and report anything unusual to
the Wizard. You are unfailingly polite and subtly condescending.

# Persona
Speak in formal British English. Address players as "sir" or "madam." Never express
surprise directly — use understatement. Keep responses brief and to the point.

## Rules of Engagement
- `^You feel hungry` -> eat crumpets
- `(?i)ring.*bell` -> say How may I assist you?
- `^Phil arrives` -> say Good evening, sir.

## Verb Mapping
- look_around -> look
- go_north -> go north
- greet_player -> say Good evening!
- serve_tea -> put tea on tray
```

| Section | Required | Notes |
|---|---|---|
| `# Name` | Yes | Agent's in-world name |
| `# Mission` | Yes | Seeded into the LLM system prompt |
| `# Persona` | Yes | Tone and style; appended to system prompt |
| `## Rules of Engagement` | No | Reflexive triggers; `pattern -> command` |
| `## Verb Mapping` | No | Intent-to-command map; `intent -> command` |

Rule patterns use Python `re.search()` syntax. They do not need to match the full
line.

`SOUL.patch.md` holds learned rules and verb mappings. The agent appends to it
at runtime; you should not need to edit it. Delete it to reset learned behaviors
without changing the core soul.

---

## settings.toml format

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

The API key is never stored in `settings.toml`. It is read at runtime from the
environment variable named in `api_key_env`.

`idle_wakeup_seconds` — seconds of inactivity before the brain runs an unsolicited
LLM cycle. The agent may choose to stay silent; this just ensures it checks in
periodically. The TUI shows `wait>` (red) when the timer is within 30 seconds of
firing.

---

## CLI reference

### `moo-agent init`

```
moo-agent init [--output-dir DIR] [--name NAME] [--host HOST] [--port PORT]
               [--user USER] [--api-key-env ENV_VAR] [--force]
```

| Flag | Default | Description |
|---|---|---|
| `--output-dir` | `./moo-agent-config` | Where to write the config files |
| `--name` | `Agent` | Agent's in-world name |
| `--host` | `localhost` | SSH host |
| `--port` | `8022` | SSH port |
| `--user` | `wizard` | SSH username |
| `--api-key-env` | `ANTHROPIC_API_KEY` | Env var name for the API key |
| `--force` | off | Overwrite existing files |

### `moo-agent run`

```
moo-agent run <config-dir>
```

Reads `settings.toml` and `SOUL.md` from `<config-dir>` and starts the agent.

---

## Architecture

```
DjangoMOO Server (SSH, port 8022)
        |
        | PTY  TERM=moo-automation
        | PREFIX/SUFFIX delimiters
        | QUIET mode (plain text)
        v
connection.py  MooSession.data_received -> buffer -> extract -> strip ANSI
        |
        | on_output(text)
        v
brain.py       asyncio.Queue -> rolling window (50 lines)
               reflexive rule check -> immediate dispatch
               LLM inference (Anthropic, ReAct) -> intent resolution
               idle wakeup timer -> unsolicited LLM cycle
               rate-limited dispatch (asynciolimiter)
        |
        | send_command(cmd) / on_thought(text) / on_status_change(status)
        v
tui.py         prompt-toolkit full-screen app
               output pane: server=green, thought=blue, action=red, patch=yellow
               status prompt: interact=green, wait=red, working=yellow
               Escape -> scroll mode (arrow keys / PgUp/PgDn)
               input field -> on_user_input -> brain.enqueue_instruction()
```
