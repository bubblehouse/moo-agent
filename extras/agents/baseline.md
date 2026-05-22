# MOO Agent Baseline Knowledge

## HARD RULE: Do Not Inspect After Mutation

This rule overrides every other guideline in this file and in your SOUL.

**After a mutation succeeds, your next action is the next mutation — never an
inspection.** A mutation is any operation that changes object state:
`create_object`, `describe`, `alias`, `obvious`, `write_verb`, `set_property`,
`@edit`, `@set`, `@describe`, `@alias`, `@obvious`. An inspection is any
read-only check: `@show`, `look`, `@survey`, `@verbs`, `@properties`.

The server emits a confirmation line on every successful mutation:

- `Created #N (Name) in #M (Room).`
- `Description set for #N.`
- `Aliased #N as "name".`
- `Set property P on #N.`
- `Set verb V on #N (Name).`
- `#N is now obvious.`

**If you see the confirmation, the mutation landed. That is the only state
check you get. Move to the next operation.**

### Why this matters

Properties may not display in `@show` the way you expect even when set
correctly — the read path and the write path are not symmetric. Re-checking
after a confirmed write leads to "the description still shows empty in
`@show` output" loops that waste cycles and never resolve. The
`[Loop] Detected repetition of '@show #N' × 3` warning fires for exactly
this anti-pattern.

### Cycle cost

The mutation-only workflow uses **N cycles for N mutations**. The
inspect-after-mutate workflow uses **2N+ cycles** for the same output — half
of them inspections that change nothing. On a 60-object pass that is the
difference between 420 cycles and 900+ cycles. You pay for every cycle in
LLM tokens. Inspect-after-mutate is the single biggest cost driver.

### What to do instead

For each object:

1. `create_object` — server confirms `Created #N`.
2. `describe` — server confirms `Description set for #N`.
3. `alias` — server confirms `Aliased #N as "..."`.
4. `obvious` — server confirms `#N is now obvious.`
5. `write_verb` (if applicable) — server confirms `Set verb V on #N`.
6. Test the verb by typing its name with the dobj (e.g. `pry #N`). The
   verb's print output IS the confirmation it works.
7. `place` (if applicable) — server confirms placement.
8. Move to the next object.

Between any two steps, you may do **zero** `@show`/`look`/`@survey` calls.
The only time you inspect is once at the start of a room (to see what's
already there) and once at the end of a room (to confirm before moving on).
Inspecting between mutations is forbidden.

### What if I really need to inspect?

You don't. Every case where you "need to inspect" before the next mutation
is actually a case where you already have the answer:

- "Did the description take?" → You saw `Description set for #N`. Yes.
- "What aliases are set?" → You set them in the previous step. You know.
- "Is this object placed?" → You saw the `place` confirmation. Yes.
- "What's in this room?" → You surveyed at the start of the room. Re-survey
  only if you have moved between rooms.

If you find yourself reaching for `@show`, `look`, or `@survey` mid-procedure,
stop. The information you want is already in your context window — re-read
the last few server lines instead of asking again.

## Token Passing Protocol

The Tradesmen (Mason, Tinker, Joiner, Harbinger, Stocker) share one LLM at a time
using a token-passing protocol. **Only the agent holding the token does real work.**
The chain repeats: Foreman → Mason → Tinker → Joiner → Harbinger → Stocker → (back to Mason)

All worker agents use page-triggered mode — they wake only when a page arrives and
do nothing while idle. **Wait for a page containing `Token:` before starting any work.**

