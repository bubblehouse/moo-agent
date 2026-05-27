# Completed Work

Index of fixes that survived the moo-core rollback. Before logging a bug in
[BUGS.md](../BUGS.md), grep here — if the behavior is listed, it works (or has
a documented hand-written override) and shouldn't be re-reported.

All fixes live in `moo/zil_import/` (Rule Zero). Two approved moo-core
exceptions documented at the bottom.

## Smoke milestones

| Date | Pass / Total | Score | Rank | Notes |
| --- | --- | --- | --- | --- |
| 2026-05-20 | 393 / 397 | 284 / 350 | Adventurer | 3 shakedown bugs fixed (tree-drop / climb particle / teleport render); smoke byte-identical to the pre-change baseline — 0 regressions. Remaining 4 fails (take painting load-too-heavy, take trident/skull thief-stolen, score) are pre-existing. |
| 2026-05-19 | 397 / ~400 | ~294 / 350 | Adventurer | thief-cycle randomness causes 10-30pt swings per run |
| 2026-05-18 | 365 / 371 | 330 / 350 | Master | round-4 (post invisible-clear + throw-rewrite) |
| 2026-05-10 | 363 / 363 | 350 / 350 | Master Adventurer | end-to-end run via the teleport sentinel + reset-seeded values |
| 2026-05-06 | 358 / 358 | 254 / 350 | Adventurer | turnfunc parser fallback fix |
| 2026-05-06 baseline | 108 / 350 | — | — | pre-rollback |

The 350 ceiling depends on:

- `__teleport_to_living_room__` sentinel in `zork1_smoke.py` (Sandy Beach has no overland return)
- pre-seeded `MAGIC-FLAG` / `CYCLOPS-FLAG` shortcuts in `_reset_state_body.py`
- thief NOT looting the visited rooms before player gets there (probabilistic)

## Player commands that work / known message

Listed alphabetically. File pointer is the verb file or rewrite location.

### Inventory & containers

- `take <obj>` — substrate, clears `invisible` flag post-itake (`verbs/zork_thing/substrate_verbs/take.py`)
- `take all` — gathers room contents only; does NOT recurse into takeable containers (`verbs/system/take_helpers.py`)
- `take all but X` — alias-aware exclusion (`verbs/system/dispatch_multi.py`)
- `take all from CONTAINER` — peeks into nested open containers (`verbs/system/dispatch_multi.py`)
- `drop me` — "You'd lose your balance." (`verbs/zork_thing/substrate_pre/pre_drop.py`)
- `put X in Y` — three-tier rejection ladder (no Y / closed / non-container); peeks nested (`verbs/zork_thing/substrate_verbs/put.py`)
- `give X to <actor>` / `feed <actor> X` — V-GIVE vs V-SGIVE form-aware swap (`verbs/zork_thing/substrate_pre/pre_sgive.py`)
- `give X to me` — "You can't give something to yourself." (no recursion)
- `feed <actor>` (no item) — "Give what to whom?"
- `examine <obj>` — descriptive line first, contents view only if open+non-empty (`verbs/zork_thing/substrate_verbs/examine.py`)
- `examine me` — "There's nothing special about yourself." (no username leak)
- `look in <obj>` — uses "the" (no article-agreement issue with mass nouns) (`verbs/zork_thing/substrate_verbs/look_inside.py`)
- `look at/in/under/behind/on X` — rewritten at do_command layer (`verbs/system/do_command.py`)

### Movement & vehicles

- bare directions (`n`, `north`, `up`, etc.) — walk dispatcher includes them (`verbs/zork_actor/dispatchers/walk.py`)
- `walk <dir>` / `go <dir>` — same dispatcher
- `climb <thing>` — checks dobj in-scope; topical refusal when absent (`verbs/zork_actor/dispatchers/climb.py`)
- `climb up <obj>` / `climb down <obj>` — dispatcher peels the leading `up`/`down` particle and walks that direction (canonical `CLIMB UP/DOWN OBJECT`; the parser folds the particle into the dobj string) (`verbs/zork_actor/dispatchers/climb.py`)
- `climb tree` at Forest Path — walks to Up-A-Tree
- `<GOTO>` teleports describe the destination — `_.goto` (`verbs/system/movement.py`) updates HERE/LIT and runs V-FIRST-LOOK after relocating, so `pray`, mirror-rub, i-river drift and jigs_up respawn render the room they land on instead of a silent screen
- Up a Tree: dropping an object relocates it to the path below with a single "falls to the ground" line — the TREE-ROOM M-BEG drop branch returns True so substrate V-DROP doesn't double-fire "You're not carrying it"
- bare `up` in non-climbable forest rooms — "You can't go that way." (was tree message; reset patches the exit msg)
- `disembark` (bare) — auto-targets vehicle (`verbs/system/do_command.py`)
- boat ashore from non-water source — "You can't bring the magic boat ashore." (`verbs/zork_exit/move.py`)
- River 1-5 → Sandy Beach drift — boat passes (source nonlandbit allows)
- `enter <door>` — falls through to canonical "hit your head" when no exit references it (`verbs/zork_thing/helpers/other_side.py`)
- exit traversal fires `enterfunc` + `score_obj` on dest (`verbs/zork_exit/move.py`)

