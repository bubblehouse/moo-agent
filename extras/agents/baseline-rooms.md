# MOO Agent Room Knowledge

## Room Traversal

Agents that visit existing rooms (Tinker, Joiner, Harbinger, Stocker) follow this protocol:

1. **Check `Remaining plan:` first.** If it contains room IDs (from the token page),
   emit `PLAN:` from that list and skip room discovery.
2. If no room list was provided, run `rooms()` once to discover all rooms.
   This returns a flat `#N  Room Name` list — much more compact than `@realm $room`.
3. Filter out system rooms — skip any room named "Generic Room" or "Mail Distribution Center".
4. Emit a single `PLAN:` line with room IDs pipe-separated:

   ```
   PLAN: #9 | #22
   ```

5. Visit each room using `teleport(destination="#N")` — do not chain `go` commands.
   `teleport` moves you directly without traversing exits.
6. In each room, call `survey()` (not `show()`) to get the compact exit+contents summary.
   `survey()` produces ~5 lines; `show()` produces ~40 lines and will stall the session.
7. After completing each room, emit an updated `PLAN:` with the remaining rooms:

   ```
   PLAN: #22
   ```

8. When the plan is empty, pass the token to your successor and call `done()`.

**Never call `@realm $room` after initial discovery.** Use `rooms()` instead.
If you restart mid-session, your plan is restored from disk automatically.

**PLAN: format is strict** — pipe-separated on a single line. No bullets, no
numbered lists, no multi-line. The plan tracker only reads `PLAN: #N | #M | ...`.

On session resume with no active plan (no disk file), re-run `rooms()` once
to rebuild the list, then emit `PLAN:` as above.

**Use `look through <direction>` to peek at a destination before moving.**
This shows the destination room's full description without navigating there:

```
look through north   →  shows what is in the room to the north
```

## Parent Class Quick Reference

| Class | Use for | Notable behaviour |
| --- | --- | --- |
| `$thing` | Portable props, tools, items | take/drop verbs |
| `$container` | Openable objects (chests, bags, cabinets) | open/close/put/take verbs |
| `$furniture` | Sittable, immovable fixtures (chairs, benches) | sit/stand verbs; wizard `moveto` allowed; **cannot contain objects — use `$container` if players need to put things inside** |
| `$note` | Readable text objects (signs, menus, letters) | `read` verb; `text` property |
| `$player` | NPCs with dialogue | full messaging infrastructure |
| `$room` | Rooms — use `@dig`, not `@create` | contents, exits, announce |

## Aliases

Every object needs at least one alias so players can refer to it by name. Add
aliases immediately after `@create`.

**Multi-word names:** alias every trailing sub-phrase — drop one leading word at a time,
all the way down to the bare final noun. Do not alias individual adjectives alone.

```
name: "heavy wooden lid"
aliases: "wooden lid", "lid"

name: "pneumatic message tube"
aliases: "message tube", "tube"
```

Three words → two aliases. Four words → three aliases. Continue until you reach the
bare final noun. Every step is required — stopping after one alias is wrong.

**Names with prepositions** ("of", "with", "for", "from", "in"): split on the
preposition. Alias the last word before the preposition AND the last word of the
name. Both are required. Skip everything in between.

```
name: "tin of brass polish"
→ split: "tin" | "brass polish"
→ aliases: "tin", "polish"

name: "bottle of lamp oil"
→ split: "bottle" | "lamp oil"
→ aliases: "bottle", "oil"

name: "tin of bone meal"
→ split: "tin" | "bone meal"
→ aliases: "tin", "meal"

name: "jar of river clay"
→ split: "jar" | "river clay"
→ aliases: "jar", "clay"
```

Never alias "of X" or multi-word phrases after the preposition — only the final word.

**Single-word names:** alias close synonyms only — as few as needed, as close to the
original word as possible. Avoid distant synonyms.

```
name: "torch"
aliases: "lantern"          ← close synonym
NOT: "light source"         ← too distant
```

**`alias` tool call syntax** — one alias at a time, `name` (singular string):

```
alias(obj="#38", name="lid")        # correct
alias(obj="#38", name="wooden lid") # call again for each additional alias
```

Never pass a list to `alias`. Call it once per alias name.

**`obvious`** controls whether an object appears in room listings. Set it after
creating every room object. Use the `obvious` **tool call** — the tool name matches
the underlying verb (`@obvious`):

```
obvious(obj="#38")   # correct — tool call
```

## #N Object References

**After `@create`, use `#N` for every subsequent operation on that object** —
`@describe`, `@alias`, `@move`, `@obvious`, `@edit verb`, `@edit property`.
Name-based lookup only works when the object is in your current location or
inventory. The moment an object moves — or another object shares the same name —
the parser will silently target the wrong one.

```
WRONG: @alias "flashlight" as "torch"           → may alias a different flashlight
RIGHT: @alias #277 as "torch"                   → aliases exactly the object you created

WRONG: @edit verb flip on "Main Electrical Panel" with "..."  → may hit wrong object
RIGHT: @edit verb flip on #356 with "..."                     → targets the exact object
```

**Objects inside containers are invisible to the parser.** After `@move #N to #container`,
use `#N` for all operations — name lookup will fail:

```
@create "reagent vial" from "$thing"   → Created #164 (reagent vial)
@move #164 to #163                     → moved inside the cabinet
@describe #164 as "..."                → CORRECT — use #N
@describe "reagent vial" as "..."      → WRONG — parser can't find it inside container
```

**`@create` must be a standalone `COMMAND:`, never inside `SCRIPT:`.** SCRIPT: queues
all commands before any run, so you cannot use the `#N` from `@create`'s output in later
commands of the same script — the ID isn't known yet.

```
WRONG:
SCRIPT:
@create "metal box" from "$thing"   # assigns #33
@move #33 to here                   # WRONG — you guessed; could be any number

RIGHT:
COMMAND: @create "metal box" from "$thing"
# server responds: Created #33 (metal box)
SCRIPT:
@move #33 to here
@describe #33 as "..."
@alias #33 as "box"
```

**Naming rules:**

- No underscores — `"heavy power cable"` not `"heavy_power_cable"`
- Lowercase unless a proper noun or brand name — `"oak writing desk"`, not `"Oak Writing Desk"`
- Exact room spelling — if you dug `"The Armory"`, reference it as `"The Armory"` everywhere

**`@describe here as "..."` for the current room.** Never `@describe "Room Name" as "..."` —
rooms cannot be found by name. Navigate to the room first, then use `@describe here`.

```
WRONG: @describe "The Kitchen" as "Warm and smelling of herbs."
RIGHT: go north
       @describe here as "Warm and smelling of herbs."
```

**Check existing exits before digging.** `@burrow` and `@dig` fail with "There is
already an exit in that direction" if the direction is taken. Run `exits()` first.
