# Harbinger Learned Rules

## Lessons Learned

- `send_report` sends a **mail** message only — it does NOT return the token. If `done()` is blocked with "you must page Foreman", you have NOT yet called `page()`. Call `page(target="foreman", message="Token: Harbinger done.")` explicitly, wait for "Your message has been sent.", then call `done()`. `send_report` and `page()` are two separate calls; you need both.
- **CRITICAL: When `done()` is blocked, your IMMEDIATE next action must be `page(target="foreman", message="Token: Harbinger done.")` — nothing else. Do not plan, do not roll, do not call `done()` again. Call `page()` first, wait for "Your message has been sent.", then call `done()` alone in a separate cycle.**
- `read_board` returns a bare list of room IDs, e.g. `#690`. Read it **exactly once**. Whatever it returns is the complete room list for this pass. Do not re-read the board.
- **When `read_board` returns "Nothing posted for topic 'tradesmen'" — call `divine()` IMMEDIATELY.** Do NOT retry `read_board`. Do NOT teleport to The Agency. Just call `divine()` right where you are.
- **CRITICAL: Create NPCs only while standing inside the target room.** Before `@create`, always confirm your current location with `survey()`. If you are in The Agency or any room other than your target, `teleport` there first.

## Rules of Engagement

## Verb Mapping
