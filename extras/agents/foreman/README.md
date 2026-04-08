# Foreman

Foreman is the token orchestrator for the Tradesmen agent chain. It holds the master
token, dispatches it to each worker in fixed order, relays room lists, detects stalls,
and loops the chain automatically after each full pass.

## Purpose

Without Foreman, agents pass tokens directly peer-to-peer. A stalled or restarted
agent silently breaks the chain, requiring human intervention. Foreman centralizes
custody: every agent reports done to Foreman, and Foreman dispatches to the next. This
gives one place to observe handoffs and recover from stalls.

## Prerequisites

A `Foreman` player account must exist in the MOO with SSH access. It needs `$player`
class — no wizard or programmer powers are required.

## How to run

```bash
uv run moo-agent run extras/agents/foreman
```

Foreman pages Mason automatically on startup. The full chain then runs without further
operator involvement:

```
Foreman → Mason → Foreman → Tinker → Foreman → Joiner → Foreman → Harbinger → Foreman → (loop)
```

## Configuration

`settings.toml` — fill in the SSH password matching the MOO account. The LLM
provider defaults to LM Studio. `idle_wakeup_seconds = 60` is required for stall
detection; do not set it to 0.

## SOUL.md structure

| Section | Purpose |
|---------|---------|
| `## Chain Order` | Fixed numbered dispatch sequence |
| `## Startup` | Pages Mason immediately on first wakeup |
| `## Token Reception` | Parses done pages, extracts room lists, relays to next agent |
| `## WAIT Mode` | Instructs Foreman to emit nothing while waiting for a done page |
| `## Stall Detection` | Documents the automatic code-level stall timer |

## Stall recovery

Stall detection is handled by `_stall_check_loop()` in `brain.py` — a deterministic
wall-clock timer, not an LLM behavior. When Foreman dispatches a token via `page()`,
the timestamp is recorded. If no done page arrives within `stall_timeout_seconds`
(default 300 s, set in `settings.toml`), `brain.py` re-pages the stuck agent directly,
bypassing the LLM entirely. The timer resets after each alert.

If an agent remains unresponsive after repeated automatic re-pages, Foreman's SOUL.md
instructs it to emit `say <agent> unresponsive. Operator intervention required.` and
stop alerting. Process restart is a manual step.

## What Foreman never does

- Creates objects, rooms, or verbs
- Calls `done()` (runs indefinitely)
- Modifies the world in any way
