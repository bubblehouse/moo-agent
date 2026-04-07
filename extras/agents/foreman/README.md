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
| `## Stall Detection` | Uses `say` anchors to measure elapsed wakeup cycles per agent |

## Stall recovery

Foreman detects stalls by counting wakeup cycles after a relay `say` line with no
done response. After 3 cycles (~3 minutes) it pages the stuck agent. After 3
unanswered alerts it emits a `say` alerting the operator. It cannot restart agent
processes — that requires manual intervention.

## What Foreman never does

- Creates objects, rooms, or verbs
- Calls `done()` (runs indefinitely)
- Modifies the world in any way
