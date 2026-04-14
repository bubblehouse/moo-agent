# Harbinger Learned Rules

## Lessons Learned

- `send_report` sends a **mail** message only — it does NOT return the token. If `done()` is blocked with "you must page Foreman", you have NOT yet called `page()`. Call `page(target="foreman", message="Token: Harbinger done.")` explicitly, wait for "Your message has been sent.", then call `done()`. `send_report` and `page()` are two separate calls; you need both.
- `read_board` returns a bare list of room IDs, e.g. `#690`. Read it **exactly once**. Whatever it returns is the complete room list for this pass. Do not re-read the board.

## Rules of Engagement

## Verb Mapping
