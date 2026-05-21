## Lessons Learned

**CRITICAL: Do NOT teleport to The Agency before starting work.** You are already in The Agency when you receive the token. Call `divine()` immediately from wherever you are — no teleport needed first.

**CRITICAL: Filter The Agency (#23) from your plan.** `divine()` sometimes returns The Agency. Never put #23 in the `plan` field — skip it and use only the other rooms divine() returned.

**`read_board` is not one of your tools.** If you find yourself calling `read_board`, stop immediately and call `divine()` instead. `divine()` is your only room source.

**Never chain MOO commands with semicolons.** Use actions in sequence: `open(obj="#N")`, then `take(item="#M", source="#N")`.

**`@opacity` syntax requires `is`: `@opacity #N is 1`.** `@opacity #N 1` fails.

**`open`, `close`, `put`, `take`, `drop` are tools.** Emit them as actions — `open(obj="#N")`, `close(obj="#N")`, `put(item="#N", container="#M")`, `take(item="#N", source="#M")`, `drop(obj="#N")` — never route them through `raw`.

**A container must be open before you can `put` anything into it.** If you get "is closed" on a put, call `open(obj="#N")` first, then `put(item="#item", container="#N")`.

**`alias` is a tool.** Emit it as an `alias(obj='#N', name='short name')` action — one name per call. To add multiple aliases, make multiple calls. Never route `alias` through `raw`.

**`survey` is a tool.** Emit it as a `survey(target='#N')` action, or `survey()` for the current room. Never route `survey` through `raw`. To check container contents after opening, an `open(obj="#N")` action then a `raw` action with `look` — the look output shows contents.

**Object creation must be the last action in its turn.** The created ID is unknown until the server responds. Create the object, read the `Created #NNN` response on the next turn, then reference `#NNN` in follow-up actions.

**When `@create` output reads "Created #N ... Transmuted #N to #M (Generic Thing)", the created object is #N — not #M.** The "Transmuted" line shows the parent class assignment (#M is the parent class, e.g. `$thing`). Always use the `Created #N` number as your object ID. Example: `Created #321 (iron bolt) / Transmuted #321 to #13 (Generic Thing)` → object is #321, use `#321` in all subsequent commands.

**Check your inventory before creating test items.** If you already have items (stones, bolts, beads, screws), do not create more. Use what you have. Run `look` or `survey` and check your inventory first — creating 5+ items when 1 would do wastes context and time.

## Verb Mapping

## Rules of Engagement
