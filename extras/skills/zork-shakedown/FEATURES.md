# Suggested Features for the django-moo `default` Dataset

A comparison of what zork1 offers against what the default bootstrap ships
today. Zork's underlying world model (1980 ZIL) has very different goals than
django-moo's framework, but enough of its mechanics are genre-staples that
they belong in any MUD-flavored core.

This list is sourced from a survey of:

- `django-moo/moo/bootstrap/default/verbs/` (~20 object classes)
- `moo-agent/moo/bootstrap/zork1/verbs/` (substrate + 130+ rooms)

Each suggestion notes the relevant zork1 source paths so a future
implementer can study the prior art before writing anything new. None of
these proposals require porting zork1-specific code: the goal is a generic
version of the *mechanic*, not the *implementation*.

## A note on scope

The default dataset is intentionally a framework, not a game. Combat,
score, and hunger don't belong baked into `root_class`. The right shape
for almost every item below is an **opt-in object class** in
`moo/bootstrap/default/verbs/` (alongside `flashlight`, `lock_utils`,
`container`, etc.), plus a small documented hook in `room`/`player` if
needed. A builder who wants a Zork-style game subclasses; a builder who
wants a chat MUD ignores it.

---

## Tier 1 — Foundational gaps that affect every MUD

✅ # 1. Scheduled events / daemons / heartbeat

**Gap:** the default dataset has no way to schedule recurring or delayed
work. `enterfunc` and `confunc` fire on player action; nothing fires on
its own. Every dynamic MUD needs this.

**Zork prior art:** `zork_thing/daemons/` ships ~15 distinct daemons
(`i_fight`, `i_thief`, `i_lantern`, `i_candles`, `i_rfill`, `i_rempty`,
`i_river`, `i_cyclops`, `i_forest_room`, `i_cure`, `i_match`,
`i_sword`, etc.). They are driven by a per-player queue stored on the
player's zstate; the main loop pops and re-queues.

**Proposed shape for default:**

- A `daemon` object class with `interval` (ticks), `next_fire` (timestamp),
  and an `on_tick()` verb the runtime invokes.
- A `system.tick` Celery beat task that walks active daemons and dispatches.
- Helper verbs on `wizard`: `@daemon list`, `@daemon kill <n>`, `@daemon trigger <n>`.
- Per-player vs per-room vs per-object scoping (zork mixes all three).

This is the prerequisite for items 2, 6, and 9 below.

✅ # 2. NPCs with autonomous behavior

**Gap:** default has nothing like an NPC. `player` is for humans only;
there's no base class for an entity that perceives the world and acts on it.

**Zork prior art:** `zork_actor/` (the substrate) plus
`rooms/round_room/thief/`, `rooms/troll_room/troll/`,
`rooms/cyclops_room/cyclops/`, `rooms/bat_room/bat/`,
`rooms/up_a_tree/canary/`, `rooms/forest_1/songbird/`,
and the genuinely-clever `zork1/daemons/i_thief.py` (deterministic
beeline-to-treasure replacement of the original random walk).

**Proposed shape:**

- An `npc` class inheriting from `player` (or a sibling under `root_class`)
  that supports `tell()` without a real connection.
- A `personality` daemon hook: `npc.act()` runs on tick, receives the room
  state, and decides whether to move, speak, attack, or idle.
- Stock subclasses: `wanderer` (random walk between marked rooms),
  `shopkeeper` (sits in one room, responds to `buy`/`sell`),
  `guard` (blocks an exit until a condition is met).

### 3. Death, unconsciousness, and reset

**Gap:** there is no notion of a player being incapacitated. `@quit` is
the only exit; rejoining puts you back where you were.

**Zork prior art:** `_.jigs_up(msg)` (in `zork_thing/helpers/`) is the
canonical death path. It prints the message, presents restart / restore
/ quit / score, and resets the player. `UNCONSCIOUS` is a separate flag
on the player's zstate that blocks actions for a number of turns.