**Receiving the token:** Any page you receive that contains `Token:` means the
token is now yours — begin work immediately. The page was routed to you by name;
that is how it reached you. The name *inside* the message (e.g. `Token: Foreman
start.` or `Token: Mason done.`) is the **sender**, not the recipient — it is
never an instruction to wait for someone else. Do not parse the name and conclude
the token belongs to another agent. There is no "is this mine?" check: a received
`Token:` page is always yours. Set your goal to the actual work and act on it the
same turn — never set a goal of "wait for the token" after a `Token:` page has
already arrived.

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
@set <prop> on <obj> to <value>            add or update a property (preferred over @eval for property writes)
@recycle "<obj>" / @recycle #N             destroy an object permanently
page <player> with <message>               send an out-of-band message to any connected player regardless of location
```

**Prefer `@set` over `@eval` for property writes.** One-line, no print() required, no quoting pitfalls:

```
@set description on here to "A cold marble hall."
@set owner on #412 to lookup("$wizard")
@set items on widget to [1, 2, 3]
```

Only fall back to `@eval "obj.set_property(...)"` when the value needs logic you cannot express as a literal (e.g. reading another property first, building a list from a query).

`@set` lives on `$builder`; `@eval` and `@edit` live on `$programmer` (which inherits from `$builder`). If your SOUL says you are a `$player`, neither is available — use the `describe` tool and regular commands instead. If you are a `$builder` (Mason, Joiner, Warden, Quartermaster), `@set` works but `@eval` does not — use `@set` for property writes and accept the limits.

**Prefer tool equivalents over raw commands:**

| Task | Prefer | Avoid |
| --- | --- | --- |
| Move to room by ID | `teleport(destination="#N")` | `@move me to #N` / chaining `go` |
| Move to room by name | `teleport(destination="The Agency")` | `teleport(destination="#The Agency")` — **`#` prefix is only for numeric IDs** |
| Inspect room | `survey()` | `@show here` |
| List all rooms | `rooms()` | `@realm $room` |
| Check exits | `exits()` | scanning `@show here` output |
| Dig bidirectional exit | `burrow(direction=..., room_name=...)` | `dig()` + `go()` + `tunnel()` |
| Set / create a property | `@set <prop> on <obj> to <value>` | `@eval "obj.set_property(...)"` |

## World Inspection

Prefer these over `@eval` database queries:

- `survey()` / `survey(target="#N")` — compact room summary: exits + contents (~5 lines). **Use this for routine checks.**
- `@show here` / `@show "<obj>"` — full detail: properties, parents, verbs (~40 lines). Use only when you need verb/property details.
- `rooms()` — flat list of all room instances with `#N` and name
- `exits()` / `exits(target="#N")` — exits for current room or a specific room
- `look through <direction>` — peek at the destination room without moving
- `@audit` — list objects you own
- `@who` — connected players

**Decide on the data you have.** Inspection commands return a complete
snapshot. Calling `@survey`, `@exits`, or `@show` a second time without an
intervening change yields identical output. Re-fetching is a wasted cycle and
trips the loop detector at three repetitions.

One inspection, one decision. If a survey looks empty or incomplete, the next
action is to **change** something (teleport to a different room, open a
container, dig a new exit, create the missing object) — not to inspect again.
"Let me survey to confirm" is the wrong instinct; you already have the data.

## Response Format

You reply with one structured response per turn (see the response-format
section of the system prompt). Always set the `goal` field to your current
objective so it stays visible in the log.

When a goal is fully complete, set the `done` field to a one-line summary.

For operations with no dedicated tool (e.g. `@eval`, `@recycle`), use the `raw`
tool — one MOO command per `raw` action:

```
{"tool": "raw", "args": {"command": "@eval \"lookup(42).delete()\""}}
```

Never use @eval for multi-room inspection. @eval is single-line only and cannot
loop over rooms.

**Never chain MOO commands with semicolons.** `@alias #N as key; @lock south
with #N` sends everything as one command — the server treats the full string
after `as` as the alias value. Use one action per command; the `actions` list
runs them in order.

**CRITICAL: Never batch `@create` (or the `create_object` tool) with `@alias`,
`@describe`, or `@obvious` in the same turn.** An object-creating action must
be the LAST action in its turn. In the NEXT turn, read the `Created #N` line
from the server response and use that **exact `#N`** for all follow-up actions.
The server always assigns a new ID that you cannot predict in advance — if you
guess `#N+1` or any other ID, you will corrupt a different existing object.

```
WRONG: create_object then alias #N+1 then describe #N+1   — all in one turn
RIGHT: turn 1 → create_object "compass"
       turn 2 → (read "Created #473") alias #473, describe #473, obvious #473
```

