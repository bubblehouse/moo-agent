# tinker

An autonomous object-maker for DjangoMOO. Tinker connects as a `$programmer` account,
visits each room Mason has built, and installs interactive `$thing` objects appropriate
to the room's theme. It can also implement secret exits as verbs on objects. It does
not create `$furniture`, `$container`, or NPCs.

Tinker is one of *The Tradesmen*, four specialized agents intended to run concurrently
on the same MOO instance. Run Tinker after Mason has built the room structure.

## When to use it

Run Tinker when you want to:

- Populate rooms with thematic, interactive objects autonomously
- Add secret exits (lever-behind-a-painting, loose-brick patterns) without manual authoring
- Verify that objects produce correct verb output

## Prerequisites

- A running DjangoMOO server reachable via SSH
- A `$programmer` account Tinker can log into (username `tinker`, created by `default.py` bootstrap)
- Rooms already built by Mason (Tinker uses `@realm $room` to discover them)
- LLM credentials (see Configuring settings.toml below)
- `moo-agent` available after `uv sync`

## Running

```bash
moo-agent run extras/agents/tinker
```

## Configuring settings.toml

```toml
[ssh]
user = "tinker"
password = "Pw9cX3mZrT6y"   # set by default.py bootstrap

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
| `# Name` | `Tinker` |
| `# Mission` | Create interactive `$thing` objects; implement secret exits via verbs |
| `# Persona` | Inventive, precise; reads room description before creating anything |
| `## Room Traversal` | `@realm $room` at start; `PLAN:` tracking; `@show here` before each create |
| `## Object Scope` | Only `$thing` — never `$furniture`, `$container`, or `$player` NPCs |
| `## Secret Exits` | Verb body using `context.player.move(dest)` |
| `## Verb Dispatch` | `--dspec`/`--iobj` specs; `context.parser.get_pobj()`; `--on #N` requirement |
| `## Verb Testing` | REQUIRED: test call in the same `SCRIPT:` as `@edit verb` |
| `## Verb Cadence` | One verb per object; no more than two without a strong reason |
| `## No Repeated Looks` | Cap on consecutive inspections |
| `## Common Pitfalls` | `$note` intercept; `AmbiguousObjectError` recovery; `#N` discipline |
| `## Awareness` | "Mason built the rooms. Joiner adds furniture. Harbinger may add NPCs." |
| `## Rules of Engagement` | Reflexive triggers: errors, test pass/fail, `^Go where?` |
| `## Context` | Links: `object-model.md`, `verb-patterns.md` |
| `## Tools` | `go, create_object, write_verb, alias, make_obvious, move_object, show, look, done` |
| `## Verb Mapping` | Navigation intents; inspect/audit shortcuts |

## Verb dispatch knowledge

Tinker's SOUL.md carries the `## Verb Dispatch` and `## Verb Testing` sections
that were removed from `baseline.md` during the Tradesmen refactor. These sections
cover `--dspec`/`--iobj` shebang flags, `context.parser.get_pobj()`, the `--on #N`
requirement, and the mandatory post-write test call. Tinker is the only Tradesman
that writes verbs on objects other than NPCs, so the detail lives here rather than
in baseline.

## $programmer requirement

Tinker needs a `$programmer` account because it uses `@edit verb` and `@eval`.
These verbs live on `$programmer`, not `$player`. The `default.py` bootstrap creates
the `tinker` account as `$programmer`.

## Soul evolution

Tinker accumulates learned rules in `SOUL.patch.md` at runtime. Audit before
restarting — the most common corrupt entry is a wrong lesson about `@edit verb`
syntax that disables all verb writing.

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
- Verb patterns for interactive objects: `extras/skills/game-designer/references/verb-patterns.md`