**Proposed shape:**

- A `die(message)` verb on `player` that:
  - Sends the player to their `home_location` (or a configurable morgue).
  - Drops carried items at the death site.
  - Resets a `dead` flag after N seconds (or on `revive`).
- A wizard `@revive <player>` and `@kill <player>` for testing.
- A `dead` property gate in do_command so dead
  players see "You can't, you're dead." rather than a normal response.

---

## Tier 2 — Genre support: items every adventure-style MUD wants

### 4. Score, points, and treasures

**Gap:** no score system at all.

**Zork prior art:** `zork_thing/score/`:

- `score_obj(obj)` adds `obj.value` to player score, then zeros `value`
  so a treasure can't be re-scored by drop-and-pickup.
- `score_upd(delta)` for arbitrary point awards (puzzle solutions).
- `tvalue` (treasure-display value at game end) separate from `value`
  (pickup points).
- `finish()` shows the score breakdown and offers restart.

**Proposed shape:**

- A `score` property on `player` (integer, default 0).
- A `treasure` mixin or property on objects: `pickup_value` and
  `deposit_value`.
- Score adjusts on `take` if `pickup_value > 0` (then zeros it).
- A `@score` verb that lists ranks ("Beginner", "Junior Adventurer",
  "Master", etc. — Zork uses a tiered system).
- Optional: a "deposit room" pattern where treasures need to be
  delivered to score, not just picked up.

### 5. Combat

**Gap:** no combat mechanics. There's no HP, no weapons, no attack verb.

**Zork prior art:** `zork_thing/combat/`:

- `villain_blow()` — single-round attacker swings at defender.
- `hero_blow()` — player swings back; weapon strength + roll vs target.
- `fight_strength()`, `villain_strength()` — both sides track
  consumable HP (strength decrements on hit).
- `find_weapon()` — picks the strongest weapon in inventory.
- The combat resolution is a 1d100 roll vs strength delta. Outcomes
  include miss, hit, stagger, unconscious, kill — zork has a small
  table of flavor messages for each.

**Proposed shape:**

- A `combatant` mixin (HP, attack, defense properties).
- `attack <target> [with <weapon>]` verb.
- A combat-round daemon (item 1) so multi-turn fights play out.
- Configurable damage tables.
- Hooks for NPCs (item 2) to fight back.

### 6. Consumable light sources

**Gap:** default has `flashlight` as a binary on/off switch. No fuel,
no warning, no decay. `match_utils` exists but is just for string
matching — there is no real "burns out in 30 seconds" light.

**Zork prior art:** three different decay models in
`zork_thing/daemons/`:

- `i_lantern` — slow burn (hundreds of turns), warnings at thresholds,
  then dark.
- `i_candles` — discrete tick decay with a final flicker.
- `i_match` — single-shot; lights for ~2 turns then gone.

**Proposed shape:**

- Extend `flashlight` (or add `consumable_light`) with `fuel`,
  `max_fuel`, `consume_per_tick`.
- Bind a daemon (item 1) to tick fuel down when lit.
- A `recharge`/`refuel` verb (matches, batteries) that consumes a
  source object.
- Warning messages at 25%, 10%, 1 turn left.

### 7. Pseudo-objects (examinable scenery)

**Gap:** the default lets a builder mark an object `@nonobvious`, but
there's no clean pattern for "the chasm you can look at but not pick
up." Builders end up creating a real Object with `@lock` to deny take.

**Zork prior art:** `zork_thing/pseudo_objects/` and per-room
implementations:
`chasm_pseudo`, `door_pseudo`, `gate_pseudo`, `dome_pseudo`,
`lake_pseudo`, `stream_pseudo`, `chain_pseudo`, `nails_pseudo`,
`paint_pseudo`, `gas_pseudo`. Each is a per-room stub that prints
flavor on `look`/`examine` and a curt refusal on `take`/`push`/`use`.

