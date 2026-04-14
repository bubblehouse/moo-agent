# Joiner Learned Rules

## Lessons Learned

- `read_board` returns a bare list of room IDs, e.g. `#690`. Read it exactly once. Whatever it returns is the complete room list — do not re-read. Proceed immediately to `divine()` then start placing furniture.

- **The board and divine() are called exactly once at the start of each token cycle — then you are done with The Agency.** After `divine()` returns rooms, emit `PLAN:` and teleport immediately to the first room. Do not re-read the board. Do not teleport back to The Agency. Do not call `divine()` again. If you catch yourself teleporting to The Agency or #23 after already having a PLAN:, stop — you are in a loop. Teleport to the first room in your PLAN: instead.

- **Never call `obvious()` with a room ID.** `obvious()` is only for objects you just created with `@create`. The `#N` you pass must come from a `Created #N` line in server output — never from `survey()` room output or from teleport destinations. Room IDs and object IDs look identical; always trace the `#N` back to a `@create` response before calling `obvious()`.

- **After placing furniture in a room, immediately emit `PLAN:` with remaining rooms and move on.** Do not linger to alias, re-describe, or re-survey. One piece of furniture per room is sufficient — do not loop within a room with repeated teleports and surveys before acting.

- **When `survey()` shows ANY objects in room Contents (any #N IDs listed), skip the room immediately.** Do NOT create, describe, alias, or obvious anything. The room is already furnished. Emit `PLAN:` with remaining rooms and `teleport(destination=next_room_id)` in the SAME response. Do not linger or try to add "one more piece".

`$furniture` CANNOT be moved after creation — `@move #N to #M` always fails with "cannot be moved." Always use `@create "name" from "$furniture" in #ROOM` to place furniture at creation time. If an object is already misplaced, use the five-step reparent-move: `@add_parent "$thing" to #N`, then `@remove_parent "$furniture" from #N`, then `@move #N to #ROOM`, then `@remove_parent "$thing" from #N`, then `@add_parent "$furniture" to #N`. The extra `$thing` step is required because `$furniture.moveto` blocks non-wizard movement but `$thing.moveto` does not.

- **When `@create` runs, the server returns TWO lines: `Created #N (name)` then `Transmuted #N (name) to #M (Generic Thing)`. Always use the `#N` from the `Created #N` line. Never use the `#M` from the Transmuted line — that is the parent class ID, not your new object. All follow-up `@describe`, `alias`, and `obvious` calls must use the `#N` from `Created`.**

- **CRITICAL: After `@create`, IMMEDIATELY call `survey()` to verify the object ID in the room Contents list BEFORE calling `@describe`, `@alias`, or `@obvious`.** The server response line `Created #N` gives you the ID, but if you're unsure or in any doubt, survey() is the authoritative source. Do NOT predict or assume the next ID. Do NOT use #N+1. Use only the exact #N you can see in either a `Created #N` server line or a `survey()` Contents entry. If you cannot find the ID in either place, skip @obvious and move on.

- **`$furniture` objects CANNOT hold items** — `@move #N to #M` where #M is a `$furniture` object (table, bench, shelf, stool) always fails with PermissionError. Only `$container` objects (chests, trunks, crates) can hold items. If you want to suggest something is "on" a table, leave the item in the room itself (its location is the room). Do not try to move items into furniture.

- **After `read_board` + `divine()` return results, emit `PLAN:` immediately and teleport to the first room. Do not teleport back to #23 or re-read the board.** If you find yourself teleporting to #23 or calling `read_board` again after already having room IDs, you are in a loop — stop, emit `PLAN:` with whatever rooms you have, and teleport to the first one.

- **When `read_board` returns "Nothing posted for topic 'tradesmen'" — do NOT call `read_board` again.** "Nothing posted" is the final, authoritative answer; retrying will return the same result forever. Immediately call `divine()` to get rooms. Do not teleport to The Agency first — call `divine()` from wherever you are.

- **Never try to `@describe`, `@alias`, or `@obvious` an object ID before running `@create`.** The object does not exist yet and the command will fail with "There is no '#N' here." Always run `@create` first in its own SCRIPT: block, read the `Created #N` from the server response, then use that exact `#N` for all follow-up commands in the next cycle. Do not predict the next ID from room contents.

## Rules of Engagement

## Verb Mapping
