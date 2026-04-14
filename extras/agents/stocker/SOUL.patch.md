# Stocker Learned Rules

## Lessons Learned

- `read_board` returns a bare list of room IDs, e.g. `#690`. Read it **exactly once**. Whatever it returns — even a single ID — is the complete room list for this pass. **Do not call `read_board` again.** Proceed immediately to `divine()` then start stocking.
- When `@create` runs, the server returns TWO lines: `Created #N (name)` then `Transmuted #N (name) to #M (Generic Thing)`. **Always use the `#N` from `Created #N`, never the `#M` from Transmuted.** The `#M` is the parent class (Generic Thing = #13), not the new object. All follow-up aliases, describe, and obvious commands must use the `#N` from the `Created` line.
- `$furniture` objects (shelves, benches, cabinets) **cannot hold items** — `move_object` into them always fails with PermissionError. Only `$container` objects accept items. When a room has a shelf or furniture, leave stocked items in the room directly (the item's location is already the room). Do not attempt to move items into furniture.
- `write_verb` must be called as a direct tool call, never inside a `SCRIPT:` line. The SCRIPT parser cannot handle code arguments that contain parentheses or escaped quotes. Always call `write_verb(obj="...", verb="...", code="...")` directly in a tool response, not via `SCRIPT: write_verb(...)`.
- Keep verb code short. Long code strings (> 5 lines) in `write_verb` expand the context window and cause context overflow errors on subsequent cycles. If a verb needs complex logic, split it across two calls or simplify the code.

## Rules of Engagement

## Verb Mapping
