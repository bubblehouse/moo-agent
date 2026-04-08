# MOO Agent Baseline Knowledge

## Token Passing Protocol

The Tradesmen (Mason, Tinker, Joiner, Harbinger, Stocker) share one LLM at a time
using a token-passing protocol. **Only the agent holding the token does real work.**
The chain repeats: Foreman → Mason → Tinker → Joiner → Harbinger → Stocker → (back to Mason)

All worker agents use page-triggered mode — they wake only when a page arrives and
do nothing while idle. **Wait for a page containing `Token:` before starting any work.**

**When you finish your mission:**

Before calling `done()`, pass the token back to Foreman:

```
page(target="foreman", message="Token: <YourName> done.")
done(summary="...")
```

Call `page()` first in its own tool response. Wait for `Your message has been sent.`
before calling `done()` alone in a separate response. Never batch them.

**Token page format:**

```
Token: Mason done. Rooms: #9,#22
```

The `Rooms:` portion is appended by the brain — do not construct it yourself. When
Foreman relays the token to you, the brain extracts the room list and sets your
`Remaining plan:` automatically. Check for `Remaining plan:` in your context before
calling `rooms()` — if it is already populated, emit `PLAN:` from that list directly.

**On reconnect:** If you restart mid-session and the system log shows
`Resuming from prior session` with an active goal, page Foreman immediately so it
can relay the token without waiting for the stall timer:

```
page(target="foreman", message="Token: <YourName> reconnected.")
```

Replace `<YourName>` with your agent name (e.g., `Tinker`, `Joiner`, `Stocker`).
Then wait for Foreman's token page before beginning any work.

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

## Rules of Engagement

- `^WARNING:` -> say Warning logged. Continuing.
- `^Go where\?` -> survey()
- `^Not much to see here` -> survey()

## Verb Mapping

- look_around -> look
- check_location -> look
- go_north -> go north
- go_south -> go south
- go_east -> go east
- go_west -> go west
- go_up -> go up
- go_down -> go down
- go_northwest -> go northwest
- go_northeast -> go northeast
- go_southwest -> go southwest
- go_southeast -> go southeast
- go_home -> home
- check_inventory -> inventory
- inspect_room -> @survey here
- teleport_to -> teleport #N
- list_rooms -> @rooms
- audit_objects -> @audit
- check_who -> @who
