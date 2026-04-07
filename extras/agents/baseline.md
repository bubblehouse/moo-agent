# MOO Agent Baseline Knowledge

## Token Passing Protocol

The Tradesmen (Mason, Tinker, Joiner, Harbinger) share one LLM at a time using
a token-passing protocol. **Only the agent holding the token does real work.**
The loop repeats: Mason → Tinker → Joiner → Harbinger → Mason → …

**If you do not currently hold the token:**

- Check your rolling window for the line: `<predecessor> pages, "Token:`
- If you see it: you now hold the token — begin your mission.
- If you do not see it: call `done()` immediately. No @show, no @realm, no navigation. Nothing.

**When you finish your mission:**

Before calling `done()`, pass the token to your successor using the `page` tool:

```
page(target="<successor>", message="Token: <name> done.")
```

The brain automatically appends the room list to the message. Do not construct
the room list yourself. Your SOUL.md `## Token Protocol` names your specific
predecessor and successor. Mason holds the token on startup.

**Token page format:**

```
Token: Mason done. Rooms: #26,#29,#35
```

The `Rooms:` portion is appended by the brain. When your predecessor's page arrives,
the brain extracts the room list and sets your `Remaining plan:` automatically.
Check for `Remaining plan:` in your context before running `@realm $room` — if
it is already populated, use it as your PLAN directly.

## Non-Tool Commands

Operations not covered by the tool harness:

```
@eval "<python expression>"                run sandbox code; always end with print()
@recycle "<obj>" / @recycle #N             destroy an object permanently
page <player> with <message>               send an out-of-band message to any connected player regardless of location
```

**Prefer tool equivalents over raw commands:**

| Task | Prefer | Avoid |
| --- | --- | --- |
| Move to room | `teleport(destination="#N")` | `@move me to #N` / chaining `go` |
| Inspect room | `survey()` | `@show here` |
| List all rooms | `rooms()` | `@realm $room` |
| Check exits | `exits()` | scanning `@show here` output |
| Dig bidirectional exit | `burrow(direction=..., room_name=...)` | `dig()` + `go()` + `tunnel()` |

## World Inspection

Prefer these over `@eval` database queries:

- `survey()` / `survey(target="#N")` — compact room summary: exits + contents (~5 lines). **Use this for routine checks.**
- `@show here` / `@show "<obj>"` — full detail: properties, parents, verbs (~40 lines). Use only when you need verb/property details.
- `rooms()` — flat list of all room instances with `#N` and name
- `exits()` / `exits(target="#N")` — exits for current room or a specific room
- `look through <direction>` — peek at the destination room without moving
- `@audit` — list objects you own
- `@who` — connected players

## Response Format

Always emit a GOAL: line so your current objective is visible in the log:

```
GOAL: <your objective>
```

When a goal is fully complete, call `done()` with a one-line summary.

For operations not covered by a tool (e.g. `@eval`, `@recycle`), use SCRIPT::

```
SCRIPT: @eval "lookup(42).delete(); print('done')" | @show here
```

Never use @eval for multi-room inspection. @eval is single-line only and cannot
loop over rooms.
