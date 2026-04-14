# Stocker Learned Rules

## Lessons Learned

- `read_board` returns a bare list of room IDs, e.g. `#690`. Read it **exactly once**. Whatever it returns — even a single ID — is the complete room list for this pass. **Do not call `read_board` again.** Proceed immediately to `divine()` then start stocking.
- When `@create` runs, the server returns TWO lines: `Created #N (name)` then `Transmuted #N (name) to #M (Generic Thing)`. **Always use the `#N` from `Created #N`, never the `#M` from Transmuted.** The `#M` is the parent class (Generic Thing = #13), not the new object. All follow-up aliases, describe, and obvious commands must use the `#N` from the `Created` line.
- `$furniture` objects (shelves, benches, cabinets) **cannot hold items** — `move_object` into them always fails with PermissionError. Only `$container` objects accept items. When a room has a shelf or furniture, leave stocked items in the room directly (the item's location is already the room). Do not attempt to move items into furniture.
- `write_verb` must be called as a direct tool call, never inside a `SCRIPT:` line. The SCRIPT parser cannot handle code arguments that contain parentheses or escaped quotes. Always call `write_verb(obj="...", verb="...", code="...")` directly in a tool response, not via `SCRIPT: write_verb(...)`.
- **CRITICAL: Never batch `@create` with `@alias`, `@describe`, or `@obvious` in the same SCRIPT: block.** `@create` must be the ONLY command in its SCRIPT: block. In the NEXT cycle, read the `Created #N` line from the server response and use that exact `#N` for alias, describe, and obvious. If you batch them together you predict a future object ID before the server assigns it, and you will accidentally alias or describe an existing unrelated object (e.g., an exit). Wrong: `SCRIPT: @create "water" from "$thing" in #N / @alias #N+1 as "water"`. Right: one SCRIPT: with only `@create`, then a separate cycle for alias/describe/obvious using the actual ID from the server response.
- Keep verb code short. Long code strings (> 5 lines) in `write_verb` expand the context window and cause context overflow errors on subsequent cycles. If a verb needs complex logic, split it across two calls or simplify the code.
- **CRITICAL: One room per LLM cycle. Do NOT emit SCRIPT: blocks for multiple rooms in a single response.** Stock one room completely, emit `PLAN:` with remaining rooms, then stop. The next cycle handles the next room. Batching all rooms into one response causes a queue deadlock and forces an agent restart.
- **After any `[server_error]` on a teleport (e.g. "There is no '#541' here"), do NOT re-survey the current room.** Use `survey()` to confirm where you are, then emit `PLAN:` with the rooms still to visit and teleport to the next one. Repeated survey-without-action loops require a manual restart.
- **When `read_board` returns "Nothing posted for topic 'tradesmen'" — do NOT call `read_board` again and do NOT teleport to The Agency.** "Nothing posted" is the final answer; retrying will return the same result forever. Immediately call `divine()` from wherever you are to get rooms. Then emit `PLAN:` and teleport to the first room in the SAME response.

## Rules of Engagement

## Verb Mapping
