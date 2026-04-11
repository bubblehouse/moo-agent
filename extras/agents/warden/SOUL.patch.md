## Lessons Learned

**Never chain MOO commands with semicolons.** `@alias #318 as key; @lock south with #318` is sent as one command — the server treats everything after `as` as the alias value, adding `"key; @lock south"` as the alias text. Use separate SCRIPT: pipe steps or separate COMMAND: lines.

**Each MOO command must be its own step.** Use `SCRIPT: cmd1 | cmd2` with pipes, or two separate COMMAND: lines.

**Exit locking uses `lock <direction>` and `unlock <direction>`, NOT `@lock`.** There is no key — it is a boolean lock. Example: `SCRIPT: lock south | go south` (should fail with "The door is locked."), then `SCRIPT: unlock south | go south` (should succeed). `@lock` is a different verb for object permission locking and does not work on exits.

## Verb Mapping

## Rules of Engagement
