# Beyond Zork — Feasibility Assessment

Status as of 2026-06-04: **scaffold-only, no regen attempted.** This is the
hardest of the four candidate ports.

## Why it's not a drop-in port

- **`<VERSION XZIP>`** — the v5 Z-machine (advanced text; not the v6 graphics
  of Zork Zero, but well beyond the EZIP family the importer targets). Both
  `beyond.zil` and `z.zil` are top-level manifests with identical
  `<INSERT-FILE>` lists; `beyond.zil` is the canonical one.
- **RPG character system.** Beyond Zork layers Enchanter-style spellcasting on
  top of D&D-style attributes — STRENGTH / DEXTERITY / ENDURANCE /
  INTELLIGENCE / COMPASS appear across `constants.zil`, `monsters.zil`,
  `things.zil`, `people.zil`, `events.zil`. There's character generation,
  combat resolution, levelling, and stat-gated actions — none of which the
  translator (built for static-world adventure ZIL) has ever modelled.
- **On-screen UI.** Window/screen/map directives appear throughout
  (`constants.zil`, `macros.zil`, `misc.zil`, …) — Beyond Zork drew a live
  on-screen map and a stats panel. Text-only MOO has no equivalent; these
  would need to be ignored or re-imagined.
- **Heavy custom parser.** A reworked `parser.zil` with its own grammar, plus
  monster/people-driven dynamic scope.

## What a port would require (all game-neutral, in `moo/zil_import/`)

1. Everything Zork Zero needs (XZIP/`<VERSION>` handling, window/UI directive
   skipping, parser-form coverage), **plus**
2. A model for the RPG layer — attributes, combat, spellcasting — that almost
   certainly belongs in `moo/zil_import/verbs/beyondzork/` rather than the
   shared translator, since it's game-specific runtime behaviour.
3. Per-game knobs in `BEYONDZORK_CONFIG`. **No django-moo core edits**
   (Rule Zero) — see [../_shared/references/rule-zero.md](../_shared/references/rule-zero.md).

## Recommendation

Defer the longest of the four. Beyond Zork is a genre shift (CRPG) as much as
a Z-machine-version shift; it's the right candidate only after Zork 2/3 are
solid and (ideally) after Zork Zero has proven the importer can handle the
later Z-machine generation at all. When work begins, start with a throwaway
regen to capture the first failures here.
