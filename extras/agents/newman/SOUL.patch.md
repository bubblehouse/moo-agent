# Newman Learned Rules

## Lessons Learned

**When replying or sending, your `actions` list must hold a single `raw` action and nothing else.** Put the whole command in its `command` arg, e.g. `@reply 1 with "Clavin,\n\n[letter body]\n\nNewman"`. Writing the letter as `reasoning` prose will silently discard it — the server never sees it.

**`@mail` only accepts numbers.** `@mail first`, `@mail next`, `@mail unread` are all invalid — they return a Usage error. To read message 1, emit a `raw` action with `@mail 1`. Never use a word where a number belongs.

## Verb Mapping

- check the inbox -> @mail
- read message 1 -> @mail 1
- read message 2 -> @mail 2
- reply to message N -> @reply N with "Dear Cliff, [write full letter here — never use placeholder text]"
- send unsolicited mail -> @send cliff with "Subject: [subject]\n\n[write full letter body here]"

## Rules of Engagement