**Proposed shape:**

- A `scenery` object class that:
  - Lives in a room's `pseudo_objects` collection (separate from
    `contents`), so it doesn't show in the obvious-listing or count
    against `accept()`.
  - Implements default-refusal verbs (`take`, `push`, `drop`) with
    customizable messages.
  - Resolves through the room's `match_object` so `look chasm` works.
- Builder verbs: `@scenery <name> on <room>`, `@scenery describe`,
  `@scenery reply <verb> "<message>"`.

### 8. Containers with capacity and weight

**Gap:** default's `container` tracks open/closed and opacity but has
no capacity limit, no weight, and no carrying-cap on the player.
Players can carry infinity.

**Zork prior art:** zork uses `OSIZE` (object size), `CSIZE`
(container size), and player capacity (`STRENGTH`). `itake.py` and
`itake_2.py` enforce both inventory weight and container-fit on every
pickup.

**Proposed shape:**

- `size` and `capacity` properties on `thing` and `container`.
- `accept()` (already a verb) extended to check size against
  `remaining_capacity`.
- A configurable inventory cap on `player`.
- A `@weigh` or extended `inventory` verb that shows used/total.
- Allow some games to opt out by leaving capacity at -1 (current behavior).

---

## Tier 3 — Useful object/world primitives

### 9. Liquid handling (fill, empty, pour, drink)

**Gap:** no built-in liquid model. `bottle` doesn't exist as a class.

**Zork prior art:** `rooms/kitchen/bottle/`, `rooms/kitchen/water/`,
`rooms/reservoir/`, `rooms/reservoir_south/global_water/`,
`rooms/maintenance_room/leak/`, `rooms/maintenance_room/putty/`,
plus the river/reservoir daemons.

The pattern: a `bottle` is a container that accepts only liquids, with
verbs `fill from <source>`, `empty`, `pour <liquid> on/in <target>`,
`drink <liquid>`. Liquids are objects with a `liquid` flag; sources
emit a fresh liquid object on `fill`. Putty/leak is a special-case
"liquid → solid" transition.

**Proposed shape:**

- A `liquid_container` class (bottles, jars, glasses).
- A `liquid` class with `name`, `taste`, `drinkable`, `quantity`.
- A `liquid_source` class (faucet, river, well) that issues liquids
  on `fill`.
- Verbs: `fill <container> from <source>`, `pour <container> [on/in
  <target>]`, `drink <liquid>`, `empty <container>`.

### 10. Multi-room vehicles

**Gap:** no vehicle concept. A player can't "be inside a thing that
moves through rooms."

**Zork prior art:** `inflated_boat/` (the magic boat). The boat is
both a container (the player goes inside) and a moveable Object
(its location is a room). The `i_river` daemon walks it downstream
through a sequence of rooms; the player's `look` returns the boat's
location's description; movement verbs while aboard either operate
the boat or are refused.

There's also the canonical Zork hack of `punctured_boat/` — the boat
swaps class when ruptured, losing its float behavior. That's a clever
generic pattern: object class as state.

**Proposed shape:**

- A `vehicle` class (extends `container`). Has a `location` that's a
  room; players inside see `vehicle.location.look` not `vehicle.look`.
- Verbs: `board <vehicle>`, `disembark`, `pilot <direction>` (or use
  movement verbs while aboard).
- Optional: passenger limits, fuel, navigability per terrain.
- The "swap class on event" pattern itself is generally useful and
  could be a documented `@morph` builder verb.

### 11. Push/turn/press for switches and buttons

**Gap:** no canonical "press" or "turn" verb. Builders adapt
something else.

**Zork prior art:** `rooms/maintenance_room/blue_button/`,
`brown_button/`, `red_button/`, `yellow_button/`. Each is a simple
press-triggers-side-effect object. The flat collection of buttons in
one room is a memorable puzzle.

**Proposed shape:**

- A `switch` class with `state` (on/off) and verbs `push`, `press`,
  `turn`, `toggle`.
