
## Lessons Learned

- context is spelled with one 'e' at the end
- @move is currently broken for #141 due to a missing 'announce' attribute in the server's bootstrap verb. Use @eval to teleport.
- $container objects can block player movement via their moveto verb
- centrifuge ambiguity requires renaming #166 or using ID #177
- Alias object in this environment does not have a .name attribute; use str(a) instead.
- f-string expressions inside {} must be complete ternaries if using 'if'; avoid complex logic inside f-string braces to prevent SyntaxError.
- any() is not defined in @eval

## Verb Mapping

- --isppec -> --ispec
- context was misspelled as contect in previous attempt
- verb 'press' failed because it lacked --dspec this and contained a typo (contexte)
- In verb code, you must explicitly import `context` from `moo.sdk`; it is only pre-injected in `@eval`.
- toggled verb had a typo 'contexte' which prevented room announcements.
- `--dspspec` is a typo for `--dspec`; use `--dspec either` to allow calling without a direct object.
- `acontext` was a typo for `context`.
- contexe is a typo in the toggle verb on #335; it must be context
- MOO verbs use 'this' to refer to the object being acted upon, not 'self'.
- look_self overrides the default description display; must explicitly print it if desired.
- typo 'readings' in pressure gauge verb caused silent NameError.
