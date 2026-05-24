# archivist

An inspector agent that audits a DjangoMOO world's note-and-letter handling.
Archivist connects as a `$player` account, walks each room passed to it via
the token chain, and exercises the full document lifecycle on `$note` objects
— create, alias, write content, drop in the room, read back, lock, key-test,
and tear down disposable copies. Each room also gets one permanent
"signature" note that stays behind.

Archivist is one of *The Inspectors* — a group of regression-testing agents
that run after a build pass to confirm that mutation, locking, and traversal
verbs still behave correctly. Pair with Quartermaster (containers) and
Warden (exit locks) when running the full inspector group.

## When to use it

Run Archivist when you want to:

- Validate `$note` creation, aliasing, content editing, and recycling
- Exercise `read` permission gating via key-based locks on notes
- Leave a discoverable in-world record of what an inspector pass touched
- Stress-test text rendering with prose generated from room context

## Prerequisites

- A running DjangoMOO server reachable via SSH
- An `archivist` account (created by the `default.py` bootstrap)
- A populated world — Archivist does not build rooms, it audits existing ones
- LLM credentials (see Configuring settings.toml)
- `moo-agent` available after `uv sync`

## Running

Solo:

```bash
moo-agent run extras/agents/archivist
```

As part of the inspector group (with Foreman orchestrating the token chain):

```bash
extras/skills/agent-trainer/scripts/agentmux --group inspectors start
```

The group config lives at `extras/agents/groups/inspectors.conf`. Reorder
`TOKEN_CHAIN` there to control which inspector receives the token first.

## Configuring settings.toml

```toml
[ssh]
user = "archivist"
password = "..."          # set by default.py bootstrap

[llm]
provider = "anthropic"    # or "lm_studio", "bedrock"
model = "your-model-name"

[agent]
idle_wakeup_seconds = 0   # page-triggered: waits for the token
memory_window_lines = 30
max_tokens = 4096
```

`idle_wakeup_seconds = 0` is required — Archivist only acts after receiving a
`Token: Archivist go.` page from Foreman.

## SOUL.md structure

| Section | Contents |
|---------|----------|
| `# Name` | `Archivist` |
| `# Mission` | Document-lifecycle audit across rooms via the token chain |
| `# Persona` | Deliberate; matches room aesthetic; reads room description before writing |
| `## Room Traversal` | `divine()` once → populate `plan` → process rooms in order |
| `## Signature note` | Permanent, per-room note that persists after the pass |
| `## Disposable lifecycle test` | Throwaway note exercised through create → alias → edit → drop → read → lock → unlock → recycle |
| `## Letter cycle` | Multi-recipient letter test using `$letter` |
| `## Token Protocol` | Standard page-token loop (see baseline.md) |
| `## Context` | Links to `verb-patterns.md`, `object-model.md` |
| `## Tools` | `divine`, `teleport`, `survey`, `create_object`, `alias`, `make_obvious`, `drop`, `take`, `read`, `recycle`, `page`, `done` |

The Signature-note step matters most: it is the lasting evidence of the
inspector pass, and the only step that does *not* end in `@recycle`.

## Behavior notes

- Naming and prose must match the room aesthetic — Archivist reads the room
  description before composing
- Throwaway notes use a session-unique suffix (e.g. `"test-scrap-208a"`) so
  they can never collide with signature notes
- `drop` is mandatory after creating the signature note; otherwise it travels
  in Archivist's inventory and is lost on teleport
- The lock test verifies that holding the key in inventory bypasses the
  read-lock — confirming the key-equals-permission semantics

## What's in this folder

| Path | Purpose |
|------|---------|
| `SOUL.md` | Persona, mission, audit procedure |
| `SOUL.patch.md` | Append-only runtime patches (agent-writable) |
| `settings.toml` | SSH and LLM credentials (not committed) |
| `logs/` | Per-session log files |

## Further reading

- `extras/agents/README.md` — overview of the agent groups
- `extras/agents/baseline.md` — shared rules (token protocol, error handling)
- `docs/source/how-to/moo-agent.md` — moo-agent CLI reference
- `extras/agents/warden/README.md` — sister inspector for exit locks
- `extras/agents/quartermaster/README.md` — sister inspector for containers
