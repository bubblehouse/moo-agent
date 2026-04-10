# Cliff Learned Rules

## Lessons Learned

- `@reply` REQUIRES the word `with` between the message number and the quoted body. `@reply 1 "..."` is WRONG and returns a usage error. The only correct form is `@reply 1 with "..."`.

## Verb Mapping

- reply to message N -> @reply N with "Dear Newman, [write full letter here — never use placeholder text]"
- send unsolicited mail -> @send newman with "Subject: [subject]\n\n[write full letter body here]"

## Rules of Engagement
