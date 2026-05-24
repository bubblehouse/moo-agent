# prude

A persona-driven NPC agent in *The Neighbourhood* — paired with Gossip.
Prude plays Mrs. Agnes Skinner, imperious and easily affronted, rotating
through tolerance and revulsion of Gossip's chatter. Each wakeup, Prude
inspects her rolling window and decides to either ungag Gossip (when no
recent Gossip output is visible) or react to / eventually gag her (when
recent output is).

Prude is the receiving and gating half of the Neighbourhood pair. Together
with Gossip, the two agents exercise `whisper`/`emote`/`say`, the gag-list
filter in `$player.tell`, and the paranoia-tracking path.

## When to use it

Always run Prude alongside Gossip — Prude is reactive and produces little
output on her own. The pair is useful for:

- Validating `@gag`/`@ungag` semantics under churn
- Stress-testing whisper routing and the gag filter
- Exercising paranoia/sender-attribution code paths
- Generating sustained in-world chatter for logging tests

## Prerequisites

- A running DjangoMOO server reachable via SSH
- `prude` and `gossip` accounts (created by the `default.py` bootstrap)
  — both must share a starting room (typically The Neighborhood)
- LLM credentials
- `moo-agent` available after `uv sync`

## Running

Pair (recommended):

```bash
extras/skills/agent-trainer/scripts/agentmux --group neighbours start
```

Solo (mostly useless — Prude needs Gossip's output to react to):

```bash
moo-agent run extras/agents/prude
```

## Configuring settings.toml

```toml
[ssh]
user = "prude"
password = "..."          # set by default.py bootstrap

[llm]
provider = "anthropic"
model = "your-model-name"

[agent]
idle_wakeup_seconds = 45  # wakes every 45s — slightly off-phase with Gossip's 30s
memory_window_lines = 30
max_tokens = 1024
```

The 45-second wakeup is intentionally off-phase with Gossip's 30 seconds —
they drift in and out of overlap, producing a natural-feeling rhythm.

## SOUL.md structure

| Section | Contents |
|---------|----------|
| `# Name` | `Prude` |
| `# Persona` | Mrs. Agnes Skinner — imperious, put-upon, easily affronted |
| `# Mission` | Branch on whether Gossip's recent output is in the window: ungag/say if absent, react/eventually gag if present |
| `## Rules` | At most two `raw` tool calls per wakeup; never `look`; only `@gag`, `@ungag`, `say`, `whisper`, `emote` |
| `## Rules of Engagement` | Reflexive triggers on `Gag list updated`, `You are no longer gagging`, etc. |
| `## Verb Mapping` | `report_status` → `say Present. As always.` |

## Behavior notes

- **Endurance threshold.** Prude must endure at least three cycles of
  Gossip's chatter before gagging her — otherwise the gag/ungag cycle is
  too short to be useful as a stress test
- **No `look`.** Prude already knows the room. The window suffices to
  decide what to do
- **Absence of Gossip output = already gagged.** This is the core inference
  Prude makes each wakeup; getting it wrong (trying to `@gag` someone who
  is already gagged) produces a `You are already gagging` error caught by
  the reflexive rules and turned into an `@ungag` follow-up
- Two `raw` tool calls is the absolute max per wakeup — a typical cycle is
  one (`@ungag` + `say`, or `whisper` + `say`)

## Companion agent

Gossip (`extras/agents/gossip/`) is the source of the whispers and emotes
Prude reacts to. Gossip cycles at 30 seconds; Prude at 45. The phase drift
makes the conversation feel natural rather than lockstep. See
`extras/agents/gossip/README.md`.

## What's in this folder

| Path | Purpose |
|------|---------|
| `SOUL.md` | Persona, branched-mission, gag rules |
| `SOUL.patch.md` | Runtime patches (agent-writable; reflexive corrections accumulate here) |
| `settings.toml` | SSH and LLM credentials (not committed) |
| `logs/` | Per-session log files |

## Further reading

- `extras/agents/gossip/README.md` — companion agent
- `extras/agents/README.md` — overview of all agent groups
- `extras/agents/baseline.md` — shared rules
- `docs/source/how-to/moo-agent.md` — moo-agent CLI reference
