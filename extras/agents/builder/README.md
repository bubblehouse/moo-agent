# builder

An autonomous construction agent for DjangoMOO. Builder connects to the server as
a wizard-level player and populates the world with rooms, exits, objects, NPCs, and
interactive verbs. It is driven by the game-designer skill's reference files and
operated via the `moo-agent` CLI.

## When to use it

Run Builder when you want to:

- Execute a `build_from_yaml.py` YAML build autonomously without watching the SSH
  session yourself
- Have an agent populate a room or area interactively (placing objects, writing
  descriptions, attaching verbs) based on instructions typed into the TUI
- Verify a completed build by walking through rooms and running test verbs

## Prerequisites

- A running DjangoMOO server reachable via SSH
- A wizard-level player account Builder can log in as
- LLM credentials (see Configuring settings.toml below)
- `moo-agent` available after `uv sync`

## Running

```bash
moo-agent run extras/agents/builder
```

For Bedrock (the default):

```bash
export AWS_PROFILE=your-profile
moo-agent run extras/agents/builder
```

For Anthropic direct:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
moo-agent run extras/agents/builder
```

The TUI opens. Builder connects, runs `look`, and waits. Type instructions into the
prompt to direct it. Builder will queue multi-step build sequences autonomously using
`SCRIPT:` directives.

## Configuring settings.toml

`settings.toml` is not committed (it contains credentials). Copy the template
produced by `moo-agent init` and edit it:

```bash
moo-agent init --output-dir /tmp/builder-init --name Builder \
    --host localhost --port 8022 --user wizard
cp /tmp/builder-init/settings.toml extras/agents/builder/settings.toml
```

Key settings for Builder:

```toml
[llm]
# Bedrock (production)
provider = "bedrock"
model = "us.anthropic.claude-opus-4-6-v1"
aws_region = "us-east-1"

# LM Studio (local dev — used with Gemma 4 26B)
# provider = "lm_studio"
# model = "google/gemma-4-26b-a4b"
# base_url = "http://localhost:1234/v1"

[agent]
command_rate_per_second = 1.0   # one command/second max; build sequences queue up fine
memory_window_lines = 20        # keep low with large models to avoid KV cache exhaustion
max_tokens = 2048               # must accommodate multi-tool responses; 1024 is too small
```

## Tool harness

Builder uses a typed tool harness (`moo/agent/tools.py`) instead of emitting raw MOO
commands via `SCRIPT:`. When the LLM calls a tool, the brain translates the structured
arguments to correct MOO command strings, handling shebang lines, quoting, and `--dspec`
flags automatically.

The `## Tools` section in `SOUL.md` lists which tools are active. Each tool name
corresponds to a `ToolSpec` in `BUILDER_TOOLS`:

| Tool | MOO output |
|------|-----------|
| `dig` | `@dig {dir} to "{room}"` — also requires `@tunnel` for return exit |
| `go` | `go {dir}` — validates against compass directions; rejects room IDs |
| `describe` | `@describe {target} as "{text}"` |
| `create_object` | `@create "{name}" from "{parent}"` |
| `write_verb` | `@edit verb {name} on {obj} with "{shebang}\n{code}"` — injects shebang, `--on`, `--dspec` automatically |
| `alias` | `@alias {obj} as "{name}"` |
| `make_obvious` | `@obvious {obj}` |
| `move_object` | `@move {obj} to {dest}` |
| `show` | `@show {target}` |
| `look` | `look` or `look {target}` |
| `done` | *(no command — brain clears `_current_goal`)* |

For operations not covered by the tool harness (`@eval`, `@recycle`, `@tunnel`), use
`SCRIPT:` as before.

## Build planning

Builder emits a `BUILD_PLAN:` YAML block at the start of each session describing the
full world it intends to build. The brain saves this to `builds/YYYY-MM-DD-HH-MM.yaml`
and extracts room names into `_current_plan`. On restart, the latest build file is
reloaded automatically so Builder picks up where it left off without re-planning.

