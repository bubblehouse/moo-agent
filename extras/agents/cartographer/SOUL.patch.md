## Lessons Learned

**`teleport` has no `@` prefix.** Use `teleport(destination="#N")` as a tool call, not `@teleport #N`. The `@teleport` form fails with "Huh?".

**`survey()` and `teleport()` are tool calls, not SCRIPT: commands.** Call them standalone. Inside SCRIPT: blocks, only raw MOO commands like `look`, `@audit here`, `go north`.

**`@who` and `@whereis` must use SCRIPT: format.** `SCRIPT: @who` not bare `@who`.

## Verb Mapping

- audit -> @audit here

## Rules of Engagement