- An `on_change` hook (verb on the switch) that's invoked when state
  flips — so builders write the side effect without writing the verb.

### 12. Pronoun resolution ("it", "her", "them")

**Gap:** default has gendered substitution (`pronoun_sub` in
`string_utils`) for output, but no input-side resolution. Players
can't say `take it` after `look sword`.

**Zork prior art:** `zork_thing/parser/this_is_it.py` — every verb
that resolves an object as its dobj writes the object onto the player's
zstate as `P-IT-OBJECT`. The parser checks that slot when it sees
the word `it`.

**Proposed shape:**

- A `last_dobj` (and `last_iobj`) property on `player`, updated by
  the parser after every successful resolution.
- Parser recognizes `it`, `him`, `her`, `them` and substitutes from
  the appropriate slot.
- Gendered slots (`him`/`her`) check the referent's `gender`.
- Timeout: if the last dobj has been deleted or moved out of reach,
  fall through to normal disambiguation.

---

## Tier 4 — Polish and convenience

### 13. Command history and replay

**Zork prior art:** `zork_actor/dispatchers/#.py` —
`#command`, `#record`, `#unrecord`, `#random` particle verbs let
players replay or randomize input. Useful for test scaffolding.

**Proposed shape:** an opt-in `@history`, `@!! <n>` (replay nth-back
command), `@record start/stop` for test capture.

### 14. Game-state save/restore

**Zork prior art:** the canonical `save`/`restore` verbs. In zork
these write all object locations and flags to a file. In a persistent
MUD this is less critical, but a per-player "checkpoint" (for tutorial
or puzzle worlds) is genuinely useful.

**Proposed shape:** `@checkpoint <name>` and `@restore <name>` that
serialize and rehydrate the player's location, inventory, and
relevant flags. Wizard-only or quota-limited.

### 15. Room and exit visibility predicates

**Zork prior art:** `zork_thing/predicates/` includes `is_lit`,
`is_open`, `is_takeable`, `is_visible`, `is_holdable`,
`is_described`, etc. The default has a couple of these scattered
on object classes; consolidating into a predicates module would make
verb authoring cleaner.

**Proposed shape:** a `predicates` SDK module in `moo.sdk`
exposing `is_lit(obj)`, `is_visible(obj, observer)`, etc., so a
verb author doesn't reinvent each check.

---

## What NOT to port

A few zork things are too game-specific to belong in the default:

- **Grue** — zork's "you have been eaten" is a flavor implementation
  of the dark-room hazard. The generic version is just: dark room
  with no light source → player takes damage / dies (item 3 + item 6).
- **Specific monsters** — thief, troll, cyclops, bat are excellent
  examples of NPC patterns (item 2) but shouldn't ship as concrete
  classes.
- **Specific puzzles** — egg/canary, bell/book/candle, coal/diamond
  machine are zork content. They illustrate the substrate but
  don't generalize.
- **Maze rooms** — a single instance of the maze pattern is great in a
  game; the framework doesn't need a maze primitive.

---

## Suggested implementation order

If someone wanted to take all of this on:

1. **Daemons (item 1)** — unblocks 5 of the other items.
2. **Death (item 3)** — small change, immediate gameplay value, prereq
   for combat.
3. **NPC base class (item 2)** — paired with daemons, enables most
   adventure content.
4. **Score (item 4)** — small, satisfying, makes simple puzzle worlds
   possible.
5. **Pseudo-objects / scenery (item 7)** — small change, big
   reduction in builder friction.
6. **Capacity (item 8)** — gameplay constraint that opens up puzzle
   design.
7. **Combat (item 5)** + **light decay (item 6)** — these need
   daemons.
8. **Switches (item 11)** — trivial once the rest exists.
9. **Pronouns (item 12)** — touches the parser; needs care.
10. **Liquids (item 9)** and **vehicles (item 10)** — biggest scope,
    do last.