### Bare-verb prompts (do_command guard)

`take`, `get`, `grab`, `open`, `close`, `shut`, `examine`, `x`, `describe`,
`give`, `donate`, `offer`, `feed`, `throw`, `hurl`, `toss`, `eat`, `drink`,
`wear`, `read`, `attack`, `kill`, `break`, `drop`, `pour`, `spill`,
`give to <iobj>` — all print canonical "What do you want to X?" / "Give what
to whom?" instead of "I don't know how to do that." (`verbs/system/do_command.py`)

### Combat

- `attack <npc> with <weapon>` — HERO-BLOW resolves on each turn (stagger/miss/hit/wound/kill)
- `attack me with sword` — "If you insist.... Poof, you're dead!" → respawn at West of House
- `throw <weapon> at <actor>` — rewritten to `attack <actor> with <weapon>` (`verbs/system/do_command.py`)
- death sequence — `system_object.player_start` seeded; jigs_up teleports to West of House (`verbs/system/death.py`, reset)

### Parser shims

- Trailing `.?!` stripped from verb word (`look.`, `inventory!`, bare `.`) — `verbs/system/do_command.py`
- `turn off X` / `turn X off` → `extinguish X` rewrite — same
- `turn on X` / `turn X on` → `light X` rewrite — same
- Pronoun `it` / `him` / `her` tracks last dobj (`verbs/system/resolve_pronoun.py`)
- Bare-adjective dobj resolution (`push yellow` → yellow button) (`verbs/system/resolve_dobj_late.py`)
- Scenery + open-container dobj peek (`verbs/system/resolve_dobj_late.py`)
- `examine self` / `examine myself` → `context.player` — same
- `again` / `g` — restores snapshotted parser state (`verbs/system/do_command.py`)

### Misc verbs with hand-written replacements

- `dig <obj>` (no tool) — "Digging with your bare hands ..." (`verbs/zork_thing/substrate_verbs/dig.py`)
- `fill <bottle>` (bare or with water) — uses `water_source` / `global_objects`, no Z-machine table walk (`verbs/zork_thing/substrate_pre/pre_fill.py`)
- `drink water` — depletes bottle inventory (`verbs/zork_thing/helpers/hit_spot.py`)
- `version` — single-print banner, no per-digit newlines (`verbs/zork_actor/version.py`)
- `diagnose` — drops C-TABLE contribution, no crash (`verbs/zork_actor/diagnose.py`)
- `listen` / `smell` (bare) — canonical inert response (`verbs/zork_actor/listen.py`, `smell.py`)
- `echo` — Loud Room flips LOUD-FLAG; elsewhere "echo echo..." (`verbs/zork1/echo.py`)
- `sing` / `dance` / `jump` — canonical inert responses (`verbs/zork_actor/`)
- `yell` — `--dspec none`
- `sit` — "Quaint, but unproductive."

## Substrate / system verbs (key contracts)

### `verbs/system/do_command.py` — System Object pre-dispatch hook

Runs before parser dispatch. Sequenced:

1. `again` / `g` rehydration
2. Punctuation strip + bare-verb prompt table
3. Throw-at / turn-off / look-prep rewrites
4. `zil_init` (GO routine) on first command of session
5. `_.tick()` for per-turn daemons
6. preturnfunc / M-BEG dispatch
7. `_.resolve_pronoun` + `_.resolve_dobj_late`
8. Last-command snapshot
9. `_.dispatch_multi` (take/drop all)

### `verbs/system/movement.py` — `walk`, `goto`, `perform`, `remove`, `next_sibling`

`perform` invokes the target verb WITHOUT positional args (god-verbs read
`mode = args[0]` — passing prso/prsi would shadow it and recurse via
passthrough). Parser dobj/iobj are set before the call.

### `verbs/zork_exit/move.py` — exit traversal

