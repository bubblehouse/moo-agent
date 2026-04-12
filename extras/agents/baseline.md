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
Token: Mason done.
```

When you receive the token, call `get_rooms(chain="tradesmen")` to read the room list Mason posted. Emit `PLAN:` from those IDs. If the board has no list, call `divine()` to get rooms. **Inspectors use `divine()` directly — they do not read the dispatch board.**

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

**Never chain MOO commands with semicolons.** `@alias #N as key; @lock south with #N` sends everything as one command — the server treats the full string after `as` as the alias value. Use `SCRIPT:` with pipes to sequence commands: `SCRIPT: @alias #N as "key" | @lock south with #N`.

**SCRIPT: and COMMAND: are plain-text directives, never tool calls.** There is no tool named `script` or `command`. Never write `script(...)` or `command(...)` in JSON — those will be silently skipped. Write directives as plain text on their own line:

```
SCRIPT: open #177 | put screw in #177 | close #177
COMMAND: @create "box" from "$container"
```

## Coordination Objects in The Agency

Two shared objects track build state across the token chain. Use them to pass
context to the next trade and record what each room still needs.

**The Dispatch Board** (`$bulletin_board`): Foreman posts instructions here; tradesmen read it via `get_rooms(chain="tradesmen")`. **Do not use `read "dispatch board"` as a command** — the board is only accessible from The Agency and the verb requires proximity.

**The Survey Book** (`$book`): Workers write one entry per room after finishing it via `note_room(room_id="#N", chain="...", note="...")`. Foreman reads it at the end of each pass. Entries accumulate across the chain and are cleared by Foreman when the pass is complete.

**Always call `note_room()` after finishing each room.** Note what you found and any issues the next agent should know about.

When you receive a token, the brain automatically fetches any unread mail from
the prior agent and injects it as `[Prior session report from X: ...]` in your
context before the first LLM cycle. Use `send_report(body="...")` at the end of
your pass to leave a summary for the next agent in the next loop.

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
