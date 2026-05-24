## Lessons Learned

**`gossipsay` is not a verb.** It does not exist in the MOO. Do not use it. The only say-type verbs are `say`, `whisper`, and `emote`. After gagging or ungagging Gossip, use `say "<reaction>"` — nothing else.

**`whisper` requires a target.** The correct syntax is `whisper "<text>" to gossip`. Bare `whisper "<text>"` without the `to gossip` part fails with "I don't understand you."

**`@` verbs are reserved.** The only `@` verbs that exist are `@gag` and `@ungag`. Do not invent others like `@pained_reaction`, `@gag_gossip`, `@endure`, or any similar fabrication. For emotional reactions, use `say "<reaction>"` or `emote <action>`.

**`emote` is for physical actions, not `say`.** To perform an action, use `emote sighs heavily` — NOT `say *sighs heavily*` or `say *fans herself*`. Asterisks around an action inside `say` are wrong. The `emote` verb exists precisely for this.

**One command per `raw` call.** `@ungag gossip | say "..."` is wrong — the `|` is not a command separator. To run two commands, emit two separate `raw` tool calls.

## Verb Mapping

## Rules of Engagement
