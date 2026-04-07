# Tinker Learned Rules

## Lessons Learned

`PLAN:` must be a single pipe-separated line: `PLAN: #6 | #19 | #26 | ...` — never use bullet points or numbered lists for PLAN:. Never call `@realm $room` again after initial discovery.

**CRITICAL: `done()` freezes your session permanently until a new token arrives.** It is NOT a per-room completion signal. Only call `done()` once — AFTER all rooms in your PLAN are visited AND you have paged Foreman. After completing each room, emit `PLAN: <remaining rooms>` and set a new `GOAL:` — never `done()`. Calling `done()` early requires an operator restart and wastes all progress.

## Rules of Engagement

## Verb Mapping
