# harbinger

An autonomous NPC-summoner for DjangoMOO. Harbinger connects as a `$programmer`
account, visits each room Mason has built, and rolls a random number (0–1) to
decide whether to create an NPC. Only rooms that roll ≤ 0.10 get an NPC — roughly
10% of rooms — keeping the world from feeling overrun. Each NPC is a `$player`
child with a `tell` verb override and a `lines` property that drives its dialogue.

Harbinger is one of *The Tradesmen*, four specialized agents intended to run
concurrently on the same MOO instance. Run Harbinger after Mason has built the
room structure.

## When to use it

Run Harbinger when you want to:

- Sprinkle NPCs into a world without overpopulating it
- Give a small number of rooms a present, reactive voice
- Delegate NPC authoring entirely — Harbinger writes personality from the room description

## Prerequisites

- A running DjangoMOO server reachable via SSH
- A `$programmer` account Harbinger can log into (username `harbinger`, created by `default.py` bootstrap)
- Rooms already built by Mason (Harbinger uses `@realm $room` to discover them)
- LLM credentials (see Configuring settings.toml below)
- `moo-agent` available after `uv sync`

## Running

```bash
moo-agent run extras/agents/harbinger
```

## Configuring settings.toml

```toml
[ssh]
user = "harbinger"
password = "Bt6wF5jRcU3e"   # set by default.py bootstrap

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
| `# Name` | `Harbinger` |
| `# Mission` | Create NPCs in ~10% of rooms via random roll; one well-crafted NPC beats five generic ones |
| `# Persona` | Patient, deliberate; finds the right voice for each spirit; avoids generic greetings |
| `## Room Traversal` | `@realm $room` at start; `PLAN:` tracking; `@show here` before rolling |
| `## The Random Roll` | `@eval "import random; print(random.random())"` — proceed only if result ≤ 0.10 |
| `## NPC Creation` | Six-step sequence: `@create`, `@describe`, set `lines` via `@eval`, write `tell` verb, `@move`, `@obvious` |
| `## NPC Scope` | Only `$player` children — never `$thing`, `$furniture`, or `$container` |
| `## Dialogue` | 3–6 lines; atmospheric, specific, odd; no "Hello, traveler." |
| `## Awareness` | "Mason built the rooms. Tinker adds interactive objects. Joiner adds furniture." |
| `## Rules of Engagement` | Reflexive triggers: errors, random result > 0.10 → skip |
| `## Context` | Links: `object-model.md`, `verb-patterns.md` (for `tell` pattern) |
| `## Tools` | `go, create_object, write_verb, alias, show, look, done` |
| `## Verb Mapping` | Navigation intents; inspect/audit shortcuts |

## NPC tell verb pattern

Harbinger's SOUL.md carries the NPC `tell` verb pattern that was removed from
`baseline.md` during the Tradesmen refactor:

```python
import random
from moo.sdk import context
lines = this.get_property('lines')
if lines and args and ': ' in args[0]:
    line = random.choice(lines)
    this.location.announce_all_but(this, f'{this.name} says: {line}')
```

The critical rule: **never call `this.location.announce_all(...)` inside `tell`** —
`announce_all` calls `tell` on every object in the room including the NPC, causing
infinite recursion. Always use `announce_all_but(this, message)`.

## $programmer requirement

Harbinger needs a `$programmer` account because it uses `@edit verb` (to write the
NPC `tell` override) and `@eval` (for the random roll and setting the `lines`
property). The `default.py` bootstrap creates the `harbinger` account as `$programmer`.

## Soul evolution

Harbinger accumulates learned rules in `SOUL.patch.md` at runtime. The most common
stale entries are observations about specific NPCs that no longer exist after a DB
reset. Audit before restarting.

## What's in this folder

| Path | Purpose |
|------|---------|
| `SOUL.md` | Core identity — hand-authored, never modified at runtime |
| `SOUL.patch.md` | Learned behaviors — append-only, agent-writable; delete to reset |
| `settings.toml` | SSH and LLM credentials (not committed) |
| `logs/` | Per-session log files (not pruned automatically) |

## Further reading

- Full `moo-agent` CLI reference: `docs/source/how-to/moo-agent.md`
- Object model and NPC pattern: `extras/skills/game-designer/references/object-model.md`
- Verb patterns for `tell` override: `extras/skills/game-designer/references/verb-patterns.md`
