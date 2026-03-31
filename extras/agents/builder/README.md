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
provider = "bedrock"
model = "us.anthropic.claude-opus-4-6-v1"
aws_region = "us-east-1"

[agent]
command_rate_per_second = 1.0   # one command/second max; build sequences queue up fine
memory_window_lines = 50        # keep high — build sequences produce verbose output
idle_wakeup_seconds = 300       # builder should only act when instructed; 5-min wakeup
```

## SOUL.md structure

Builder's `SOUL.md` has five sections:

| Section | Contents |
|---------|----------|
| `# Name` | `Builder` |
| `# Mission` | Instructs it to build rooms, objects, exits, NPCs, verbs; emphasises craft and specificity over generic output |
| `# Persona` | Methodical and terse; dry humour; no hedging ("something like") — says the thing itself |
| `## Rules of Engagement` | Reflexive triggers: `^Connected` → `look`; error/warning lines → announce then continue; `^PASSED`/`^FAILED` → report test result |
| `## Context` | Links to game-designer reference files loaded into the system prompt at startup |
| `## Verb Mapping` | Navigation intents (`go_north`, `check_inventory`, etc.) and build-specific intents (`inspect_room` → `@show here`, `audit_objects` → `@audit`) |

### Context files loaded at startup

Builder's `## Context` section links four game-designer reference files:

| File | What it provides |
|------|-----------------|
| `references/moo-commands.md` | Exact syntax for all wizard build commands (`@create`, `@dig`, `@eval`, etc.) |
| `references/object-model.md` | Parent classes, property inheritance, furniture/container/note/NPC patterns |
| `references/room-description-principles.md` | Chekhov's Gun rule, obvious property, paragraph structure for room descriptions |
| `references/verb-patterns.md` | RestrictedPython code patterns for interactive verbs |

The shared `extras/agents/baseline.md` is loaded first and provides: sandbox rules,
`@eval` pre-imports, the parent class quick reference, and the `SCRIPT:`/`COMMAND:`/
`DONE:` response format.

## Soul evolution

Builder accumulates learned rules and verb mappings in `SOUL.patch.md` at runtime.
Delete `SOUL.patch.md` to reset learned behaviors without changing the core persona.

## What's in this folder

| Path | Purpose |
|------|---------|
| `SOUL.md` | Core identity — hand-authored, never modified at runtime |
| `SOUL.patch.md` | Learned behaviors — append-only, agent-writable; delete to reset |
| `settings.toml` | SSH and LLM credentials (not committed) |
| `logs/` | Per-session log files (created automatically; not pruned automatically) |

## Further reading

- Full `moo-agent` CLI reference: `docs/source/how-to/moo-agent.md`
- Game-designer command reference: `extras/skills/game-designer/references/moo-commands.md`
- Object model and parent classes: `extras/skills/game-designer/references/object-model.md`
