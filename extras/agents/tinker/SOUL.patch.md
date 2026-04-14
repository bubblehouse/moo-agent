# Tinker Learned Rules

## Lessons Learned

- `read_board` returns a bare list of room IDs separated by newlines, e.g. `#690` or `#690\n#67`. Read it exactly once. Whatever it returns — even a single ID — is the complete room list for this pass. Do not re-read the board. Proceed immediately to `divine()` and then visit each room.
- `divine()` may return up to 6 rooms. Only take the first 1-2 from its result. Combined with the board rooms, your total room list per pass must not exceed 3 rooms. Stop adding rooms once you have 3.
- **`write_verb` must be a tool call, never in a SCRIPT: block.** Putting `write_verb(...)` in a SCRIPT: block sends it verbatim to the MOO server, which returns "Huh?". Always call it directly as a tool: `write_verb(verb="...", obj="#N", code="...")`.
- **`write_book` must be a tool call, never in a SCRIPT: block.** Same rule as `write_verb` — putting `write_book(...)` in SCRIPT sends it as raw text to the server and fails with "Huh?". Call it directly as a tool: `write_book(room_id="#N", topic="tradesmen", entry="...")`.
- **After writing a verb, test it with the exact verb name you wrote.** If you wrote `calibrate`, test with `calibrate #N` — not `activate #N` or any other name.
- **Never teleport to #0 or #1.** `#0` is not a valid room; `#1` is the system object, also not a room. Both fail with errors. To return to The Agency, use `teleport $player_start`.

## Rules of Engagement

## Verb Mapping
