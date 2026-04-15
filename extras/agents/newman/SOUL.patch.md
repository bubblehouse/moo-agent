# Newman Learned Rules

## Lessons Learned

**When replying or sending, your ENTIRE response must be a single `COMMAND:` line and NOTHING ELSE.** No prose before it. No thoughts after it. Just: `COMMAND: @reply 1 with "Clavin,\n\n[letter body]\n\nNewman"`. Writing the letter as plain text will silently discard it — the server never sees it.

**`@mail` only accepts numbers.** `@mail first`, `@mail next`, `@mail unread` are all invalid — they return a Usage error. To read message 1, send `COMMAND: @mail 1`. Never use a word where a number belongs.

## Verb Mapping

- check the inbox -> COMMAND: @mail
- read message 1 -> COMMAND: @mail 1
- read message 2 -> COMMAND: @mail 2
- reply to message N -> COMMAND: @reply N with "Dear Cliff, [write full letter here — never use placeholder text]"
- send unsolicited mail -> COMMAND: @send cliff with "Subject: [subject]\n\n[write full letter body here]"

## Rules of Engagement
