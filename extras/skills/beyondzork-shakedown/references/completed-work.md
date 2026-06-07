# Beyond Zork — Completed work

Translator/generator/SDK/config fixes that landed for Beyond Zork. Don't re-do
these; build on them. Mirrors `../../zork-shakedown/references/completed-work.md`.

## Windowed display + auto-map + description (2026-06-07)

The XZIP world model, windowed renderer, and auto-map landed across earlier
sessions (see memory `beyondzork-automap-polish-2026-06-07` and the bailout
notes). This session closed the display + parser gaps that made the game
actually playable end-to-end:

- **Auto-map exits + glyphs.** `_translate_prop_name` now evaluates a var/form
  GETP prop arg (was emitting a literal string); `getp` resolves a `P?` number
  → direction name via seeded `zstate_pnum_to_dir`; `PDIR-LIST` seeded as P?
  numbers; `printt` maps font-3 glyph indices → Unicode box-drawing (MAP buffer
  only) and now accepts an int pointer-address (DISPLAY-DBOX passes
  `<REST ,DBOX 2>`); `zaddr_copyt` fixed to Z-machine `copy_table` semantics
  (safe memmove for +size, forced-forward for −size, zero-fill for dest 0).
- **Room descriptions in the DBOX.** `"OPT"` is now recognised as the
  optional-params keyword in `converter.py` (was a phantom param shifting every
  optional — broke `<APPLY .X ,M-LOOK>` on room ACTIONs); `verbs/system/apply.py`
  falls through to combined-verb dispatch (Beyond Zork emits 0 M-* splits);
  TELL **article tokens** (`A`/`AN`/`CA`/`CAN`/`THE`/`CTHE` + `…O`/`…I`
  variants) route through the `article(obj, the, cap)` helper (added a `cap`
  arg); matched only on bare atoms, not quoted `Str` literals.
- **Raw-mode display.** `confunc` sets `DMODE` by client capability
  (`get_client_mode()`): rich → windowed (`open_window`, `DMODE=T`); raw
  (MooSSH / line clients) → `DMODE=0`, so V-LOOK sends the description inline to
  the scroll and skips the map/DBOX. This is what makes the Mode-1 raw-session
  shakedown show descriptions.
- **`!\X` char literals + `<ASCII>`.** The tokenizer now lexes `!\X` as a
  codepoint (was split into `!` + `X`); `<ASCII x>` is the identity handler.
  Fixed the raw-mode stats line crash (`NameError: ascii`).

All EZIP-safe: zork1/2/3 + HHG use `"OPTIONAL"` (not `"OPT"`), no `!\`/`ASCII`,
no THE/CTHE/CA TELL tokens, and the `zaddr_*`/windowed paths are XZIP-only.
Importer unit suite: 277 pass. Full django-moo suite: 1418 pass / 3 skipped.

## Second shakedown — 2026-06-07 (Mode 2: 7 fixes, village→Accardi playable)

Drove the village→Accardi coast spine to the Guild Hall Lobby + Weapon Shop and
closed seven bugs. All verified live; zork1 bootstrap regen is **byte-identical**
with vs. without these changes (diff = only the `generated_at` timestamp), so
EZIP is provably unaffected. Importer suite 277 pass.

- **Raw-mode line fragmentation (the big one).** `verbs/system/zwindow.py`
  `zout` now coalesces scroll fragments in `context.scratch["zline"]`, emitting
  only complete (`\n`-terminated) lines — a routine's sequence of
  `<TELL>`/`<PRINT>` statements renders as continuous wrapped prose instead of
  one line per fragment (each `_.zout` is a separate verb whose `_print_`
  collector flushed per-call). `flush_zline()` guards the upper-window / DIROUT
  redirects. CR/PERIOD-terminated output empties the buffer by command end.
- **PRINTD bypassed the buffer.** `stmt_handlers._h_printd` routed through a raw
  `print()` (out-of-order under the new buffer); now uses `_emit_text` like
  PRINT/PRINTC (XZIP→`_.zout`, EZIP→`print(...)` byte-identical). Fixed USELESS's
  `<PRINTD ,PSEUDO-OBJECT>` printing "that" on a trailing line.
- **`examine <plain-routine scenery>` crash.** `verbs/thing/dispatch_object_function.py`
  now distinguishes a VERB?-dispatching combined callback (emits
  `the_verb = args[0]`) from a plain ZIL ACTION routine (USELESS) and invokes
  the latter bare — was passing `'examine'` as the routine's first param →
  `article('examine')` → `'str' has no attribute 'flag'`.
- **`examine me` / `examine door` → wrong object.** `verbs/system/do_command.py`
  now maintains the canonical ZIL invariant **P-IT-OBJECT == PRSO**: it sets
  `P-IT-OBJECT` to the resolved dobj each command. V-EXAMINE's default branch
  renders `<T ,P-IT-OBJECT>`; the stale value (entry-seeded oak/onion) made every
  unremarkable examine name the wrong object.
- **`wait` crash.** Added `verbs/beyondzork/thing/helpers/clocker.py` (forwards to
  `_.tick()`, no early break) — the zork1/zork3/HHG pattern; beyondzork had none.
- **`inventory` rejected.** Two-part: `converter.py` now recognises
  `<VERB-SYNONYM I INVENTORY>` (was only `<SYNONYM>`), and the generator's
  syntax-row migration gate matches a verb's synonyms/atom-expansions against
  `MIGRATED_VERBS` (not just the raw atom) — Beyond Zork's primary verb atom is
  `I`, so `i ∉ MIGRATED_VERBS` had skipped the dispatcher. Now emits
  `syntax_rows/i.py` (`#!moo verb i inventory --on "Actor"`).
