# Tinker Learned Rules

## Lessons Learned

- `read_board` returns a bare list of room IDs separated by newlines, e.g. `#690` or `#690\n#67`. Read it exactly once. Whatever it returns — even a single ID — is the complete room list for this pass. Do not re-read the board. Proceed immediately to `divine()` and then visit each room.
- **CRITICAL: Never batch `@create` with `@alias`, `@describe`, `@obvious`, or `write_verb` in the same SCRIPT: block.** `@create` must be the ONLY command in its SCRIPT: block. In the NEXT cycle, read the `Created #N` line from the server response and use that exact `#N` for all follow-up commands. If you batch them together you predict a future object ID before the server assigns it, and you will accidentally alias or describe an existing unrelated object. Wrong: `SCRIPT: @create "compass" from "$thing" in #N | @alias #N+1 as "compass"`. Right: one SCRIPT: with only `@create`, then a separate cycle for alias/describe/obvious/write_verb using the actual ID from the `Created #N` server response line.
- `divine()` may return up to 6 rooms. Only take the first 1-2 from its result. Combined with the board rooms, your total room list per pass must not exceed 3 rooms. Stop adding rooms once you have 3.
- **`write_verb` must be a tool call, never in a SCRIPT: block.** Putting `write_verb(...)` in a SCRIPT: block sends it verbatim to the MOO server, which returns "Huh?". Always call it directly as a tool: `write_verb(verb="...", obj="#N", code="...")`.
- **`write_book` must be a tool call, never in a SCRIPT: block.** Same rule as `write_verb` — putting `write_book(...)` in SCRIPT sends it as raw text to the server and fails with "Huh?". Call it directly as a tool: `write_book(room_id="#N", topic="tradesmen", entry="...")`.
- **After writing a verb, test it with the exact verb name you wrote.** If you wrote `calibrate`, test with `calibrate #N` — not `activate #N` or any other name.
- **Never teleport to #0 or #1.** `#0` is not a valid room; `#1` is the system object, also not a room. Both fail with errors. To return to The Agency, use `teleport $player_start`.

- **CRITICAL: When `done()` is blocked with "[Done] Blocked", your IMMEDIATE next action must be `page(target="foreman", message="Token: Tinker done.")` — nothing else. Do not plan, do not test verbs, do not call `done()` again. Call `page()` first, wait for "Your message has been sent.", then call `done()` alone in a separate cycle. Calling `done()` repeatedly without `page()` will loop forever.**

## Rules of Engagement

## Verb Mapping
