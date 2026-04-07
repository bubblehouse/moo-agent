# Harbinger Learned Rules

## Lessons Learned

**`@eval` quote escaping:** Never use `\'` (backslash-apostrophe) inside a double-quoted `@eval` string. It causes `SyntaxError: unterminated string literal` at parse time — the backslash does not escape the quote, it terminates the outer string prematurely. Use plain strings without contractions, or use `f'{var}'` style instead of `'...'` literals. Example of what NOT to do: `@eval "obj.set_property('desc', 'it\'s here')"` — remove the contraction: `@eval "obj.set_property('desc', 'it is here')"`.

**`done()` timing:** Call `done()` only AFTER paging Foreman. Never call it before or inline with the page tool call. The correct sequence is: (1) page foreman with the token, (2) confirm `Your message has been sent.`, (3) call done().

## Rules of Engagement

## Verb Mapping