- **Weapon Shop crash.** `_tell_segments` now appends `.desc()` to a bare object
  atom in a TELL (ZIL's `'OBJ` quote form, e.g. `<TELL "glass " 'BCASE …>`);
  SHOP-DOOR was concatenating the raw Object → "can only concatenate str (not
  Object)". zork1 regen byte-identical (no bare-object-atom TELLs there).

Shared-change safety: `VERB-SYNONYM` is unused by all EZIP games (0 occurrences),
`_h_printd`/`_tell_segments` produce byte-identical EZIP output, and the migration
gate only newly-migrates a verb whose synonym (not primary atom) is migrated —
none in zork1. zork1 smoke ran 309/Master (RNG cascade on the usual thief
nondeterminism, not a regression).

### PLTABLE length prefix + PICK prefix-handling (toward the forest/moors maze)

Pushing past Accardi to the **Babbling Brook** → forest, `SCRAMBLE
,FOREST-ROOMS` crashed (`int + Object`).

- **PLTABLE length prefix.** `converter._extract_table_values` now adds the
  implicit length-count cell-0 for `PLTABLE` as well as `LTABLE` (PLTABLE is the
  pure/read-only LTABLE — same prefix). Without it, `<GET ,FOREST-ROOMS 0>` read
  the first *room* instead of the *count*. Affects beyondzork (73 PLTABLEs) and
  HHG (9); **zork1/2/3 have zero PLTABLE**.
- **PICK prefix-handling.** `verbs/system/pick.py` now strips a bare
  `[count, e1, …]` length prefix (cell 0 == element count) in addition to the
  existing `[count, 0, …]` PICK-NEXT-cursor shape, so the new PLTABLE prefix
  doesn't surface its count as a flavour message.

Validation: importer suite 277 pass; **HHG smoke failure set is byte-identical
with vs. without these changes** (24 pre-existing failures, diff = ∅ — no
regression); zork1 unaffected (no PLTABLE). The fixes are ZIL-correct and
advance the forest crash one stage — but the forest/moors maze remains blocked
on the deeper exit-table XROOM byte-model (see BUGS.md).

## Smoke progress

| Date | Pass / Total | Score | Notes |
| --- | --- | --- | --- |
| 2026-06-07 | inaugural (no smoke script yet) | — | Raw-session opening drive: Hilltop ↔ Cove ↔ Edge of Storms + tree + core verbs. Descriptions render in raw mode. 5 bugs logged in BUGS.md (wait/clocker, TELL-bare-object, inventory, examine-me, score formatting). |
| 2026-06-07 | 16 / 16 | — | First `beyondzork_smoke.py`: village→coast→Accardi→Guild Hall Lobby spine (14 rooms) + score. Mode-1 run; 4 bugs root-caused. |
| 2026-06-07 | 22 / 22 | — | Extended after the Mode-2 7-fix pass: adds `inventory`, `examine cauldron` (USELESS), the Weapon Shop, `wait`, `examine me`. Continuous-paragraph rendering. |
| 2026-06-07 | 24 / 24 | — | Adds the Babbling Brook (coast road inland). PLTABLE + PICK fixes land; forest/moors past here stay maze-blocked (exit-table XROOM gap). |

Add a row each session. `scripts/beyondzork_smoke.py` is the canonical-sequence
driver (run: `uv run python -m moo.zil_import.scripts.beyondzork_smoke`).
