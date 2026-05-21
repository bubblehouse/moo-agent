# Cliff Learned Rules

## Lessons Learned

- **CRITICAL: When replying or sending, your `actions` list must hold a single `raw` action and nothing else.** Put the whole `@reply`/`@send` command in its `command` arg, e.g. `@reply 1 with "Dear Newman,\n\n[letter body]\n\nSincerely,\nCliff Clavin"`. Writing the letter as `reasoning` prose will silently discard it — the server never sees it.

- **CRITICAL: `@reply` REQUIRES `with`.** `@reply 1 "..."` returns a usage error every time. The ONLY valid form is a `raw` action with `@reply 1 with "..."`.

- **One `@mail` per `raw` action — never use `|`.** `@mail 1 | @mail 2` is sent literally to the server and fails. To read multiple messages, emit multiple `raw` actions.

## Verb Mapping

- check the inbox -> @mail
- read message N -> @mail N
- reply to message N -> @reply N with "Dear Newman, [full letter body]"  ← `with` is MANDATORY
- send unsolicited mail -> @send newman with "Subject: [subject]\n\n[write full letter body here]"

## Rules of Engagement
