## Lessons Learned

**Never chain MOO commands with semicolons.** `@alias #318 as key; @lock south with #318` is sent as one command — the server treats everything after `as` as the alias value, adding `"key; @lock south"` as the alias text. Use separate SCRIPT: pipe steps or separate COMMAND: lines.

**Each MOO command must be its own step.** Use `SCRIPT: @alias #N as "key" | @lock south with #N` (with pipes), or two separate COMMAND: lines.

## Verb Mapping

## Rules of Engagement
