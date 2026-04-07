# Tinker Learned Rules

## Lessons Learned

**`create_object` places the new object directly in the current room** — you do not need `move_object` after creation. Use `create_object` inside `SCRIPT:` and reference the returned `#N` for alias, make_obvious, write_verb. If you still see `PermissionError: #N (Tinker) did not accept #M`, the object WAS created in the room — do NOT retry creation, and do NOT use move_object. Just proceed with alias and write_verb using the `#M` from the error message.

If you see `AmbiguousObjectError` (e.g. "do you mean #43 or #44?"), you have already created duplicates. Use `move_object` on the higher-numbered ID to place it here, then move on — never try to create another copy.

`PLAN:` must be a single pipe-separated line: `PLAN: #6 | #19 | #26 | ...` — never use bullet points or numbered lists for PLAN:. Never call `@realm $room` again after initial discovery.

**CRITICAL: `done()` freezes your session permanently until a new token arrives.** It is NOT a per-room completion signal. Only call `done()` once — AFTER all rooms in your PLAN are visited AND you have paged Foreman. After completing each room, emit `PLAN: <remaining rooms>` and set a new `GOAL:` — never `done()`. Calling `done()` early requires an operator restart and wastes all progress.

## Rules of Engagement

## Verb Mapping
