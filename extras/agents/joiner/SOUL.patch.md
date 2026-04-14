# Joiner Learned Rules

## Lessons Learned

- `read_board` returns a bare list of room IDs, e.g. `#690`. Read it exactly once. Whatever it returns is the complete room list — do not re-read. Proceed immediately to `divine()` then start placing furniture.

- **The board and divine() are called exactly once at the start of each token cycle — then you are done with The Agency.** After `divine()` returns rooms, emit `PLAN:` and teleport immediately to the first room. Do not re-read the board. Do not teleport back to The Agency. Do not call `divine()` again. If you catch yourself teleporting to The Agency or #23 after already having a PLAN:, stop — you are in a loop. Teleport to the first room in your PLAN: instead.

- **Never call `obvious()` with a room ID.** `obvious()` is only for objects you just created with `@create`. The `#N` you pass must come from a `Created #N` line in server output — never from `survey()` room output or from teleport destinations. Room IDs and object IDs look identical; always trace the `#N` back to a `@create` response before calling `obvious()`.

- **After placing furniture in a room, immediately emit `PLAN:` with remaining rooms and move on.** Do not linger to alias, re-describe, or re-survey. One piece of furniture per room is sufficient — do not loop within a room with repeated teleports and surveys before acting.

- **When `survey()` shows furniture already exists in a room, skip it immediately.** Do not call `obvious()`, `alias()`, or `describe()` on objects you didn't create. Emit `PLAN:` with the remaining rooms and move on. Do not linger.

`$furniture` CANNOT be moved after creation — `@move #N to #M` always fails with "cannot be moved." Always use `@create "name" from "$furniture" in #ROOM` to place furniture at creation time. If an object is already misplaced, use the five-step reparent-move: `@add_parent "$thing" to #N`, then `@remove_parent "$furniture" from #N`, then `@move #N to #ROOM`, then `@remove_parent "$thing" from #N`, then `@add_parent "$furniture" to #N`. The extra `$thing` step is required because `$furniture.moveto` blocks non-wizard movement but `$thing.moveto` does not.

## Rules of Engagement

## Verb Mapping
