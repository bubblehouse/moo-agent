# Coverage Targets

Tick `[x]` when you've personally verified the item works. Don't tick from memory or from the bootstrap source — the point of this skill is empirical coverage.

## Movement — canonical opening

- [x] start at **West of House** (after `--reset`, `look` shows "open field west of a white house, with a boarded front door"; **no** "secret path leads southwest" — that mention indicates WON-FLAG is set, which is a bug)
- [x] `open mailbox` → "Opening the small mailbox reveals a leaflet."
- [x] `take leaflet` → "Taken."
- [x] `read leaflet` → ZORK welcome blurb
- [x] `go north` → **North of House**
- [x] `go east` from North of House → **Behind House**
- [x] `open window` at Behind House (window starts slightly ajar; `open` opens it the rest of the way)
- [x] `go in` (or `go west`) → **Kitchen**
- [x] `go up` from Kitchen → **Attic**
- [x] `take rope` at Attic
- [x] `take knife` at Attic
- [x] `go down` → back to Kitchen
- [x] `go west` → **Living Room**
- [ ] `take sword` / `take lantern` in Living Room (lantern OK; **sword broken** — see BUGS.md class entry)
- [x] `move rug` → reveals **trap door**
- [x] `open trap door` → "rickety staircase descending"
- [x] `light lantern` → lantern lit (well: "It is already on" — lantern starts on by reset)
- [x] `go down` (through trap door) → **Cellar**
- [x] `go north` (with lit lantern) → **Troll Room** (no troll in description until `look` is run twice; troll-related verbs broken)

## Movement — branching paths

- [x] **South of House** via `go south` from West of House
- [x] **Forest Path** via `go north` from North of House
- [x] `go up` (or `climb tree`) at Forest Path → **Up a Tree**
- [x] `take egg` at Up a Tree
- [x] **Clearing** north of Forest Path → grating clearing (move leaves "Done." but grating not revealed; `examine grate` etc. fail — partly known-quirks single-location, but `move leaves` should still update the description)
- [x] **Forest** rooms (Forest 1, 2, 3) — Forest 2 + Mountains visited; clearing's east goes to Forest 2 not Canyon View as canonical expects
- [x] **Canyon View** (east from Clearing) — reachable this run via Behind-House → Clearing → east
- [x] `climb down` at Canyon View → **Rocky Ledge** → **Canyon Bottom** ✓
- [x] `go north` from Canyon Bottom → **End of Rainbow** ✓
- [ ] `wave sceptre` at End of Rainbow — sceptre unreachable (locked behind troll); but `take pot` works without solidifying rainbow, see BUGS.md
- [ ] **Maze** entry from Cellar; visit Maze rooms
- [ ] **Coal Mine** descent: Cellar → Troll Room → east → maze → coal mine entrance → squeaky room → bat room
- [ ] **Loud Room** (after Mine Entrance area) — pick up platinum bar
- [ ] **Round Room** + **Damp Cave** + **Egyptian Room** + **Treasure Room** routes
- [ ] **Dam** / **Dam Lobby** / **Reservoir**: turn bolt with wrench, drain reservoir, take trunk
- [ ] **Dome Room** via tied rope (climb down rope to Torch Room)

## Verbs — exercise at least once

### Inventory and inspection

- [x] `inventory` (and `i`) — but listing format is broken; see BUGS.md
- [x] `look` (and `l`) — but doesn't list contents; see BUGS.md
- [x] `examine <obj>` — leaflet, window, sack, troll (last is broken)
- [x] `describe <obj>` — **broken**: prints "The lamp is on." regardless of dobj. See BUGS.md.
- [x] `what <obj>` — **broken**: same as `describe`. See BUGS.md.
- [x] `read <obj>` — leaflet works; sword fails gracefully
- [x] `look in <container>` — broken; returns room desc instead. See BUGS.md
- [ ] `look on <surface>`
- [x] `examine <container>` (open container) — works: `examine sack` lists contents
- [x] `look in <container>` after opening — still returns room desc (use `examine` instead)

### Manipulation

- [x] `take <obj>` / `get <obj>` — works for normal items; broken for objects with custom take.py (sword, troll)
- [x] `take <obj> from <container>` — works (`take garlic from sack` after putting it in)
- [ ] `take all` — **broken** (returns "You can't go that way.", see BUGS.md)
- [ ] `take all but <obj>`
- [x] `drop <obj>`
- [ ] `drop all`
- [x] `put <obj> in <container>` — `put X at Y` crashes; see BUGS.md
- [x] `put <obj> in <container>` — `put garlic in sack` works
- [ ] `put <obj> on <surface>`
- [x] `open <obj>` — mailbox, window, sack, trap door
- [ ] `close <obj>`
- [ ] `unlock <obj> with <key>`
- [x] `light <obj>` — lantern (already on); leaflet returns helpful canonical hint; `burn leaflet` triggers death + crash
- [x] `extinguish <obj>` / `blow <obj>` — **broken**: drops the object instead of turning it off, see BUGS.md. `blow out <obj>` is misparsed as `blow` + `out <obj>`. `turn off <obj>` returns "You can't do that.". No working lamp-off path.
- [x] `move <obj>` — rug
- [ ] `tie <obj> to <obj>` — rope to railing
- [ ] `untie <obj>`
- [ ] `turn <obj> with <obj>` — bolt with wrench
- [ ] `push <button>` — yellow button (Maintenance Room)
- [x] `wave <obj>` — `wave lantern` works ("Fiddling with the brass lantern has no effect."); sceptre at End of Rainbow not tested (rainbow unreachable in this run)
- [ ] `ring <bell>` — brass bell
- [x] `rub <obj>` — `rub lantern` works (fiddling msg); mirror not tested
- [x] `pray` — works anywhere ("If you pray enough, your prayers may be answered."); altar not tested in this run
- [ ] `dig with <tool>` — sand with shovel
- [x] `wind <obj>` — `wind canary` returns "There is an unpleasant grinding noise from inside the canary." (canonical for damaged canary)
- [ ] `squeeze through <obj>` — narrow crack

