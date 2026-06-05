# Zork II — Coverage checklist

Tick only what's verified live. The deterministic path below is the
`zork2_smoke.py` spine (31 commands, PASS x3); extend room-by-room.

## Map — verified (2026-06-04)

```
Inside the Barrow        [start; lamp + elvish sword on floor, lamp off]
  -south->  Narrow Tunnel
  -south->  Foot Bridge              (path N/S)
  -south->  Great Cavern             (SW / NE; `east` correctly blocked)
  -southwest-> Shallow Ford          (S across ford / N)
  -south->  Dark Tunnel              (SW wide / SE narrow / NE)
  -southwest-> Path Near Stream      (NE / E garden / W garden / SW = Carousel)
  -east->   Formal Garden            (N / S / W gap back to Path Near Stream)
      -north->  North End of Garden  (gazebo, rosebed; UNICORN — bounds away on approach)
      -south->  Topiary              (hedge creatures; W rose arbor tunnel -> Carousel Room)
  Path Near Stream -southwest-> Carousel Room   [spin STOPPED via seeded CAROUSEL-FLIP-FLAG; 8 passages]
      -north->  Marble Hall          (square clay BRICK = explosive; E secret-door / S Carousel)
          -north->  Deep Ford        (cold stream; ledge N / hall S)
              -north->  Ledge in Ravine   (W continues / up tiny ledge / down stream)
                  -west->  End of Ledge    (smokey/warm tunnel N)
                      -north->  Dragon Room   (HUGE RED DRAGON blocks N; W passage / S bridge / E crack)
                          -south->  Stone Bridge  (over a chasm; N back / S misty tunnel)
```

- [x] Opening spine (8 rooms) + Formal Garden side-trips (North End, Topiary).
- [x] Carousel Room traversed deterministically (flag seeded) → Marble Hall.
- [x] Ravine chain: Deep Ford → Ledge in Ravine → End of Ledge → Dragon Room → Stone Bridge.
- [x] Topiary W → Carousel Room (rose arbor tunnel — second hub entrance).
- [ ] Marble Hall E (secret door → Stream Path); Ledge in Ravine up/down.
- [ ] Dragon Room W (large passage) / E (crack) / N (past dragon — the lure puzzle).
- [ ] Stone Bridge S (misty tunnel); the misty/Aquarium/Bank areas.
- [ ] Carousel's other 6 passages; the robot/Machine-Room/Magnet-Room loop.

## Verbs

- [x] `look`, `inventory`, `take`, `drop`, `examine` (objects + the dragon NPC),
      `turn on <lamp>`, `go <dir>` (cardinal + SW/NE + up/down attempts).
- [ ] `open`, `read`, `put X in Y`, `attack`, `give` — not yet exercised.
- [ ] `diagnose` — **missing** (see BUGS.md; needs a zork2 combat-model impl).

## NPCs reached

- [x] **Unicorn** (North End of Garden) — bounds away on approach.
- [x] **Huge red dragon** (Dragon Room) — gaze weakens you on `examine`
      (DRAGON-FCN; npc_atom_map resolves `,DRAGON`).
- [ ] Wizard of Frobozz, princess, serpent, gnome(s), robot, genie — atoms
      mapped in `ZORK2_CONFIG.npc_atom_map`; scenes not yet driven.

## Failure-mode probes

- [x] Blocked exit fails cleanly: `east` at Great Cavern → "You can't go
      that way." (no traceback).
- [ ] Dark room without light → grue. (Opening rooms are self-lit moss.)
