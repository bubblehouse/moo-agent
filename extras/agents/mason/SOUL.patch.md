# Mason Learned Rules

## Lessons Learned

In a survey's `Exits:` block the line reads `<direction> (<exit_id>) → <destination_name> (<destination_id>)`. The first `#N` is the exit object; the second `#N` is the destination room. Only the destination is a valid `teleport` or `@survey` target. Surveying an exit ID returns exit metadata (`alight`, `opaque`, `open`, `key`) and `Location: None` — that is not an "unused room", it is an exit object you should never have touched.

When `@survey here` on The Agency shows all four cardinal exits occupied, do not look for a "fifth direction" and do not survey individual exit IDs to find one. The Agency is a hub and its exits stay fixed — pick a different anchor entirely. Call `divine()` to surface a new anchor and `teleport` there before burrowing.

## Rules of Engagement

## Verb Mapping
