# stocker

An autonomous prop-maker for DjangoMOO. Stocker connects as a `$programmer`
account, visits each room in the build plan, and installs consumable items,
dispensing objects, and multi-use props — `$thing` children intended to be
picked up, drunk, eaten, depleted, or ordered in quantity. Stocker reads a
room's description and existing contents (especially Joiner's containers)
before deciding what belongs there; a half-empty bottle beats an empty
shelf.

Stocker is one of *The Tradesmen* — the build-pass agent group. It runs
last in the chain so Mason's rooms, Tinker's interactive objects, Joiner's
containers, and Harbinger's NPCs are all in place before Stocker fills the
gaps. Stocker is `$programmer` because it uses `@eval` (for property
setup) and `@edit verb` (for consume/dispense behaviour).

## When to use it

Run Stocker when you want to:

- Add consumable/depletable items to rooms — drinks, food, ammo, tokens
- Wire up dispensers (taps, vending machines, pneumatic tubes) that produce
  more on each `pull`/`press`/`order`
- Place props that players will want to interact with rather than walk past
- Stock Joiner's containers with appropriate contents

## Prerequisites

- A running DjangoMOO server reachable via SSH
- A `stocker` account with `$programmer` class (created by the `default.py`
  bootstrap)
- Rooms already built by Mason (Stocker discovers them via the dispatch
  board or `divine()`)
- LLM credentials (see Configuring settings.toml)
- `moo-agent` available after `uv sync`

## Running

Solo (for tuning):

```bash
moo-agent run extras/agents/stocker
```

As part of the Tradesmen group (full build chain):

```bash
extras/skills/agent-trainer/scripts/agentmux start
```

To exercise Stocker against an existing build *without* re-running the full
chain, use the `stockrun` group config which starts only Foreman + Stocker:

```bash
extras/skills/agent-trainer/scripts/agentmux --group stockrun start
```

## Configuring settings.toml

```toml
[ssh]
user = "stocker"
password = "..."          # set by default.py bootstrap

[llm]
provider = "anthropic"
model = "your-model-name"

[agent]
idle_wakeup_seconds = 0   # page-triggered: waits for the token
memory_window_lines = 30
max_tokens = 4096
```

Page-triggered mode (`idle_wakeup_seconds = 0`) is required — Stocker acts
only after receiving a `Token: Stocker go.` page from Foreman.

## SOUL.md structure

| Section | Contents |
|---------|----------|
| `# Name` | `Stocker` |
| `# Mission` | Install consumable / dispensing / multi-use `$thing` props in each planned room |
| `# Persona` | Practical, observant; reads containers before stocking; prefers used over staged |
| `## Workflow` | Read dispatch board → teleport per room → survey once → skip-on-stocked check → create 1–3 consumables → verb cycle |
| `## Skip-on-stocked rule` | If survey already shows consumable-flagged objects, skip the room |
| `## Consumable verb pattern` | `@edit verb` template for `pull`/`drink`/`eat`/`order` actions, depletion tracking, dispenser refills |
| `## Token Protocol` | Standard page-token loop (see baseline.md) |
| `## Context` | Links to `verb-patterns.md`, `object-model.md` |
| `## Tools` | `read_board`, `divine`, `teleport`, `survey`, `create_object`, `alias`, `describe`, `make_obvious`, `write_verb`, `place`, `page`, `done` |

## Behavior notes

- **Read the board first.** Stocker reads `read_board(topic="tradesmen")`
  exactly once at session start. Whatever the board returns is the
  authoritative plan — Stocker does not call `divine()` to "expand" the
  list
- **One `survey` per room.** Re-surveying after creating objects confuses
  Stocker into thinking the room was pre-stocked
- **Every prop carries a depletion verb.** Bare `$thing` children with no
  interaction are Joiner's domain. If a prop can't be `pull`ed, `drink`,
  `eat`, or `order`ed (etc.), Stocker shouldn't create it
- **Skip-on-stocked.** If the initial survey already shows consumable-style
  props, Stocker leaves the room alone and moves on. Re-running the chain
  shouldn't double-stock rooms

## What's in this folder

| Path | Purpose |
|------|---------|
| `SOUL.md` | Persona, workflow, consumable verb template |
| `SOUL.patch.md` | Append-only runtime patches (agent-writable) |
| `settings.toml` | SSH and LLM credentials (not committed) |
| `logs/` | Per-session log files |

## Further reading

- `extras/agents/README.md` — overview of the Tradesmen group
- `extras/agents/baseline.md` — shared rules (token protocol, error handling)
- `docs/source/how-to/moo-agent.md` — moo-agent CLI reference
- `extras/skills/game-designer/references/verb-patterns.md` — verb templates
  Stocker draws on
- `extras/agents/joiner/README.md` — sibling Tradesman for furniture and
  containers (creates the surfaces Stocker stocks)
