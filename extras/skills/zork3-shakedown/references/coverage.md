# Zork III — Coverage checklist

Master to-do list for shakedown. Walk it section by section; tick only what
you've actually verified live. Patterned after
`../../zork-shakedown/references/coverage.md` — flesh out the room/verb lists
from the source (zork3's dungeon + actions files) during the first session.

## Movement

- [ ] Opening room reached on connect; `look` returns its description.
- [ ] Canonical opening sequence walked (fill in once mapped).

## Verbs

- [ ] Core verbs exercised: `take`, `drop`, `examine`, `open`, `read`,
      `inventory`, `go <dir>`, `put X in Y`.

## Failure-mode probes

- [ ] Blocked exits fail correctly (not with a traceback).
- [ ] Dark rooms without light fail correctly.
