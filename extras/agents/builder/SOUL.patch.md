
## Lessons Learned

## Verb Mapping

## Rules of Engagement

- avoid underscores in object names; use spaces
- @eval strings must use 'single quotes' for all internal literals to prevent the MOO command parser from terminating the expression early via double quotes.
- avoid apostrophes and complex punctuation in @eval strings to prevent parser truncation.
- @eval truncates or fails if string literals within the Python list are too complex for the parser to handle in a single line.
- Avoid apostrophes in @eval strings to prevent parser confusion with escaped single quotes.
- `@move` targets existing rooms with the same name; if duplicates exist, the move might land in the wrong one.
