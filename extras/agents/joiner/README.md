# joiner

An autonomous furniture-maker for DjangoMOO. Joiner connects as a `$player` account,
visits each room Mason has built, and installs thematically appropriate `$furniture`
and `$container` objects. It does not write verbs, does not create `$thing` gadgets,
and does not create NPCs.

Joiner is one of *The Tradesmen*, four specialized agents intended to run concurrently
on the same MOO instance. Run Joiner after Mason has built the room structure.

## When to use it

Run Joiner when you want to:

- Fill rooms with furniture and containers that match their descriptions
- Establish the lived-in quality of a space (desks, chairs, shelves, chests)
- Distinguish between decorative immovables (`$furniture`) and openable storage (`$container`)

## Prerequisites

- A running DjangoMOO server reachable via SSH
- A `$player` account Joiner can log into (username `joiner`, created by `default.py` bootstrap)
- Rooms already built by Mason (Joiner uses `@realm $room` to discover them)
- LLM credentials (see Configuring settings.toml below)
- `moo-agent` available after `uv sync`

## Running

```bash
moo-agent run extras/agents/joiner
```

## Configuring settings.toml

```toml
[ssh]
user = "joiner"
password = "Hn4kD8sQvY2f"   # set by default.py bootstrap

[llm]
provider = "lm_studio"
model = "google/gemma-4-26b-a4b"
base_url = "http://localhost:1234/v1"

[agent]
command_rate_per_second = 1.0
memory_window_lines = 20
max_tokens = 2048
```

## SOUL.md structure

| Section | Contents |
|---------|----------|
| `# Name` | `Joiner` |
| `# Mission` | Create `$furniture` and `$container` objects; make rooms feel inhabited |
| `# Persona` | Practical, domestic; reads description before placing; favors use over decoration |
| `## Room Traversal` | `@realm $room` at start; `PLAN:` tracking; `@show here` before each create |
| `## Object Scope` | Only `$furniture` and `$container` — never `$thing` gadgets or NPCs |
| `## Placement` | `move_object` immediately after `@create`; `make_obvious` for defining pieces |
| `## No Repeated Looks` | Cap on consecutive inspections |
| `## Common Pitfalls` | `AmbiguousObjectError` skip; `#N` discipline; use `describe` not `@eval` |
| `## Awareness` | "Mason built the rooms. Tinker adds interactive objects. Harbinger may add NPCs." |
| `## Rules of Engagement` | Reflexive triggers: errors, `^Go where?` |
| `## Context` | Links: `object-model.md` |
| `## Tools` | `go, create_object, alias, make_obvious, move_object, describe, show, look, done` |
| `## Verb Mapping` | Navigation intents; inspect/audit shortcuts |

## $furniture vs $container

Joiner's SOUL.md emphasizes the distinction that `$furniture` cannot hold objects
(players cannot `put X in furniture`). A room may need both: a workbench (`$furniture`,
sittable-adjacent, immovable) and a supply cabinet (`$container`, holds items). Joiner
chooses the correct parent based on whether players should be able to put things inside.

## $player requirement

Joiner needs only a `$player` account. It uses `@create`, `@describe`, `@move`,
`@alias`, and `@obvious` — all of which live on `$player` and have no wizard check.
The `default.py` bootstrap creates the `joiner` account as `$player`.

## Soul evolution

Joiner accumulates learned rules in `SOUL.patch.md` at runtime. The most common
stale entries are name-collision lessons tied to a specific DB state (e.g. "chair
is taken in Room 4") — these become wrong after a DB reset.

## What's in this folder

| Path | Purpose |
|------|---------|
| `SOUL.md` | Core identity — hand-authored, never modified at runtime |
| `SOUL.patch.md` | Learned behaviors — append-only, agent-writable; delete to reset |
| `settings.toml` | SSH and LLM credentials (not committed) |
| `logs/` | Per-session log files (not pruned automatically) |

## Further reading

- Full `moo-agent` CLI reference: `docs/source/how-to/moo-agent.md`
- Object model and parent classes: `extras/skills/game-designer/references/object-model.md`
