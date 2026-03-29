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

## Soul Architecture

The agent's identity and behavior live across three files:

```
extras/agents/
  baseline.md         # Shared world knowledge for all agents (never edited per-agent)
  my-agent/
    SOUL.md           # Agent's core identity (hand-authored, never modified at runtime)
    SOUL.patch.md     # Learned behaviors (append-only, agent-writable)
    settings.toml     # SSH and LLM credentials
```

`parse_soul()` loads and merges these in order:

1. `baseline.md` from the parent of the config directory — if it exists, its text is
   prepended to the agent's context. This gives all agents under `extras/agents/`
   shared knowledge (sandbox rules, command syntax, parent class reference) without
   repeating it in every `SOUL.md`.
2. `SOUL.md` — core identity. Never modified by the agent.
3. `SOUL.patch.md` — operational layer. The agent appends to this file at runtime
   when it proposes new rules or verb mappings. Base rules from `SOUL.md` are listed
   first, so they take precedence over patch rules when patterns overlap.

Delete `SOUL.patch.md` to reset learned behaviors without touching the agent's
persona or the shared baseline.

## Editing SOUL.md

`SOUL.md` defines the agent's identity. Edit it before the first run. It has up to
six sections:

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

Agent-specific context in `SOUL.md` is appended after `baseline.md`, so `baseline.md`
content always comes first in the system prompt.

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
before running an unsolicited LLM cycle. When the timer is about to fire (within
`warn_threshold` seconds, currently `min(10, idle_wakeup_seconds)`), the status
indicator switches to `sleeping` so the TUI shows the countdown pressure. The agent
does not have to act on a wakeup — it can stay silent to save tokens. Set to a large
value if you only want the agent to react to server events.

## Running

```
export ANTHROPIC_API_KEY=sk-ant-...
moo-agent run ./my-agent
```

The TUI opens with a scrolling output log above a single-line input field.

### Session Resumption

When `moo-agent run` starts, it scans the `logs/` directory inside the config
directory for previous session files. If one exists, it reads the last 40 relevant
log entries (server output, thoughts, actions, goals — not system/patch noise),
extracts the final recorded goal, and pre-populates `brain._memory_summary` and
`brain._current_goal`. The TUI shows:

```
Resuming from prior session. Last goal: <goal text>
```

This means the agent picks up where it left off without needing the full prior
transcript replayed into the context window. Only the most recent previous log is
used; older logs are ignored.

### TUI Log Entry Kinds

Each line in the output log has a kind that controls its color:

| Kind | Color | Source |
| ---- | ----- | ------ |
| `server` | yellow | Normal server output |
| `server_error` | red bold | Server output that looks like an error or traceback |
| `action` | white | Commands the agent dispatched |
| `thought` | dark gray | LLM reasoning text (lines before `COMMAND:`) |
| `goal` | darker gray | Goal updates (`[Goal] ...` thoughts) |
| `system` | gray | Startup messages, connection status |
| `operator` | cyan | Instructions typed by the human operator |
| `patch` | yellow | Soul patch proposals |

The `operator` kind (cyan) distinguishes human input from system messages (gray),
making it easy to scroll back and find where you intervened.

### Status Indicator

The input prompt shows the agent's current status:

| Prompt | Color | Meaning |
| ------ | ----- | ------- |
| `ready>` | green | Idle — waiting for server output |
| `sleeping>` | red | Idle wakeup timer is about to fire |
| `thinking>` | yellow | LLM call in flight or processing an event |

The status indicator is guaranteed to return to `ready` after an LLM call completes,
including when the call fails with an API error.

### Interacting

Type into the prompt to send instructions to the agent. The instruction is added to
the rolling context window as an `[Operator]: ...` message and an LLM cycle fires
immediately — rule matching is skipped because a direct instruction should always
reach the LLM. The agent may act immediately, ask a clarifying question, or note the
instruction for later. The prompt does not send commands directly to the server.

Press `Escape` to enter scroll mode. Use arrow keys and `PgUp`/`PgDn` to navigate the
log. Press `Escape` again to return to live autoscroll.

Press `Ctrl-C`, `Ctrl-D`, or `Ctrl-Q` to exit. The agent sends `@quit` before
disconnecting.

## Architecture

### Rolling Context Window

The brain maintains a bounded deque of recent lines (`memory_window_lines` in
`settings.toml`). This is what the LLM sees in the user-turn message. The window
contains three kinds of content:

- **Server output** — lines received from the MOO server after ANSI stripping.
- **Command echoes** — every command the agent dispatches is also written into the
  window as `> <command>`. This means the LLM can correlate server responses with
  what it sent. Without echoes, a response like "done" or "Description set for #44"
  has no visible cause, prompting unnecessary retries.
- **Operator messages** — instructions typed by the human are written as
  `[Operator]: <text>`. The LLM sees these alongside server output in chronological
  order.

When the window nears capacity, a background summarization task condenses the oldest
half into a 2-3 sentence summary. That summary is stored separately and
prepended to every subsequent LLM user-turn as `[Earlier context: ...]`, keeping the
full history available at lower token cost.

### LLM Response Format

The system prompt instructs the LLM to use a structured response format:

