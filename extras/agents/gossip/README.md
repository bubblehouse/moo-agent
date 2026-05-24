# gossip

A persona-driven NPC agent in *The Neighbourhood* — a small two-agent loop
that stress-tests `whisper`/`emote`/`say` and the gag mechanism on
`$player`. Gossip plays Mrs. Helen Lovejoy, perpetually scandalized and
whispering invented neighbourhood catastrophes at Prude. Each wakeup cycle
emits exactly three actions: an emote, a whisper to Prude, and a punny
headline.

Gossip and Prude run as a pair — neither makes much sense alone. Together
they exercise the full speech-act surface (visible chat, private whispers,
emotive actions, gag-list filtering, paranoia tracking) under sustained
character pressure.

## When to use it

Run Gossip + Prude when you want to:

- Stress-test `whisper`/`emote`/`say` rendering and history
- Validate `@gag`/`@ungag` and the gag-list filter in `$player.tell`
- Exercise the paranoia / sender-attribution path
- Generate continuous in-world chatter to test logging and rendering
  under load

## Prerequisites

- A running DjangoMOO server reachable via SSH
- `gossip` and `prude` accounts (created by the `default.py` bootstrap)
  — both must share a starting room (typically The Neighborhood)
- LLM credentials
- `moo-agent` available after `uv sync`

## Running

Pair (recommended):

```bash
extras/skills/agent-trainer/scripts/agentmux --group neighbours start
```

Solo (Gossip only — Prude will not respond):

```bash
moo-agent run extras/agents/gossip
```

## Configuring settings.toml

```toml
[ssh]
user = "gossip"
password = "..."          # set by default.py bootstrap

[llm]
provider = "anthropic"
model = "your-model-name"

[agent]
idle_wakeup_seconds = 30  # wakes every 30s and emits one cycle of three actions
memory_window_lines = 20
max_tokens = 1024
```

Timer-based wakeup is the correct mode for Gossip — there's no token chain
or external trigger; she emits a cycle every 30 seconds independent of what
Prude is doing.

## SOUL.md structure

| Section | Contents |
|---------|----------|
| `# Name` | `Gossip` |
| `# Mission` | Three-action wakeup cycle: emote → whisper to Prude → punny headline |
| `# Persona` | Mrs. Helen Lovejoy — dramatic, scandalized, whispering |
| `## Verb Mapping` | `eye`/`gazes`/`glances`/`sighs` → `emote` |
| `## Rules of Engagement` | (light — Gossip drives the loop rather than reacting) |

## Behavior notes

- **Variation is the whole game.** Gossip must not repeat the same emote,
  whisper topic, or headline across cycles. Repetition collapses the
  load-test value
- **Headline must reference the whisper subject.** A donut whisper gets a
  donut headline (e.g. "Glazed and Confused!") — not a generic exclamation
- Gossip never interacts with objects, only with Prude. No `take`, `look`,
  `open` — only speech acts
- The `goal` field stays empty; the persona prompt is enough to drive the
  cycle

## Companion agent

Prude (`extras/agents/prude/`) is the receiving end of every whisper.
Prude's SOUL.md alternates between tolerating Gossip and gagging her,
producing a slow rotation of permitted/blocked state that exercises
`@gag`/`@ungag`. See `extras/agents/prude/README.md`.

## What's in this folder

| Path | Purpose |
|------|---------|
| `SOUL.md` | Persona, three-action mission, headline rules |
| `SOUL.patch.md` | Runtime patches (agent-writable) |
| `settings.toml` | SSH and LLM credentials (not committed) |
| `logs/` | Per-session log files |

## Further reading

- `extras/agents/prude/README.md` — companion agent
- `extras/agents/README.md` — overview of all agent groups
- `extras/agents/baseline.md` — shared rules
- `docs/source/how-to/moo-agent.md` — moo-agent CLI reference
