# warden

An inspector agent that audits a DjangoMOO world's exit-locking and lighting.
Warden connects as a `$player` account, walks each room passed to it via the
token chain, and exercises `@lock`/`@unlock` on exits using a master key
provisioned at bootstrap. A random fraction of rooms also get darkened so
later inspector passes have to deal with unlit rooms.

Warden is one of *The Inspectors* — a group of regression-testing agents
that run after a build pass. Pair with Archivist (notes) and Quartermaster
(containers) when running the full inspector group.

## When to use it

Run Warden when you want to:

- Validate `@lock <direction> with <key>` and the keyed-exit traversal path
- Confirm `unlock` cleanly restores an exit's pre-test state
- Sprinkle darkened rooms into the world so the next inspector pass has to
  navigate lighting
- Verify the bootstrap-provisioned master key works for cross-room locking

## Prerequisites

- A running DjangoMOO server reachable via SSH
- A `warden` account (created by the `default.py` bootstrap) holding the
  `warden's master key` object in inventory
- A populated world with at least some exits — Warden audits, doesn't build
- LLM credentials
- `moo-agent` available after `uv sync`

## Running

Solo:

```bash
moo-agent run extras/agents/warden
```

As part of the inspector group:

```bash
extras/skills/agent-trainer/scripts/agentmux --group inspectors start
```

## Configuring settings.toml

```toml
[ssh]
user = "warden"
password = "..."          # set by default.py bootstrap

[llm]
provider = "anthropic"
model = "your-model-name"

[agent]
idle_wakeup_seconds = 0   # page-triggered
memory_window_lines = 30
max_tokens = 4096
```

Page-triggered mode (`idle_wakeup_seconds = 0`) is required.

## SOUL.md structure

| Section | Contents |
|---------|----------|
| `# Name` | `Warden` |
| `# Mission` | Exit-locking audit across rooms via the token chain; randomized darkening |
| `# Persona` | Methodical, cautious; surveys before acting; leaves exits as found |
| `## Room Traversal` | `divine()` → populate `plan` → walk each room in order |
| `## Per-room procedure` | 13 steps: survey, grant_write on exit, drop key, lock, fail-go, take key, succeed-go, teleport back, unlock, optional darken, return to The Agency, write book entry |
| `## Darkening Sub-Procedure` | d3 roll per room; ≈1/3 of rooms get a permanent darkening property |
| `## Token Protocol` | Standard page-token loop |
| `## Context` | Links to `verb-patterns.md`, `object-model.md` |
| `## Tools` | `divine`, `teleport`, `survey`, `grant_write`, `drop`, `take`, `write_book`, `page`, `done` |

## Behavior notes

- **Single master key for the whole session.** Warden never creates new keys
  per room. The `warden's master key` is provisioned by the bootstrap and its
  `#N` is captured once via `@audit` at the start of the pass
- **Always unlock before leaving.** Step 10 is non-skippable — a left-locked
  exit poisons every subsequent inspector pass
- **The Agency (`#23`) is never darkened**, regardless of d3 roll, because
  it's the shared start room
- After each room, Warden writes a one-line entry into a shared inspector
  book via `write_book(room_id=..., topic="inspectors", entry=...)` — the
  book serves as a durable audit trail across sessions

## What's in this folder

| Path | Purpose |
|------|---------|
| `SOUL.md` | Persona, mission, lock-test procedure |
| `SOUL.patch.md` | Runtime patches (agent-writable) |
| `settings.toml` | SSH and LLM credentials (not committed) |
| `logs/` | Per-session log files |

## Further reading

- `extras/agents/README.md` — overview of the agent groups
- `extras/agents/baseline.md` — shared rules
- `docs/source/how-to/moo-agent.md` — moo-agent CLI reference
- `extras/agents/archivist/README.md` — sister inspector for notes/letters
- `extras/agents/quartermaster/README.md` — sister inspector for containers
