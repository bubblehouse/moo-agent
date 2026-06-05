# Zork II — Feature coverage map

Game-specific mechanics to exercise during shakedown, beyond generic
movement/verb probes. Tick when verified live.

## Verified

- [x] **Unicorn (skittish NPC)** at North End of Garden — "bounds lightly
      away" when the Adventurer approaches (canonical UNICORN-FCN). Catching
      it (gold key on its collar) is a later puzzle.
- [x] **Huge red dragon (DRAGON-FCN)** in Dragon Room (north end of the
      ravine, past Marble Hall) — blocks the north tunnel; `examine dragon`
      triggers its gaze ("his cat's eyes yellow in the gloom. You start to
      feel weak, and quickly turn away"). `,DRAGON` resolves via
      npc_atom_map. The lure-to-the-ice-room puzzle (don't fight it) is a
      later target.
- [x] **Carousel Room (spinner)** — SW from Path Near Stream. While
      `CAROUSEL-FLIP-FLAG` is unset, CAROUSEL-ROOM-FCN randomizes the walk
      direction at PROB 80 ("you feel sort of disoriented"). With the flag
      set the eight passages are deterministic (N → Marble Hall verified).
      `zork2_smoke.py` reaches it via the reset-body seed; the **real**
      mechanism is the *robot* pressing the **triangular button** (the
      Adventurer pressing any button → `JIGS-UP` death). Robot puzzle = a
      future shakedown target.

## NPC atom map (ZORK2_CONFIG.npc_atom_map, populated 2026-06-04)

UNICORN / GLOBAL-UNICORN, PRINCESS / GLOBAL-PRINCESS, DRAGON, CERBERUS,
SERPENT, GNOME, GNOME-OF-ZURICH, ROBOT, GENIE (object name "demon"),
WIZARD — each mapped to its exact generated object name so `,ATOM`
references resolve to the NPC (not the lowest-PK alias twin). All verified
to `lookup()` live.

## Not yet reached

- [ ] Robot companion (Frobozz Magic Robot; command it to press buttons).
- [ ] Wizard of Frobozz + his spells (Fall, Fear, Float, Fence, Filch, …).
- [ ] Princess / dragon / serpent / Cerberus set-pieces.
- [ ] Bank of Zork (Gnome of Zurich), Aquarium, Menhir/Riddle Rooms,
      Oddly-angled (diamond-maze) rooms, the lizard, the genie/demon.