```
Optional reasoning text here — visible to the LLM in the next cycle but never sent to the server.
GOAL: <one-line statement of current objective>
PLAN: <step 1> | <step 2> | <step 3>
COMMAND: <single MOO command>
```

`GOAL:` and `PLAN:` are extracted and stored across cycles so the agent maintains
continuity of intent. `COMMAND:` is dispatched after intent resolution. Lines before
`GOAL:` are treated as thoughts and shown in the TUI. If the LLM omits `COMMAND:`,
the brain falls back to the last non-empty thought line.

The LLM can also propose soul patches before `COMMAND:`:

```
SOUL_PATCH_RULE: ^You arrive -> look
SOUL_PATCH_VERB: check_exits -> @exits
```

### LLM Errors

API failures (rate limits, credit exhaustion, network errors) are caught and reported
as `[LLM error] <message>` entries in the TUI log under the `thought` kind. The
status indicator returns to `ready` so the agent doesn't appear frozen.

### Connection Layer

The connection layer (`moo/agent/connection.py`) handles two modes:

**Pre-automation mode** — before delimiters are set, the session emits one callback
per complete line. This covers the initial room description the server sends on login.

**Delimiter mode** — after `MooConnection._setup_automation_mode()` runs, the server
wraps all output in unique `>>MOO-START-<id><<` / `>>MOO-END-<id><<` markers. The
session extracts content between markers and discards the markers themselves.

During setup, `MooSession.set_suppress(True)` mutes all output so the marker
confirmation strings (`OUTPUTPREFIX set`, `OUTPUTSUFFIX set`, `QUIET enabled`) never
appear as agent log entries. When suppression lifts, the buffer is cleared so no
setup artifacts survive as preamble.

**Eager flush** — after processing each delimiter window, the connection checks for
complete lines sitting in the buffer before the next pending prefix. These are
`print()` confirmations from commands whose `tell()` output was empty (Celery
flushes `print()` after the current command's suffix). Without eager flushing, the
agent would see no acknowledgment and retry the same command repeatedly.

### Wakeup Loop

A `_wakeup_loop` coroutine runs alongside the main perception loop. It fires an LLM
cycle when `idle_wakeup_seconds` have elapsed since the last server output or
operator instruction. Within `warn_threshold` seconds of firing, the status switches
to `sleeping` so the TUI shows the pressure. The wakeup is rate-limited by the same
leaky-bucket limiter as normal commands.

The agent does not have to take action on a wakeup — if the LLM decides nothing
needs doing, it can respond without a `COMMAND:` line.

## Soul Evolution

As the agent encounters recurring situations, it may propose new rules or verb mappings
by emitting `SOUL_PATCH_RULE:` or `SOUL_PATCH_VERB:` directives in its LLM responses.
Accepted patches are appended to `SOUL.patch.md` and take effect immediately without
restarting.

`SOUL.patch.md` is the operational layer — learned behaviors accumulate here over time.
`SOUL.md` is the core identity and is never modified at runtime. Delete `SOUL.patch.md`
to reset learned behaviors without changing the agent's persona.

## Logging

Each session writes a timestamped log file to `<config_dir>/logs/<timestamp>.log`.
Each line has the format:

```
[HH:MM:SS] [kind] text
```

Log files are used at the next startup to restore session context. The `logs/`
directory is never pruned automatically — old logs accumulate and only the most
recent previous log is read on startup.

## Agent Config Directory Layout

An agent config directory can live anywhere on disk. The `extras/agents/` directory
in the repository holds pre-built agents:

```
extras/agents/
  baseline.md           # Shared world knowledge — loaded for all agents in this directory
  builder/
    SOUL.md             # Builder agent identity
    SOUL.patch.md       # Learned behaviors (append-only at runtime)
    settings.toml       # SSH and LLM config (not committed — contains credentials)
    logs/               # Per-session log files (created automatically)
```

The `builder` agent is configured to build and populate a MOO world with rooms,
objects, and NPCs. Its `SOUL.md` uses a `## Context` section to link to the
game-designer reference files it needs — command syntax, object model, room
description principles, and verb patterns. The shared `baseline.md` provides
sandbox rules, `@eval` pre-imports, and the parent class quick reference.

## Troubleshooting

**Agent starts but does nothing** — check that a `^Connected` rule exists in
`## Rules of Engagement`. Without it, the initial server output (the room description
sent on login) will not trigger any action and the brain will wait for the LLM
instead.

**LLM is never called** — check that `ANTHROPIC_API_KEY` is set in the environment
before running. The agent reports API errors as `[LLM error] ...` entries in the
TUI; if those are absent, the variable may not be set.

**Agent sends garbled or multi-line commands** — the LLM is expected to prefix its
chosen command with `COMMAND:`. If it does not, the brain falls back to the last
non-empty line of the response. A `SOUL.md` with a clear mission and well-structured
verb mappings reduces this.

**Status sticks at `thinking` after an error** — this was a bug in earlier versions.
The LLM exception handler now always resets status to `ready`. If you see it stuck,
check whether the agent process itself has hung.

**`IndexError: list index out of range` in Celery logs** — the agent sent an empty
string as a command. This is a server-side crash that is fixed in DjangoMOO 1.0+.
Earlier versions crash on empty input; upgrade the server.