- Reads `condition_flag` (FALSE-FLAG / zstate / object.open)
- Reads `dest` or `exit_routine` (snake-cased lookup)
- Gates water vehicles by terrain (source AND dest both non-nonlandbit → block)
- Vehicles relocate via `current_vehicle()`; player otherwise
- Fires `dest.enterfunc()` + `_.zork_thing.score_obj(dest)`
- Falls back to `_.zork_thing.look` for first-entry description

### `verbs/zork_thing/substrate_pre/pre_sgive.py` — V-SGIVE dispatch

Detects V-GIVE form (`to` preposition) vs V-SGIVE form (feed-style). Invokes
recipient's `give` verb directly (no `_.perform`, no actor-dispatcher
recursion). Self-give → "You can't give something to yourself."

### `verbs/zork_thing/output/{describe_object,describe_room,print_contents}.py`

- NDESCBIT and INVISIBLE are separate flags (not both → `obvious=False`)
- Article `"A "` / `"An "` based on first letter
- Custom M-LOOK rooms get exactly one banner + describe pass
- `print_contents` returns a string (caller composes the final `print(...)`)

### `verbs/zork_root/output.py` — `desc` strips atom suffix

`Forest (FOREST-2)` reads as `Forest` to the player; verb-load lookups still
see the disambiguated name.

### `verbs/zork_thing/daemons/i_thief.py` — hand-rolled thief AI

- Deterministic beeline to Treasure Room when loot in bag
- Cached `outdoor non-sacred` PK cycle on System Object (avoids ~220 verb
  dispatches per realtime tick — was timing out 15s celery hard limit)
- `rob` / `steal_junk` fires on touchbit'd rooms thief visits
- Note: Atlantis Room and Maintenance Room are flagged `outdoor=True`, so
  the thief WILL visit and rob them. Affects trident / wrench score floor.

## `_reset_state_body.py` covers

Every `--sync` re-applies. Notable items beyond bootstrap defaults:

- Adventurer Player avatar wired (was Wizard)
- `system_object.player_start = West of House` (death respawn)
- Object placements: leaflet, rope, sword, lantern, broken_lamp, egg, nest,
  painting, torch, bell, book, candles, matchbook, guidebook, coffin, canary,
  sceptre, chalice, sandwich_bag, garlic, lunch, jade, platinum_bar, diamond,
  coal, screwdriver, bracelet, kitchen_window, forest_tree, mirror_1, mirror_2,
  inflated_boat, buoy, emerald, shovel, scarab, pot_of_gold, trident,
  bag_of_coins, trunk, wrench, tube, owners_manual, broken_timber
- Thief-empty sweep: after the thief is re-parked, every item it carries
  except the stiletto + large bag is sent to limbo (and the large bag's
  contents too), so ROB / STEAL-JUNK loot can't accumulate across sessions
- Treasure invisible-clear: 24 names including thief-junk (matchbook, wrench,
  screwdriver, tour-guidebook)
- Property resets: `egg.open=True`, `mailbox.open=False`, `trap.open=False`,
  `case.open=False`, `coffin.open=False`, `buoy.open=False`,
  `machine.open=False`, `bar.sacred=True`
- zstate resets: `loud_flag=False`, `match_count=6`, `lld_flag/xb/xc=False`,
  `sing_song=False`, `cage_top=True`, `rug_moved=False`, `score=0`,
  `base_score=0`, `won_flag=False`, `magic_flag=True`, `cyclops_flag=True`,
  `light_shaft=13`, `dome_flag=False`, `lit=True`, `queue=[]`, `drop=[]`,
  `moves=0`, `started=False`, `always_lit=True`, `water_level=0`,
  `mirror_mung=False`, `beach_dig=0`, `rainbow_flag=False`,
  `gate_flag/gates_open/low_tide=None`, `deaths=0`
- Re-seeded room VALUE: Kitchen=10, Cellar=25, Treasure Room=25, EW-Passage=5
- Re-seeded treasure VALUE per `_v_map` (canonical ZIL)
- NPC strength: cyclops=10000, thief=5, troll=2, player=0
- Mine in/west exit dest → Squeaky Room
- Forest UP exit nogo_msg → "You can't go that way." (was tree-specific)
- Villain restoration (troll/thief/cyclops + axe/knife/stiletto re-placement,
  combat counters zeroed)
- ACL: `everyone:write` on every Property of every Zork-classed instance
- Player records on site: re-park at West of House, clear won_flag

## Translator / generator key behaviors

These were once bugs and are now stable. If you see something matching, it's
the established behavior — don't re-derive.

