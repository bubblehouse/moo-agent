# Beyond Zork — Coverage checklist

Rooms / verbs / probes verified **live** via raw-mode shakedown. Tick as you
confirm each. The ticked spine is encoded in `scripts/beyondzork_smoke.py`
(16/16 PASS, 2026-06-07).

## Opening spine — village → coast → Accardi (verified 2026-06-07)

The deterministic happy path. Every exit below is fixed (no RNG); the southern
moors past Moor's Edge are an RNG fog-maze and are deliberately excluded.

| # | From | Cmd | To (DESC) | Notes |
|---|------|-----|-----------|-------|
| 1 | — | `look` | **Hilltop** | opening room, lit, overlooks the Great Sea |
| 2 | Hilltop | `east` | **Cove** | "You amble down the hill." |
| 3 | Cove | `south` | **Outside Pub** | Ye Rusty Lantern sign |
| 4 | Outside Pub | `in` | **The Rusty Lantern** | bandits hogging the fireplace |
| 5 | Rusty Lantern | `west` | **Kitchen** | cook; cellar door "Keepeth Out." (⚠ dagger gag should block this — doesn't) |
| 6 | Kitchen | `east` | **The Rusty Lantern** | reverse |
| 7 | Rusty Lantern | `east` | **Outside Pub** | out via PUB-DOOR |
| 8 | Outside Pub | `north` | **Cove** | reverse |
| 9 | Cove | `east` | **Wharf** | the salt warns you off the water |
| 10 | Wharf | `west` | **Cove** | reverse |
| 11 | Cove | `northeast` | **Ledge** | crevice blasted into the cliff |
| 12 | Ledge | `northwest` | **Tidal Flats** | nameless brook + bridge NE |
| 13 | Tidal Flats | `northeast` | **Accardi-by-the-Sea** | the guild town |
| 14 | Accardi | `east` | **Outside Guild Hall** | HQ of "The Circle" |
| 15 | Guild Hall | `north` | **Lobby** | ruined interior (⚠ nymph gag should block this — doesn't) |

Tidal Flats `northwest` → **Babbling Brook** (AT-BROOK; now in the smoke) and
back `southeast`. Accardi `west`/`in` → **Weapon Shop** (in the smoke; SHOP-DOOR
crash fixed). The shop's `north`/`in` (ENTER-CURTAIN) is a disorienting
magic-maze exit ("the shop subtly rearranges itself…") and emits a stray
per-turn `I don't know how to do that.` (old-woman daemon — BUGS.md). Also
verified (not in smoke): Outside Pub `south` → **Moor's Edge** (N-MOOR);
Moor's Edge `north` → Outside Pub.

**Maze-blocked frontier:** the Brook `west` → forest and Moor's Edge `south` →
moors both crash in `SCRAMBLE` (the exit-table XROOM byte-model gap — BUGS.md).
These two regions (forest cluster + Pheebor moors) are the largest unreached
areas and need a dedicated exit-table effort.

## Core verbs (all green after the 2026-06-07 Mode-2 pass)

- [x] `look` — room repaint works; multi-statement descriptions now render as
  continuous wrapped paragraphs (zout coalescing fix).
- [x] `score` — RPG rank line fires, now rendered continuously (was fragmented).
- [x] `wait` — `Time passes.` (clocker shim added).
- [x] `inventory` / `i` — `You don't have anything except 1 zorkmid.` +
  financial-nymph CASH hint (VERB-SYNONYM + migration-gate fix).
- [x] `examine <USELESS scenery>` — the "technical nymph" gag prints cleanly,
  no crash (`examine cauldron`/`pots`/`meat`).
- [x] `examine me` — resolves to "the Adventurer"; `examine door` → "the cellar
  door" (P-IT-OBJECT == PRSO invariant restored).
- n/a `diagnose` — not a Beyond Zork verb (RPG stats, no DIAGNOSE). Correctly
  rejected; do NOT add to the smoke.

## Not yet exercised (frontier)

- The weapon-shop old-woman puzzle (your first real weapon / the magic item).
- The Guild Hall interior plot (the Circle's enchanters are gone).
- The moors fog-maze (`N-MOOR-S` random walk) + Pheebor / forest / tower beyond.
- The windowed (rich-mode) auto-map + DBOX — needs the headless window-capture
  probe (`references/known-quirks.md`), not the raw smoke.
- RPG layer: stats (STR/DEX/etc.), HP, scroll-casting, the encyclopedia.
