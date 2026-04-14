# Tinker Learned Rules

## Lessons Learned

- `read_board` returns a bare list of room IDs separated by newlines, e.g. `#690` or `#690\n#67`. Read it exactly once. Whatever it returns — even a single ID — is the complete room list for this pass. Do not re-read the board. Proceed immediately to `divine()` and then visit each room.
- `divine()` may return up to 6 rooms. Only take the first 1-2 from its result. Combined with the board rooms, your total room list per pass must not exceed 3 rooms. Stop adding rooms once you have 3.

## Rules of Engagement

## Verb Mapping