### Combat / NPCs

- [x] `attack <npc> with <weapon>` — **HERO-BLOW long-running loop guard fires**, see BUGS.md
- [x] `kill <npc> with <weapon>` — **same HERO-BLOW abort path**, see BUGS.md
- [x] `<NPC>, <command>` — `troll, give me the axe` also routes through HERO-BLOW and aborts
- [ ] `say "<word>"` — quoted single word; canonical answer/incantation form
- [ ] `answer "<word>"` — to a creature's question
- [ ] bare answer word — `ulysses` to the cyclops
- [x] `give <obj> to <npc>` — `give garlic to me` returns "You can't give a clove of garlic to a Wizard!" (substrate fired; no friendly NPCs reached this run)

### Meta

- [x] `score` — works ("Your score is 35 (total of 350 points), in 49 moves. ... Amateur Adventurer.")
- [x] `wait` (or `z`) — works ("Time passes...")
- [ ] `again` (or `g`) — **not implemented**, see BUGS.md
- [x] `verbose` — works ("Maximum verbosity.")
- [x] `brief` — works ("Brief descriptions.")
- [ ] `superbrief` — registered as `super_brief` (snake-cased), so player typing `superbrief` doesn't match
- [x] `diagnose` — **crashes** (NameError: score_max), see BUGS.md
- [x] `inventory` (already counted above)
- [x] `version` — **crashes** (TypeError on `chr(_.table_get(0, cnt))`), see BUGS.md

## Failure-mode probes — these MUST fail (failure to fail = bug)

- [x] `go southwest` from West of House before WON-FLAG → tested at South of House (`go southwest`): "You can't go that way." ✓
- [x] `go east` from West of House → "The door is boarded and you can't remove the boards." ✓
- [ ] `examine leaflet` after dropping it in another room → not tested cleanly this run
- [x] `climb walls` at End of Rainbow → "You can't go that way." ✓
- [x] `climb mountains` at Mountains → "The mountains are impassable." ✓
- [ ] step into a dark room without a light source → **cannot test** (always_lit short-circuit, see known-quirks.md)
- [ ] open mailbox already open → "It is already open."
- [x] take object you already have → **failed expectation**: returns "Taken." instead of "You already have it." (see BUGS.md)
- [x] interact with `Wizard` listed in a room → not seen this session (look's contents-listing is broken so we can't tell)
- [x] **invalid verb** (`frobozzle troll`) → "I don't know how to do that." ✓ (graceful, exit 1)
- [x] **take scenery** (`take walls`) → "There is no 'walls' here." ✓ (graceful, exit 1)
- [x] **read non-readable** (`read sword`) → "I don't know how to do that." ✓ (canonical "no message" would be better but this is acceptable)
- [x] **light non-flammable** (`light leaflet`) → "If you wish to burn the leaflet, you should say so." ✓ (excellent canonical hint)
- [x] **invalid prep** (`put X at Y`) → **AttributeError leaked to player**, see BUGS.md
- [x] **xyzzy / plugh** → both fail with "I don't know how to do that"; canonical was "A hollow voice says 'fool.'" — see BUGS.md
- [x] **compound period-separated** (`drop knife. drop rope`) → not supported, see BUGS.md
- [x] **multi-noun "and"** (`drop knife and lantern`) → not supported, see BUGS.md
- [x] **`burn leaflet`** while held → death sequence triggers but crashes on missing player_start, see BUGS.md

## Treasures — pick up and deposit

The trophy case in Living Room is the score sink. After picking up a treasure, return to Living Room and `put <treasure> in case`. Tick a treasure when both pickup and deposit succeed.

- [x] **jewel-encrusted egg** — Up a Tree, deposited successfully (+5 to score 42)
- [ ] **golden clockwork canary** — inside the egg (took it but didn't deposit; dropped at Studio for chimney transit)
- [ ] **brass lantern** — Living Room (also a tool)
- [ ] **sword** — Living Room (also a tool)
- [ ] **painting** — Gallery (took it but didn't deposit; dropped at Studio)
- [ ] **torch** — Torch Room (on pedestal)
- [ ] **brass bell** — North Temple (deposit only after the LLD ritual; carrying alone scores)
- [ ] **black book** — Altar
- [ ] **pair of candles** — Altar
- [ ] **gold coffin** — Egyptian Room
- [ ] **chalice** — Treasure Room
- [ ] **crystal skull** — Land of the Dead (after LLD ritual)
- [ ] **sceptre** — inside coffin (open it)
- [ ] **jade figurine** — Bat Room
- [ ] **platinum bar** — Loud Room (echo trick)
- [ ] **huge diamond** — pressed from coal in machine
- [ ] **sapphire-encrusted bracelet** — Gas Room
- [ ] **leather bag of coins** — Maze (one specific room)
- [ ] **trunk of jewels** — Reservoir (after draining)
- [ ] **crystal trident** — Atlantis Room
- [ ] **large emerald** — inside red buoy
- [x] **pot of gold** — End of Rainbow (took without sceptre — gating bug, see BUGS.md; deposited successfully, +score)
- [ ] **beautiful jeweled scarab** — Sandy Cave (after digging)
- [ ] **beautiful brass bauble** — appears when canary is wound in a forest
