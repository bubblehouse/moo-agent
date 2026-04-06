# Agent Verb Proposals

Observations from running the Tradesman agents (Mason, Tinker, Joiner, Harbinger) in live
sessions. Each proposal targets a concrete failure pattern visible in session logs.

---

## 1. `@survey [here | #N]` — lightweight room inspector

**Problem:** `@show here` dumps every property on the object — internal message templates
(`arrive_msg`, `oarrive_msg`, `oleave_msg`, `ejection_message`, `victim_ejection_message`,
`residents`, `free_entry`, `content_list_type`, `dark`, etc.) plus all verbs and all
properties. A single `@show here` for The Laboratory produced ~40 lines of output. After 3–4
rooms the accumulated context causes Gemma to stall and the agent must be restarted.

**Proposal:** A new verb `@survey` that returns only what agents need:

```
@survey here  →
  The Laboratory (#19)
  Exits:
    east  → The Greenhouse (#27)
    north → The Archive (#30)
    south → The Archive (#33)
  Contents:
    #46 (heavy metal storage cabinet)
    #48 (metal laboratory stool)
    #56 (glass specimen case)
```

No verbs, no properties, no message templates. Exit lines include the destination `#N` so the
agent never needs to navigate to verify identity.

**Implementation:** New verb `@survey` on `$player` (dspec: either). For rooms, query
`obj.exits` property + `obj.contents.all()`. For non-rooms, fall back to name + location +
contents.

**Impact:** Cuts per-room context cost by ~90%. Mason currently stalls every 8–10 minutes
after 1–2 rooms. With `@survey`, it should complete 4–6 rooms per session.

---

## 2. `@peek <direction>` — look through an exit without moving

**Problem:** Mason spent 5 consecutive LLM cycles trying to confirm "Is #72 The Greenhouse?"
It navigated south, called `@show here`, went west, called `@show #27`, then `@show here`
again — burning context and still ending the session uncertain. Every `go` command also adds
arrival/departure text to the log.

**Proposal:** `@peek <direction>` resolves the destination without moving:

```
@peek south  →  south leads to The Greenhouse (#72).
@peek east   →  east leads to The Observatory (#74).
@peek up     →  There is no exit in that direction.
```

**Implementation:** Verb on `$player` (dspec: any). Look up current room's exit in the given
direction, return `destination.title()` and `#destination.id`. No movement, no side effects.

**Impact:** Eliminates the entire "navigate to verify" pattern. One command answers the
question that currently takes 3–5 navigation cycles.

---

## 3. `@digreturn <direction> to "<room name>" return <return_direction>` — atomic bidirectional dig

**Problem:** Creating a bidirectional exit requires three separate commands executed across
two or more LLM cycles: `@dig north to "Room Name"`, then `go north`, then `@tunnel south to
#N`. Gemma frequently forgets `@tunnel`, uses the wrong return direction, or passes a room
name instead of `#N` to `@tunnel`. The tools.py `_dig`/`_tunnel` split also means the agent
must track intermediate `#N` values across cycles.

**Proposal:** `@digreturn north to "The Watchtower" return south` creates the forward exit,
creates the new room, moves the caller into it, and creates the return exit in one command.
Output:

```
Dug north to The Watchtower (#81).
Tunnelled south back to The Laboratory (#19).
You are now in The Watchtower (#81).
```

**Implementation:** Verb on `$player` (dspec: any, ispec: `to:any`, `return:any`). Internally
calls the same logic as `@dig` + movement + `@tunnel`. Requires custom ispec parsing for the
two prepositions (`to` and `return`). Alternatively expose as `@digreturn` with a fixed
argument format parsed from dobj string.

**Impact:** Reduces 3 fallible steps to 1 atomic step. Eliminates the most common source of
"exit wired in only one direction" bugs.

---

## 4. `@nav #N` — direct teleport to a room by object ID

**Problem:** Agents navigating between rooms must follow exit chains: `go north`, `go east`,
`go south`. Each step adds arrival/departure text to the context. For a world with 10+ rooms,
getting from Room A to Room F can take 4–6 `go` commands, filling ~20 lines of context before
any work begins. Tinker and Joiner in particular must traverse the whole world room by room.

**Proposal:** `@nav #N` teleports the caller directly to a room:

```
@nav #74  →  You move to The Observatory (#74).
```

Equivalent to `@move me to #N` but shorter, agent-friendly, and named for navigation intent.

**Implementation:** Verb on `$player` (dspec: any). Resolves the dobj as an object reference,
validates it is a room (or container), calls `player.move(dest)`. Reuse the `@move me to`
logic.

**Impact:** Collapses multi-step navigation into one command. Joiner and Tinker especially
benefit — they need to visit every room in the world sequentially and currently must navigate
through exit chains.

---

## 5. `@rooms` — flat list of all rooms with IDs

**Problem:** `@realm $room` shows the inheritance *tree* rooted at `$room`. What agents
actually want is a flat list of all room *instances* with their `#N` and name, so they can
build a traversal plan. Mason called `@realm $room` late in a session and likely received the
class hierarchy rather than room instances.

**Proposal:** `@rooms` returns a flat, paginated list of every object whose parent chain
includes `$room`:

```
Rooms in the world:
  #19  The Laboratory
  #26  The Greenhouse
  #29  The Archive
  #32  The Vault
  #71  The Library
  #74  The Observatory
  #81  The Watchtower
```

**Implementation:** Verb on `$player` (no dspec). Query
`Object.objects.filter(parents__unique_name="room")` or traverse `$room.get_descendents()`
filtering to leaf instances (not classes). Send through `open_paginator`.

**Impact:** Lets Tinker, Joiner, and Harbinger build a complete room list at session start
with one command. Currently they rely on Mason's `PLAN:` page text, which can be truncated.

---

## 6. `@exits [here | #N]` — show just exits for a room

**Problem:** A common agent sub-task is "check what exits exist before digging, to avoid
direction conflicts." Today this requires `@show here` and scanning through all the properties
to find the `exits` list. The exits are buried mid-output after verbs and other properties.

**Proposal:** `@exits` or `@exits here` returns only the exits:

```
Exits from The Laboratory (#19):
  east  → The Greenhouse (#27)
  north → The Archive (#30)
  south → The Archive (#33)
```

**Implementation:** Verb on `$player` (dspec: either). Read `obj.get_property("exits")`,
format each entry as `direction → name (#N)`.

**Impact:** Makes the pre-dig check a single focused command. Agents can confirm available
directions without pulling the full `@show` output into context.

---

## Priority order

| # | Verb | Impact | Effort |
|---|------|--------|--------|
| 1 | `@survey` | Fixes the context-overload stall pattern (Mason restarts every ~10 min) | Medium |
| 2 | `@peek` | Eliminates 5-cycle room-identity verification spirals | Low |
| 3 | `@rooms` | Enables Tinker/Joiner/Harbinger to self-navigate without Mason's PLAN: page | Low |
| 4 | `@exits` | Focused pre-dig check, avoids `@show` for a single piece of info | Low |
| 5 | `@nav` | Eliminates multi-step navigation chains | Medium |
| 6 | `@digreturn` | Reduces 3-step atomic operation to 1 | Medium–High |

`@survey`, `@peek`, `@rooms`, and `@exits` are all read-only queries with no side effects —
lowest risk, highest value. `@nav` and `@digreturn` involve movement/mutation and need more
careful testing.
