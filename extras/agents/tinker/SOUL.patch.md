# Tinker Learned Rules

## Lessons Learned

`PermissionError: #N (Tinker) did not accept #M` after `@create` is NOT a failure — the object WAS created and is in your inventory. **Immediately** use `move_object({'destination': 'here', 'obj': '#M'})` to place it in the current room. **Never** attempt to create the object again under any name or using any other method — doing so creates duplicates and causes `AmbiguousObjectError`. Using `create_object` as a tool call is NOT different from `@create` — do not retry creation.

If you see `AmbiguousObjectError` (e.g. "do you mean #43 or #44?"), you have already created duplicates. Use `move_object` on the higher-numbered ID to place it here, then move on — never try to create another copy.

`PLAN:` must be a single pipe-separated line: `PLAN: #6 | #19 | #26 | ...` — never use bullet points or numbered lists for PLAN:. Never call `@realm $room` again after initial discovery.

**CRITICAL: `done()` freezes your session permanently until a new token arrives.** It is NOT a per-room completion signal. Only call `done()` once — AFTER all rooms in your PLAN are visited AND you have paged Foreman. After completing each room, emit `PLAN: <remaining rooms>` and set a new `GOAL:` — never `done()`. Calling `done()` early requires an operator restart and wastes all progress.

## Rules of Engagement

## Verb Mapping