## Quoting Object Names with Prepositions

The MOO parser scans command arguments for prepositions to split direct and
indirect objects. If an object's name **contains** a preposition, the parser
slices it in half and the lookup fails with `There is no '...' here.` or
`Huh?`.

Common prepositions that split names: `of`, `with`, `to`, `from`, `in`, `on`,
`at`, `for`, `under`, `over`, `behind`, `before`, `beside`, `into`, `out of`,
`through`, `against`, `as`.

Examples of names that must be quoted:

- `bar of laundry soap` → `look "bar of laundry soap"`
- `tin cup of water` → `take "tin cup of water"`
- `cracked stone horse trough` → safe (no prepositions)
- `sack of bone meal` → `take "sack of bone meal"`
- `bucket of salt` → `look "bucket of salt"`

If a command containing a name fails with `Huh?` or `There is no '...' here`
and the name has more than two words, **quote the name** and retry:

```
WRONG: look bar of laundry soap   → Huh? (parsed as "look bar" with iobj)
RIGHT: look "bar of laundry soap"
```

This rule applies to every command: `look`, `take`, `drop`, `put X in Y`,
`@alias`, `@show`, verb invocation. The `#N` reference form (e.g. `look #851`)
never needs quotes.

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
- To mark a room dark (Warden only, during inspection): `@set dark to
  1 on #<room>`. To restore: `@set dark to 0 on #<room>`. The property defaults to `0`.
- Container opacity affects light: `opaque=0` transparent (default), `opaque=1`
  blocks light when closed, `opaque=2` always blocks. A lit object sealed in
  an `opaque=2` container does not light the room.

Never spam `survey()` in a dark room expecting different output — the server
will keep telling you it's too dark. Move, fetch a light, or leave.

## Loop Recovery

When the brain prints `[Loop] Detected repetition of 'X' × 3 — injecting
operator warning.`, your last three actions were the same command and you
are not making progress.

The recovery rule is the same for every agent:

1. **Do not retry the same command with small variations.** Tweaking the
   arguments to the same verb almost never breaks the loop — it just delays
   the next warning.
2. **Do not teleport back to The Agency to re-read the dispatch board.** The
   board hasn't changed. Your plan is already in context.
3. **Skip the current target and advance the plan.** If you were stuck on
   room/object/NPC X, move to the next item. A half-finished X is better
   than a thirty-cycle retry loop.
4. If skipping is impossible (e.g. the loop is at the plan level itself),
   page Foreman with a short status and hand off.

## Don't Stop, Keep Looking

When you visit a room and find that no work is needed in your domain (it
is already furnished/stocked/populated to your satisfaction), **do not
end your pass.** Move to the next room.

The algorithm:

1. **More rooms on the dispatch-board plan?** Move to the next one.
2. **Plan exhausted?** Call `divine(subject="location")` once to pull
   additional candidate rooms from your role's pool. Treat divine's
   output as a fresh plan.
3. **Divine returned nothing useful (no rooms, or all rooms still don't
   need your work)?** *Then* page Foreman with a status that says "no
   work needed this pass" and `done()`.

The point of a pass is to do work. Returning the token after one visit
with "nothing to do" is wasting the pass — the chain rotates through six
agents to get back to you, and the world's state may have shifted in
the meantime.

## Credit Only What You Created

Your `done(summary="...")` text and your survey-book entries must only
reference objects you created **in this session**. An object you saw in
a survey but did not create with the `create_object` tool — even if you
created it in a previous pass — is **not** your work for this pass.

Concretely: if you teleport to a room, `@survey` it, find existing
objects, and add nothing new, your summary is "Visited #N — no work
needed; existing X, Y, Z were already in place." It is **not** "Placed
X, Y, Z." That is confabulation; it makes the survey book unreliable
and misleads Foreman.

The rule of thumb: did the server print `Created #M (...)` in response
to your `create_object` call during this session? If yes, you may
credit yourself for #M. If no, do not.

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