- `--dspec this` / `--dspec either` / `--dspec any` emitted per V-routine
  shape (substrate / Zork Actor / 0-OBJECT)
- Action-handler bodies end with `return passthrough()` unless already
  unconditional return
- `RFALSE` inside action-owner verb-clause → `return passthrough()`
- `the_player_verb` bound from `parser.words[0]` (not `verb_name`) — sub-call
  scenarios work
- `pre_x = "pre_<verb>"` (snake-case) — old `pre-X` was a silent no-op
- PRSO/PRSI hoisted as `prso`/`prsi` locals at top of routine with
  NoSuchObjectError-safe try/except
- PRE-* routines auto-return `True` when their missing-dobj guard fires
- Per-OBJECT action-owner clauses get `--dspec this`; per-ROOM stay `--dspec either`
- Sequential COND clauses sharing verb atoms only emit the first one
  (egg/open BAD-EGG fix — `_emit_verb_clauses` drops dupes)
- M-BEG handlers return True from matched clauses; M-END exempt (RFALSE-chain).
  The injection (`_inject_return_true_into_branches`) recurses into the *tail*
  if/elif/else chain of each branch so nested COND clauses (e.g. TREE-ROOM's
  `<VERB? DROP>` body, itself a COND over PRSO) each return True. A nested
  chain that is followed by more statements is left alone — control still
  flows past it (sentence-fragment `if`s and setup guards keep working).
- `<VERB?>` checks emit `the_player_verb in [...]`
- `V?<NAME>` atom → snake-case string literal (`"disembark"` etc.)
- Arithmetic / AND / OR results parenthesized (precedence-safe)
- `<REST tbl N>` → `_.rest(tbl, N)` (byte-offset slicing)
- `<GET 0 N>` → `_.get_property("zstate_version_table")[N]` (header table)
- F-clause splitting parallel to M-clause (F-DEAD, F-UNCONSCIOUS, etc.)
- Generator `handwritten_paths` blocks auto-emit when template-tree provides
  the file (CLIMB_OVERRIDES path also honors this; WALK_OVERRIDES / PUT_OVERRIDES
  may still need it)
- `_ROUTINE_TO_VERBS` primary-arity only; V-{verb} canonical wins for shared
  bare names
- `ZIL_VERBS` post-merge unions synonym aliases into substrate shebangs
- Display-name dedup: `Forest (FOREST-1)`, `Mirror Room (MIRROR-1)` etc.
- Action-routine names alias the room (LLD-ROOM → ENTRANCE-TO-HADES)
- `set_flag("invisible", X)` writes through to `obvious = not X`
- Zork Actor inherits from Zork Thing (was Zork Root — broke passthrough())

## Daemon scheduling

- Recurring daemons require explicit `_.cancel(name)` / `_.unschedule_realtime(name)`
- GO routine fired via `_.zork_thing.zil_init()` on first command of session
  (per-player `zstate_started` gate)
- Queued daemons: `i-fight`, `i-sword`, `i-thief` (realtime), `i-candles`,
  `i-lantern`, `i-bat` (Bat Room enterfunc), `i-forest-room` (forest enterfunc),
  `i-river` (self-queues on water rooms), `i-maint-room` (blue button)
- Queue tick snake-cases daemon names before lookup
- `_reset_state_body.py` clears `zstate_queue`/`drop`/`moves`/`started`
- Recurring daemon PTs carry `expire_seconds = max(delay * 3, 10)` (set in
  `verbs/system/scheduler.py`).  celery-beat enqueues one tick per interval
  unconditionally; without an expiry, any tick that runs slower than its
  interval lets the broker queue grow without bound (a 47,188-deep backlog
  was observed, starving every interactive command).  `expire_seconds` makes
  Celery discard a tick that has sat in the queue too long — a stale realtime
  tick is pointless anyway — capping the per-daemon backlog at ~10 tasks.

## Smoke-test infrastructure

- `moo/zil_import/scripts/zork1_smoke.py` — full canonical run
- `moo/zil_import/scripts/zork1_spot.py` — arbitrary command sequence
  (`--reset` to start from canonical opening state)
- `moo/zil_import/scripts/zork1_reset.py` — CLI wrapper around the reset
- `moo/zil_import/scripts/zork1_save_state.py` — JSON snapshot of world
- `MooSSH.run(prefix_wait=2.0)` short-circuits on missing PREFIX; cuts ~8s
  per no-output verb (pray / light match / launch)
