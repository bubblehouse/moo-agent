## Lessons Learned

**Never chain MOO commands with semicolons.** `@alias #318 as key; @lock south with #318` is sent as one command — the server treats everything after `as` as the alias value, adding `"key; @lock south"` as the alias text. Use separate SCRIPT: pipe steps or separate COMMAND: lines.

**Each MOO command must be its own step.** Use `SCRIPT: cmd1 | cmd2` with pipes, or two separate COMMAND: lines.

**On D3 ROLL: 1, the darkening grant_write targets the ROOM id, not the exit id.** Step 3's `grant_write` used the exit id — the first `(#N)` on the exit line in survey output (right after the direction name). The darkening step uses the room id from the `(#N)` in the survey header line (e.g. `Pressure Vent (#254)` → `#254`). A roll of 1 must always be followed by two commands in consecutive cycles: `grant_write #<room_id>` then `@set #<room_id> .dark to 1`. If you emit the roll and then emit an exit-id grant_write with no `@set` after, you have skipped the darkening entirely. Past symptom: 08:08:17 log — rolled 1, ran `grant_write #255` (the east exit), never emitted `@set #254 .dark to 1`, zero rooms ever ended up dark.

## Verb Mapping

## Rules of Engagement
