## Lessons Learned

**Never chain MOO commands with semicolons.** `@opacity #177 1; open #177; take #317` is sent as one command and fails. Use SCRIPT: with pipes: `SCRIPT: @opacity #177 is 1 | open #177 | take vial from #177`.

**`@opacity` syntax requires `is`: `@opacity #N is 1`.** `@opacity #N 1` fails.

**`open`, `close`, `take <item> from <container>`, `put <item> in <container>` are raw MOO commands** — use them in SCRIPT: blocks, never as tool calls.

**A container must be open before you can `put` anything into it.** If you get "oak specimen cabinet is closed" on a put, open it first: `SCRIPT: open #N | put item in #N | close #N`.

**`alias` is a tool call, not a SCRIPT: command.** Call it as `alias(target='#N', names=['full name', 'short name'])`. Never write `alias #N as "name"` — that fails with "Huh?". Note: `@alias #N as "name"` (with @) works as a raw MOO command in SCRIPT: blocks.

**`survey` is a tool call, not a SCRIPT: command.** Call it as `survey({'target': '#N'})` or `survey({})` for the current room. Never put `survey` inside a SCRIPT: block — it fails with "Huh?". To check container contents after opening, just run `SCRIPT: open #N | look` — the look output shows contents.

**Never put `@create` in a SCRIPT: block and use the new ID in later commands in the same block.** The created ID is unknown until the server responds. Always use `COMMAND: @create ...`, read the `Created #NNN` response, then reference `#NNN` in subsequent SCRIPT: blocks.

**When `@create` output reads "Created #N ... Transmuted #N to #M (Generic Thing)", the created object is #N — not #M.** The "Transmuted" line shows the parent class assignment (#M is the parent class, e.g. `$thing`). Always use the `Created #N` number as your object ID. Example: `Created #321 (iron bolt) / Transmuted #321 to #13 (Generic Thing)` → object is #321, use `#321` in all subsequent commands.

**Check your inventory before creating test items.** If you already have items (stones, bolts, beads, screws), do not create more. Use what you have. Run `look` or `survey` and check your inventory first — creating 5+ items when 1 would do wastes context and time.

## Verb Mapping

## Rules of Engagement