- `MooSSH.run()` drains the channel of buffered async output before sending
  each command — ambient room daemons (forest songbird chirp) emit `tell()`s
  between commands; left in the pipe they desync the PREFIX/SUFFIX window and
  shift every later response by one (the mangled `>>> �` marker)
- `zork_session.py start --reset` stops the `django-moo-celery-1` container
  for the duration of `moo_init --sync`, then restarts it.  moo_init wraps the
  whole bootstrap in one `transaction.atomic()`; a live Celery daemon tick
  contending on the same rows deadlocks Postgres and silently rolls the entire
  reset back (stale deaths/score/inventory, wrench stuck in the thief)
- `[no-suffix]` tag excludes empty-output verbs from "slowest" timing

## `_SKIP_ROUTINES` (auto-emit suppressed)

Each has a hand-written replacement or is unreachable in DjangoMOO:

- Parser core: `CLOCKER`, `MAIN-LOOP`, `MAIN-LOOP-1`, `PARSER`, `YES?`,
  `NUMBER?`, `CLAUSE*`, `SYNTAX-*`, `UNKNOWN-WORD`, `ORPHAN*`, `CANT-*`,
  `WHICH-PRINT`, `THING-PRINT`, `WORD-PRINT`, `BUFFER-PRINT`,
  `NOT-HERE-PRINT`, `NOT-HERE-OBJECT-F`, `SNARF*`, `GET-OBJECT`,
  `MANY-CHECK`, `ITAKE-CHECK`, `GLOBAL-CHECK`, `GWIM`, `BUT-MERGE`,
  `THIS-IT?`, `GLOBAL-IN?`, `INBUF-ADD`
- Movement: `V-WALK`, `DO-WALK`, `V-CLIMB-UP`, `V-CLIMB-DOWN`,
  `V-CLIMB-ON`, `V-CLIMB-FOO`, `V-LEAP`
- Lit: `LIT?`, `DO-SL`, `SEARCH-LIST`, `OBJ-FOUND`
- P-LEXV: `V-SAY`, `V-ECHO`, `V-INCANT`
- Hand-written replacements: `GO-NEXT`, `I-THIEF`, `V-VERSION`, `V-GIVE`,
  `HIT-SPOT`, `PRE-DROP`, `V-ATTACK`, `V-DIAGNOSE`, `HELD?`

## Z-machine leakage allowlist

`moo/zil_import/tests/test_no_zmachine_leakage.py` `_KNOWN_PRIMITIVE_LEAKS`:

- `zork_thing/daemons/i_sword.py` — getpt/ptsize live leak (P?EXIT walk)
- `system/dispatch.py` — primitives only in documentation comment
- `zork_thing/helpers/other_side.py` — primitives only in docstring
- `zork_thing/substrate_pre/pre_fill.py` — primitives only in docstring

## Rule Zero exceptions (approved moo-core changes)

The user has approved exactly **two** moo-core changes since the rollback.
Anything beyond these requires a fresh conversation.

### 1. `Parser.get_pronoun_object` location-name fallback ([moo/core/parse.py](moo/core/parse.py))

Extends pronoun resolution so the caller's location's name/aliases resolve as
a pronoun (so e.g. `disembark boat` finds the boat the player is inside).
Generic, not ZIL-specific.

### 2. 2026-05-17 five-fix PR ([moo/core/parse.py](moo/core/parse.py), [moo/core/code.py](moo/core/code.py), [moo/sdk/](moo/sdk/))

- **Case-insensitive verb dispatch** — `_batch_get_verb` uses
  `names__name__iexact`. `LOOK`, `Inventory`, `EAT` all dispatch correctly.
- **`invoked_verb_name(default)` helper** in `moo.sdk` — collapses the
  recurring `parser.words[0].lower() if context.parser is not None and parser.words else verb_name`.
- **Period/comma compound-command splitter** — `_split_command_fragments()`
  splits the line before lexing. Conservative: only `.`/`,` + whitespace +
  alpha; never inside quotes or brackets. `n,n,e` (no spaces) is the
  deferred sacrifice.
- **Print collector buffering** — `_print_` is a per-verb singleton;
  `print("a", end=""); print("b")` coalesces into one writer call `"ab"`.
- **Dead-object error classification** — `get_verb()` distinguishes "verb
  name unknown" from "verb name exists but dobj didn't resolve" via a
  `Verb.objects.filter(names__name__iexact=...).exists()` check; raises
  `NoSuchObjectError(dobj_str)` for the latter.

The article-stripping half of case-insensitive dispatch (preposition retry)
remains in [TODO.md](../TODO.md). Cardinal shorthand `n,n,e` also deferred.
