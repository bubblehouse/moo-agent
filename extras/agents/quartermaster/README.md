# quartermaster

An inspector agent that audits a DjangoMOO world's container handling.
Quartermaster connects as a `$player` account, walks each room passed to it
via the token chain, and exercises the full container lifecycle —
`@create $container`, alias, describe, `open`/`close`, `put`/`take`,
`@opacity`, `@lock_for_open`, and placement prepositions. Quartermaste
re-uses any pre-existing `$container` it finds before creating a new one.

Quartermaster is one of *The Inspectors* — a group of regression-testing
agents that run after a build pass. Pair with Archivist (notes) and Warden
(exit locks) when running the full inspector group.

## When to use it

Run Quartermaster when you want to:

- Validate container `open`/`close`, `put`/`take`, and opacity flags
- Exercise `@lock_for_open` key-based locking on containers
- Stress-test container placement prepositions (`on`, `under`, `behind`, …)
- Confirm a fresh world's containers all accept items without permission errors

## Prerequisites

- A running DjangoMOO server reachable via SSH
- A `quartermaster` account (created by the `default.py` bootstrap)
- A populated world with at least some rooms — Quartermaster audits, doesn't build
- LLM credentials
- `moo-agent` available after `uv sync`

## Running

Solo:

```bash
moo-agent run extras/agents/quartermaster
```

As part of the inspector group:

```bash
extras/skills/agent-trainer/scripts/agentmux --group inspectors start
```

## Configuring settings.toml

```toml
[ssh]
user = "quartermaster"
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
| `# Name` | `Quartermaster` |
| `# Mission` | Container/opacity/locking audit across rooms via the token chain |
| `# Persona` | Methodical, precise; reuses existing containers; matches room aesthetic |
| `## Room Traversal` | `divine()` → populate `plan` → teleport to each room |
| `## Per-room procedure` | Survey for existing `$container`; reuse or create; open → put → close → opacity → lock cycle |
| `## Placement cycle` | Tests `on`/`under`/`behind` placement prepositions on a test item |
| `## Token Protocol` | Standard page-token loop |
| `## Context` | Links to `verb-patterns.md`, `object-model.md` |
| `## Tools` | `divine`, `teleport`, `survey`, `create_object`, `alias`, `describe`, `open`, `close`, `put`, `take`, `move_object`, `lock_for_open`, `unlock`, `page`, `done` |

## Behavior notes

- **Reuse first.** Quartermaster always surveys the room before creating; if
  a `$container` already lives there, it audits that one instead of making
  another
- Created objects land in Quartermaster's inventory — container verbs all
  work from inventory; placement back into the room only happens at the end
  via `move_object(obj=..., destination="here")`
- Material vocabulary is varied — Quartermaster's persona note explicitly
  avoids re-using the same material (e.g. "brass") for every test container
- A failed `open`/`close`/`put` is real evidence; Quartermaster reports it
  exactly and continues to the next room rather than retrying

## What's in this folder

| Path | Purpose |
|------|---------|
| `SOUL.md` | Persona, mission, container procedure |
| `SOUL.patch.md` | Runtime patches (agent-writable) |
| `settings.toml` | SSH and LLM credentials (not committed) |
| `logs/` | Per-session log files |

## Further reading

- `extras/agents/README.md` — overview of the agent groups
- `extras/agents/baseline.md` — shared rules
- `docs/source/how-to/moo-agent.md` — moo-agent CLI reference
- `extras/agents/archivist/README.md` — sister inspector for notes/letters
- `extras/agents/warden/README.md` — sister inspector for exit locks
