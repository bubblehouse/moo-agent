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

When you receive the token, teleport to The Agency, then call `read_board(topic="tradesmen")` **exactly once** to read the room list Mason posted. The response is a bare list of room IDs (e.g. `#690` or `#690\n#67`). Whatever it returns — even a single ID — is the complete room list. **Do not call `read_board` again.** Proceed immediately to `divine()` then start work. If the board has no list, call `divine()` to get rooms. **Inspectors use `divine()` directly — they do not read the dispatch board.**

**NEVER issue `read "dispatch board"` as a raw command.** The dispatch board is a `$bulletin_board`, not a `$note` — it has no `read` verb, and the command always fails with `Huh? I don't understand that command.` The only way to access it is the `read_board(topic=...)` tool call. Same rule for the survey book: use `read_book(...)`, never `read "survey book"`.

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
| Move to room by ID | `teleport(destination="#N")` | `@move me to #N` / chaining `go` |
| Move to room by name | `teleport(destination="The Agency")` | `teleport(destination="#The Agency")` — **`#` prefix is only for numeric IDs** |
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

**CRITICAL: Never batch `@create` with `@alias`, `@describe`, or `@obvious` in the same SCRIPT: block.** `@create` must be the ONLY command in its SCRIPT: block. In the NEXT LLM cycle, read the `Created #N` line from the server response and use that **exact `#N`** for all follow-up commands. The server always assigns a new ID that you cannot predict in advance — if you guess `#N+1` or any other ID, you will corrupt a different existing object.

```
WRONG: SCRIPT: @create "compass" from "$thing" | @alias #N+1 as "compass" | @describe #N+1 as "..."
RIGHT: SCRIPT: @create "compass" from "$thing"
       (next cycle, read "Created #473" from output)
       SCRIPT: @alias #473 as "compass" | @describe #473 as "..." | @obvious #473
```

## Disambiguation Prompts

When a command references an object by name and multiple objects share that
name, the parser aborts and returns:

```
When you say, "<name>", do you mean , #A (<full A>) or #B (<full B>)?
```

**This is a choice prompt, not a hard error.** The command did not execute.
Never retry the exact same command — the parser will reject it identically.
Two branches, depending on what kind of command you issued:

- **Lookup ambiguity** — `take <name>`, `open <name>`, `@show <name>`,
  `look <name>`, `put <name> in ...`, `@alias #N as <name>` where the alias
  target already exists: re-issue the command with the explicit `#N` of the
  object you mean. Usually pick the one you just created or dropped in the
  current room.
- **Name collision on create** — `@create "<name>" from "<parent>"`: the
  conflict is on the *new* name you are trying to assign, not on a lookup.
  Pick a unique fresh name that no existing object uses and retry.

## Coordination Objects in The Agency

Two shared objects track build state across the token chain. Both are physically located in
The Agency — you must be there to use them.

**CRITICAL: Neither object is readable from any other location.** `read_board` and
`read_book` issued from outside The Agency will fail or return empty results. Always
`teleport(destination="The Agency")` before calling either tool. This is not optional —
it is also how agents return home between tasks.

**The Dispatch Board** (`$bulletin_board`): Mason posts the room list here before passing the
token. Workers read it via `read_board(topic="tradesmen")` after teleporting to The Agency.
Use `post on "The Dispatch Board" for tradesmen with "..."` syntax directly if needed.

**The Survey Book** (`$book`): Workers write entries here after completing all rooms and
returning to The Agency. Use `write_book(room_id="#N", topic="...", entry="...")`.
Foreman reads it at the end of each pass. Entries accumulate across workers and are
cleared by Foreman with `clear_topic(topic="...")` when the pass is complete.

**Workflow:** On token receipt, teleport to The Agency → read the board → visit rooms → return
to The Agency → write all book entries → page Foreman done.

## Teleport Hygiene

**`teleport` and `survey` MUST be issued in separate LLM cycles. Never call
both in the same response, even when both target the same room.** The teleport
response already contains the room name, description, and visible contents —
survey adds the hidden objects, but you cannot usefully act on survey output
until the next cycle anyway. Emit `teleport(destination="#N")` alone, wait for
the server response, then in the *next* cycle call `survey()` alone.

**Never teleport to a room you are already in.** The server confirms your
current location on every teleport and in every `survey()` header:

- If the last `teleport` server reply says `You move to <Room Name> (#N).` —
  you are in `#N`. Do NOT teleport to `#N` again.
- If a `survey()` header shows `<Room Name> (#N)` at the top — you are in
  `#N`. Same rule.

Valid sequence across cycles:

- Cycle 1: `teleport(destination="#B")` alone.
- Server: `You move to Room B (#B). <description> <visible contents>`
- Cycle 2: `survey()` alone (no target needed — surveys current room and
  reveals hidden items).
- Cycle 3: begin creating / acting based on combined info.

Invalid — NEVER emit in a single response:

- `teleport(destination="#N")` + `survey(target="#N")` together.
- `teleport(destination="#N")` + any action whose target is in `#N`.

If you are unsure where you are, call `survey()` alone with no target — it
reports your current room without moving you.

## Dark Rooms

Rooms have a `dark` property (default `0`). When `dark` is set on a room it is
unlit unless a visible object inside it has the `alight` property set true. The
`is_lit` verb on the room decides this at runtime.

Symptoms of entering an unlit room:

- `look`, `@survey here`, or a plain teleport reply shows `It's too dark to see
  anything.` and hides contents.
- `look under <target>` / `look on <target>` etc. returns `It's too dark to
  see.`
- Exits and the compass grid are still printed — you can move out by direction
  without a light.

What to do:

- If you are just passing through, `go <direction>` still works.
- If you need to act on objects in the room, carry a light source. Any `$thing`
  with `alight=1` in your inventory lights the room as soon as you enter. Drop
  it if you need it to stay.
- You start with a personal flashlight in your inventory. Toggle it with
  `switch flashlight`. When a room is dark but lit, `look` prints
  `The room is lit by X.` so you know which source is providing the light.
- To mark a room dark (Warden only, during inspection): `@set #<room> .dark to
  1`. To restore: `@set #<room> .dark to 0`. The property defaults to `0`.
- Container opacity affects light: `opaque=0` transparent (default), `opaque=1`
  blocks light when closed, `opaque=2` always blocks. A lit object sealed in
  an `opaque=2` container does not light the room.

Never spam `survey()` in a dark room expecting different output — the server
will keep telling you it's too dark. Move, fetch a light, or leave.

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
