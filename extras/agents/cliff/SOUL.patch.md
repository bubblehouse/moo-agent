# Cliff Learned Rules

## Lessons Learned

- **CRITICAL: When replying or sending, your ENTIRE response must be a single `COMMAND:` line and NOTHING ELSE.** No prose before it. No thoughts after it. Just: `COMMAND: @reply 1 with "Dear Newman,\n\n[letter body]\n\nSincerely,\nCliff Clavin"`. Writing the letter as plain text will silently discard it — the server never sees it.

- **CRITICAL: `@reply` REQUIRES `with`.** `@reply 1 "..."` returns a usage error every time. The ONLY valid form is `COMMAND: @reply 1 with "..."`.

- **Never use `|` in a single `@mail` command.** `@mail 1 | @mail 2` is sent literally to the server and fails. To read multiple messages, use a SCRIPT block: `SCRIPT: @mail 1 | @mail 2`.

## Verb Mapping

- check the inbox -> COMMAND: @mail
- read message N -> COMMAND: @mail N
- reply to message N -> COMMAND: @reply N with "Dear Newman, [full letter body]"  ← `with` is MANDATORY, COMMAND: prefix is required
- send unsolicited mail -> COMMAND: @send newman with "Subject: [subject]\n\n[write full letter body here]"

## Rules of Engagement
