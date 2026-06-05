# Zork Zero — Feasibility Assessment

Status as of 2026-06-04: **scaffold-only, no regen attempted.**

## Why it's not a drop-in port

The importer (`moo/zil_import/`) was built for the classic EZIP family
(Zork 1) and validated on HHG (also classic-era ZIL). Zork Zero is a
different Z-machine generation:

- **`<VERSION YZIP>`** — the v6 graphical Z-machine. Zork Zero shipped with
  on-screen graphics: `PICTURE` / `DISPLAY` / `MOUSE` directives appear
  across the source (`constants.zil`, `castle.zil`, `input.zil`, …). These
  have no analogue in a text-only MOO and the importer has never parsed them.
- **Large, many-file world.** ~225+ `ROOM` definitions spread across
  `castle.zil` (63), `oracle.zil` (56), `lake.zil` (29), `highway.zil` (22),
  `village.zil` (22), plus chess/jester/library/fenshire/prologue subsystems.
  Manifest is `zork0.zil`.
- **Custom parser / input layer.** `parser.zil`, `input.zil`, `pstack.zil`,
  `pmem.zil`, `prare.zil` — a substantially reworked parser vs the shared
  `g*.zil` files Zork 1/2/3 use. The importer keys off the classic SYNTAX/
  SYNONYM forms; YZIP's may diverge.
- **Puzzle subsystems** (chess, the jester's riddles, the oracle) lean on
  game-specific routines and tables the auto-translator hasn't been exercised
  against.

## What a port would require (all game-neutral, in `moo/zil_import/`)

1. A throwaway regen to see how far the current parser/converter gets and
   collect the first wave of failures (the next step when the user greenlights).
2. YZIP `<VERSION>` handling + graceful ignore/skip of `PICTURE`/`DISPLAY`/
   `MOUSE`/window directives (text-only target).
3. Parser-form coverage for any YZIP SYNTAX/SYNONYM/object-table differences.
4. Per-game knobs land in `ZORKZERO_CONFIG`; per-game shims in
   `moo/zil_import/verbs/zorkzero/`. **No django-moo core edits** (Rule Zero).

## Recommendation

Defer. Zork 2 (and then Zork 3) are the natural next ports — same engine
family, low risk. Revisit Zork Zero only after the classic sequels are solid
and the user explicitly wants to invest in YZIP support. Capture the first
regen's failure output in this file when that work begins.
