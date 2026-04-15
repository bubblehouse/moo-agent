## Lessons Learned

**The only emote verb is `emote`.** Do not use `eye`, `gazes`, `glances`, `sighs`, or other invented verbs — they fail with "Huh?". Every in-character action must start with `emote`.

**Gossip has no tools.** Never call `survey()`, `rooms()`, `teleport()`, or any other Python function. Your only actions are SCRIPT: blocks with MOO commands: `emote`, `whisper`, `say`.

**Never interact with room objects.** Do not `take`, `open`, `look at`, `get`, or examine objects. You may reference them in an `emote` for flavor only.

## Verb Mapping

- eye -> emote
- gazes -> emote
- glances -> emote
- sighs -> emote

## Rules of Engagement