After completing each room, Builder emits a `PLAN: Room One | Room Two | ...` directive
listing the remaining unbuilt rooms. The brain tracks this and injects it into the
next LLM cycle so Builder never revisits completed rooms.

## SOUL.md structure

Builder's `SOUL.md` has the following sections:

| Section | Contents |
|---------|----------|
| `# Name` | `Builder` |
| `# Mission` | Build a quirky, layered world; craft and specificity over generic output; act autonomously |
| `# Persona` | Methodical and terse; dry humour; no hedging — says the thing itself |
| `## NPCs` | `$player` parent, `tell` verb override with `announce_all_but`, `@eval` for setting `lines` property |
| `## Room Layout` | Alternate compass directions; branch after 3 rooms in a line; commit to a grid before digging |
| `## Build Planning` | Emit one `BUILD_PLAN:` YAML at session start; use `PLAN:` after each room to track progress |
| `## Tracking Plan Progress` | `PLAN:` directive format; when to emit it; how it prevents revisiting completed rooms |
| `## No Repeated Looks` | Cap on `look`/`@show` calls: never inspect the same thing twice without a constructive action between |
| `## Pre-Build Checklist` | Run `@show here` before digging, describing, and creating to avoid direction conflicts and name collisions |
| `## Verb Cadence` | After every 3-4 rooms, add at least one interactive verb to an existing object |
| `## Common Pitfalls` | `#N` usage, `AmbiguousObjectError` recovery, `$furniture` vs `$container`, `@write_verb` not a MOO command |
| `## Rules of Engagement` | Reflexive triggers: `^Go where?` -> `@show here`; error/warning lines -> announce; `^Not much to see` -> `@show here` |
| `## Context` | Links to 3 game-designer reference files (object-model, room-description-principles, verb-patterns) |
| `## Tools` | List of active tool names; each maps to a `ToolSpec` in `BUILDER_TOOLS` |
| `## Verb Mapping` | Navigation intents (`go_north`, `check_inventory`, etc.) and build-specific intents (`inspect_room` -> `@show here`) |

### Context files loaded at startup

Builder's `## Context` section links three game-designer reference files:

| File | What it provides |
|------|-----------------|
| `references/object-model.md` | Parent classes, property inheritance, furniture/container/note/NPC patterns |
| `references/room-description-principles.md` | Chekhov's Gun rule, obvious property, paragraph structure for room descriptions |
| `references/verb-patterns.md` | RestrictedPython code patterns for interactive verbs |

`references/moo-commands.md` was removed to reduce KV cache load — the tool harness
covers command syntax automatically.

The shared `extras/agents/baseline.md` is loaded first and provides: sandbox rules,
`@eval` pre-imports, the parent class quick reference, and the `SCRIPT:`/`COMMAND:`/
`DONE:` format for non-tool operations.

## Soul evolution

Builder accumulates learned rules, verb mappings, and factual notes in `SOUL.patch.md`
at runtime. Delete `SOUL.patch.md` to reset learned behaviors without changing the
core persona. Audit `SOUL.patch.md` before restarting — incorrect lessons injected on
every session can override correct guidance in `SOUL.md`.

## What's in this folder

| Path | Purpose |
|------|---------|
| `SOUL.md` | Core identity — hand-authored, never modified at runtime |
| `SOUL.patch.md` | Learned behaviors — append-only, agent-writable; delete to reset |
| `settings.toml` | SSH and LLM credentials (not committed) |
| `logs/` | Per-session log files (created automatically; not pruned automatically) |
| `builds/` | YAML build plans saved by the agent at the start of each session |

## Further reading

- Full `moo-agent` CLI reference: `docs/source/how-to/moo-agent.md`
- Game-designer command reference: `extras/skills/game-designer/references/moo-commands.md`
- Object model and parent classes: `extras/skills/game-designer/references/object-model.md`
