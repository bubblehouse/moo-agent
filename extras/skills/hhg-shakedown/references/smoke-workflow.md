# Smoke Workflow

The development loop for ZIL importer fixes. Memorise this rhythm — every fix follows it.

## Prerequisites

- Docker stack running: `docker-compose up -d` from the repo root.
- `hhg.local` site initialised: `docker exec django-moo-shell-1 sh -c '/usr/app/bin/python /usr/app/src/manage.py moo_init --bootstrap hhg --hostname hhg.local'` (run once after first checkout; subsequent runs use `--sync`).
- ZIL source available at `/Users/philchristensen/Workspace/hitchhikersguide/s4.zil` (or wherever your local mirror lives).
- `phil` user exists with a Player record on `hhg.local` whose avatar points at the Wizard. Fixed by:

```bash
docker exec django-moo-shell-1 sh -c '/usr/app/bin/python /usr/app/src/manage.py shell -c "
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from moo.core.models.auth import Player
from moo.core.models.object import Object
phil = User.objects.get(username=\"phil\")
hhg = Site.objects.get(domain=\"hhg.local\")
wiz = Object.global_objects.get(name=\"Wizard\", site=hhg)
p, _ = Player.objects.get_or_create(user=phil, site=hhg, defaults=dict(avatar=wiz, wizard=True))
p.avatar = wiz; p.wizard = True; p.save()
"'
```

## Inner loop (per-fix)

```bash
# 1. Edit something in moo/zil_import/
$EDITOR moo/zil_import/translator.py

# 2. Regen the bootstrap from ZIL source.  IMPORTANT: --output MUST point
# to moo-agent/moo/bootstrap/hhg, not django-moo/moo/bootstrap/hhg.
# Docker mounts moo-agent's tree (compose.override.yml line 21 mounts
# ../moo-agent/moo:/usr/app/agent/moo:ro) and resolves moo.bootstrap.hhg
# from there via PEP 420 namespace packaging.  Writing to django-moo's
# tree silently does nothing — Python imports the moo-agent copy and your
# regen output is invisible to the running container.
uv run python -m moo.zil_import \
    /Users/philchristensen/Workspace/hitchhikersguide/s4.zil \
    --game-config hhg \
    --output /Users/philchristensen/Workspace/bubblehouse/moo-agent/moo/bootstrap/hhg

# 3. Sync the regenerated bootstrap into the running hhg.local DB
docker exec django-moo-shell-1 sh -c '/usr/app/bin/python /usr/app/src/manage.py moo_init --bootstrap hhg --sync --hostname hhg.local'
# The sync's 099_reset_state.py prints "hhg reset: captured snapshot..." on the
# FIRST sync (clean world) and "restored snapshot..." on every later one.  This
# is how the reset restores object positions — unlike zork1's reset, which
# re-places every object explicitly in code, hhg restores from the captured
# snapshot.  CONSEQUENCE: the snapshot is only as fresh as its capture.  After a
# regen that CHANGES THE WORLD MODEL (adds/removes/relocates rooms or objects —
# the regen banner's "Rooms/Objects" counts move), delete the snapshot so the
# next sync re-captures the new clean world; otherwise the reset restores stale
# positions and silently drops new objects:
#     docker exec django-moo-shell-1 rm -f /usr/app/snapshots/hhg-site-4.json
# Verb-only / flag-only / reset-script changes (this session's edits) DON'T move
# those counts, so the snapshot stays valid — no delete needed.
# If you see "zork1 reset" instead of "hhg reset", you regenerated without
# --game-config hhg (wrong reset body): fix the regen, delete the snapshot, re-sync.

# 4. Spot-test ONLY the commands you care about via the connected harness
# (there is no hhg_spot script — drive the long-lived session instead):
extras/skills/hhg-shakedown/scripts/hhg_session.py start --reset   # Bash run_in_background:true
extras/skills/hhg-shakedown/scripts/hhg_session.py send "look"
extras/skills/hhg-shakedown/scripts/hhg_session.py read --tail 20
extras/skills/hhg-shakedown/scripts/hhg_session.py stop

# 5. Run the full end-to-end smoke (~25-35s) and ALWAYS tee its output.
# Walks Bedroom -> green-button escape -> Dark -> Vogon Hold -> babel fish.
# Does its own reset; prints PASS / FAIL.
uv run python -m moo.zil_import.scripts.hhg_smoke 2>&1 | tee /tmp/hhg_smoke.out
echo "exit=$?"; grep -E "^PASS|^FAIL|did not contain" /tmp/hhg_smoke.out
```

**Always tee the smoke output.** The smoke takes ~70-130s real time. If you only pipe it through `grep`/`tail`/etc. you'll need to re-run it whenever you want to check a different facet of the same run (failure list, per-command timing, score trail, ...).  `tee /tmp/smoke.out` keeps the full transcript so subsequent inspection is a `grep` against the file.

```bash
# Inspect the most recent smoke run without re-running it
grep "did not contain" /tmp/smoke.out | head -20      # failure list
grep -E "^>>> '" /tmp/smoke.out | head -30            # command sequence
grep -B1 -A2 "score" /tmp/smoke.out                   # score history
grep -E "TIMING|slowest" /tmp/smoke.out -A 15         # perf summary
```

## Reading smoke output

The smoke writes per-command output to stdout: `>>> 'cmd' (out len=N)\n<output>`. Failures collect at the end as `cmd did not contain expected; actual: <text>`.

**Cluster failures by output text** to find systemic vs one-off bugs:

```bash
grep "actual:" /tmp/smoke.out | sed -E "s/.*actual: //" | sort | uniq -c | sort -rn | head -10
```

Common clusters:

- `You can't go that way.` — exit not found. May be cascade.
- `I don't know how to do that.` — verb dispatch failed. Either the verb isn't registered, the dobj isn't resolved, or `--dspec` rejects the sentence shape. Check [BUGS.md § "Translation gaps"](../BUGS.md) for known dispatch issues.
- `There is no <X> here.` — dobj not in scope. Usually a cascade.
- `>>> ��` — mangled PREFIX output. Per-clause split dropped the substrate fall-through (now mostly fixed via `passthrough()`).

**To find the FIRST failure** (cascading failures often resolve once you fix the earliest one):

```bash
grep -nE ">>> '" /tmp/smoke.out | head -30
```

Look for the first command whose output doesn't match expected, and trace back from there.

## Spot-test patterns

The spot script (`hhg_spot.py`) takes a list of commands and prints output. Use `--reset` to start from canonical opening state.

```bash
# Test a specific puzzle
uv run python -m moo.zil_import.scripts.hhg_spot --reset \
    "go north" "go east" "go west" "go up" "take rope" "go down"

# Test without reset (continues from current world state)
uv run python -m moo.zil_import.scripts.hhg_spot \
    "look" "inventory"

# Trace a single failing command in detail
uv run python -m moo.zil_import.scripts.hhg_spot --reset \
    "go north" "go east" "go west" "go west" "open trap door"
```

## Live parser introspection

When the smoke says `I don't know how to do that` and you want to know why, drop into the Django shell and trace what the parser sees:

```bash
docker exec django-moo-shell-1 sh -c '/usr/app/bin/python /usr/app/src/manage.py shell -c "
from moo.core.models.object import Object
from moo.core.code import ContextManager
from moo.core.parse import Parser, Lexer
from django.contrib.sites.models import Site
hhg = Site.objects.get(domain=\"hhg.local\")
ContextManager.set_site(hhg)
wiz = Object.global_objects.get(site=hhg, name=\"Wizard\")
lex = Lexer(\"open trap door\")
parser = Parser(lex, wiz)
print(\"dobj_str={!r} dobj={}\".format(parser.dobj_str, parser.dobj))
print(\"search order:\")
for o in parser.get_search_order():
    print(\"  {!r}\".format(o.name))
try:
    v = parser.get_verb()
    print(\"verb={!r} on={!r}\".format(v, parser.this))
except Exception as e:
    print(\"err: {}\".format(e))
"'
```

Useful when debugging:

- `parser.dobj is None` — dobj resolution failed. Check the search order — is the dobj actually accessible from the player's location?
- `parser.dobj is set, parser.this is None` — verb resolution failed. Check `dspec` on candidate verbs and inheritance from dobj.

## Quick sanity queries

After regenerating, verify state in the DB:

```bash
# Count verbs registered for a class
docker exec django-moo-shell-1 sh -c '/usr/app/bin/python /usr/app/src/manage.py shell -c "
from moo.core.models.object import Object
from django.contrib.sites.models import Site
hhg = Site.objects.get(domain=\"hhg.local\")
zt = Object.global_objects.get(site=hhg, name=\"Thing\")
print(\"thing verbs: {}\".format(zt.verbs.count()))
"'

# Check exits on a room
docker exec django-moo-shell-1 sh -c '/usr/app/bin/python /usr/app/src/manage.py shell -c "
from moo.core.models.object import Object
from moo.core.code import ContextManager
from django.contrib.sites.models import Site
hhg = Site.objects.get(domain=\"hhg.local\")
ContextManager.set_site(hhg)
bedroom = Object.global_objects.get(site=hhg, name=\"Bedroom\")
exits = bedroom.get_property(\"exits\") or []
for e in exits:
    aliases = list(e.aliases.values_list(\"alias\", flat=True))
    print(\"  {!r}: {}\".format(e.name, aliases))
"'
```

Note the `ContextManager.set_site(hhg)` call. Without it, `get_property` decodes object refs against the wrong site's `$nothing` and returns an empty list. Inside the running shell server, the site is always set during request handling — this only matters for ad-hoc debugging.

## Test suites

```bash
# Unit tests for the importer (translator + leakage)
uv run pytest moo/zil_import/tests/ -n auto

# Full repo test suite (slow — ~5 min)
uv run pytest moo/ extras/ -n auto -q
```

The leakage test (`moo/zil_import/tests/test_no_zmachine_leakage.py`) catches Z-machine primitives that snuck into generated bootstrap output. If you change verb-tree paths in `generator.py`, update `_KNOWN_PRIMITIVE_LEAKS` to match.

## Commit hygiene

The user does the commits. Don't run `git commit` or `git push` — the memory entry `feedback_no_git_commits` is explicit on this. After each session, leave the working tree clean enough that the user can run `/git:grouped-commit` and get sensible, scoped commits.

## Tracking progress

The HHG smoke is `scripts/hhg_smoke.py` (landed 2026-05-30). It's PASS/FAIL, not a score
count: it walks the full canonical path and asserts a substring at each beat, so any
regression in the Bedroom → green-button escape → Dark → Vogon Hold → babel-fish chain
turns it red. Headline metrics:

- Translator pass: HHG ZIL → `moo/bootstrap/hhg/` completes without error, every `*.py` file parses.
- Bootstrap load: `moo_init --bootstrap hhg --sync --hostname hhg.local` exits 0.
- Smoke: `uv run python -m moo.zil_import.scripts.hhg_smoke` prints `PASS` (exit 0).

After a shared translator/generator change, ALSO re-run the zork1 smoke
(`uv run python -m moo.zil_import.scripts.zork1_smoke`) — expect 227–289 (thief-RNG band).

| Date | Result | Notes |
| --- | --- | --- |
| 2026-05-30 | **PASS** | First landing of `hhg_smoke.py`; full path through babel fish ("squish in your ear"). |
| 2026-05-30 | **PASS** | After `goto` VTYPE-gate + `clocker` +1 fixes (completed-work). Still ends at the babel fish; the post-babel-fish `_survive_vogons` step is written but NOT wired into `HHG_COMMANDS` pending the i-ford-disable bug (BUGS.md "Vogon act daemon lifecycle"). |
| 2026-06-01 | **PASS** | `__survive_vogons__` now wired into `HHG_COMMANDS`. Root-caused the "Vogon act daemon lifecycle" bug to stale per-player counters the reset never cleared (not a live runaway); reset body now re-seeds the act counters/gates. Full path runs babel fish → poetry → airlock → "scooped up" → Dark. |
| 2026-06-01 | **PASS** | After the `_h_prso_p` direction-atom fix (completed-work). Smoke unchanged (still ends at "scooped up"); the **post-smoke** continuation now reaches the Heart of Gold for the first time — attach without reset, `listen` → `go south` → Entry Bay → `wait`×~4 → Bridge. zork1 smoke also green (see below). |
| 2026-06-02 | **PASS** | Smoke **extended** to the new frontier: `__reach_heart_of_gold__` → `__take_spare_drive__` → `__plug_drive__` (post-airlock Dark → Bridge → Engine Room → take spare drive → plug into the large receptacle, "Plugged."). Required reset-body reseeds for the stale endgame globals (LOOK/ARGUMENT counters + DRIVE-TO-CONTROLS/PLOTTER/BROWNIAN/…). zork1 unaffected (hhg-only reset body + smoke script). |
| 2026-06-02 | **PASS** | After the `_.zatom` atom-map reroute for shadowed object atoms (completed-work). HHG smoke PASS unchanged; `turn on spare drive` now reaches SWITCH-F (was the dipswitch). **Shared translator/generator change** — zork1 smoke re-run **5×: 242 / 252 / 289 / 304 / 309**, peak = documented baseline, **zero Tracebacks/crashes**; the visible "did not contain" fails are the known thief-RNG tail (bolt/sluice, yellow button), and the sluice puzzle uses no rerouted atom. No cross-game regression. |
| 2026-06-02 | **PASS** | Endgame shakedown found + fixed two more: `is_held(bool)` crash that blocked leaving the Bridge with the plugged drive, and nautical directions (`port`/`fore`/`aft`/`starboard`) not dispatching (completed-work). HHG smoke PASS; importer 223; zork1 sanity smoke crash-free (pure-addition changes). |
| 2026-06-02 | **PASS** | Galley `open panel` crash root-caused + fixed (missing `THIS-IS-IT` on HHG's Thing; hand-wrote the shared substrate verb — completed-work). Live-verified the close-then-open reveal path; broad HoG verb sweep otherwise crash-free. HHG smoke PASS; importer 223; zork1 sanity smoke (shared `this_is_it` now hand-written for both games) crash-free. |
| 2026-06-02 | **PASS** | Edge-case shakedown of the endgame. Fixed `take <room>` crash (`<FSET? <LOC PRSO>>` null-guard in `_h_fset_p` — shared) and silenced the Vogon intercom (scoped `i_announcement` override — completed-work). HHG smoke PASS; **zork1 smoke 263/350, 0 crashes** (shared loc fix — no regression). New minor bugs logged: `open drive` double-rebuke, `dive` ungrammatical prompt. |
| 2026-06-02 | **PASS** | **The improbability-drive WIN now fires** — fixed `RUNNING?` to check the real `zstate_queue` instead of the never-populated C-TABLE (completed-work). HHG smoke PASS; **win ending verified live** ("Good work, kid"); zork1 smoke **309/350 Master, 0 crashes** (zork has no `RUNNING?` — pure no-op there); importer 223. Also closed the endgame part-name resolution (stale red-button `switch` alias cleared → `turn on switch` reaches SWITCH-F via `peek_into`). |
| 2026-06-02 | **PASS** | Fixed the Aft Corridor delegated-banner bug (M-LOOK banner now guarded on `here()==this` — completed-work). **Shared translator change**: HHG smoke PASS; zork1 smoke **309/350 Master, 0 crashes**; importer 223. **Gotcha learned the hard way**: don't run two smokes (or a smoke + the previous still finishing) against hhg.local concurrently — they fight over the shared world and BOTH fail at early beats (`__escape_earth__` "did not contain 'Lights whirl'" is the tell). Always wait for `^PASS`/`^FAIL` in the tee'd file before launching another. Also: a single-run FAIL at the deep `__take_spare_drive__`/`__plug_drive__` beats is usually endgame nondeterminism, not a regression — re-run once clean before believing it. |
| 2026-06-02 | **PASS** | BUGS.md sweep: fixed `dive` ("What do you want to through?" → "Wheeeeeeeeee!!!!!", `dive` added to the `verbs/actor/jump.py` stub) and `open drive` double-rebuke+"Opened." (V-routine pre-prologue now `return True` not bare `return`, so a direct `<V-CARVE>` caller sees "handled"). **Shared translator change** (prologue affects both games): HHG smoke PASS; **zork1 smoke 309/350 Master, 0 crashes** (peak — no regression; a mid-run `score` shows ~136/127-moves, ignore it per the score-poll gotcha and wait for the final). Importer **223**. Both fixes live-verified on the parked Bridge. Also confirmed live the **I-TEA missile death-timer fires** (forced seed: counter 6→15 → "missiles struck … You have died" → respawn) — reclassified BUGS.md "death-timer never fires" to known-quirks (it just needs the NUT-COM-INTERFACE puzzle to queue I-TEA; `rub pad` alone dispenses only the Substitute). |
| 2026-06-04 | **PASS** | After a full **purge + clean re-bootstrap of hhg.local** (removed an entire embedded Zork I world that had been bootstrapped into site 4 — 895→307 objects, zero strays). Exposed + fixed 3 first-init bugs: stale wizard `Player` blocking `entrust` (delete hhg Players before rebuild), `099` using the `flag` *verb* before `load_verbs` (→ `set_property`), and `HEADACHE` stale-`False` drift (reset now seeds it `True`). Smoke opener canonicalized: `take gown` / `open pocket` / `take aspirin` / `take mail` (was coasting on the old world's stale inventory). All 3 POV switches re-verified on the clean world. HHG-only changes; zork1 not regenerated. **NB: a from-scratch hhg init now works** — `moo_init --bootstrap hhg --hostname hhg.local` (non-sync) after deleting the hhg `Repository` + `Player` rows. |
| 2026-06-03 | **PASS** | Re-shook the `coverage.md:153-162` crash cluster — **almost all already fixed** by intervening work (`i`/`invent`, `i am ford`, `drink from basin`, `climb tree`, `examine wall`, `throw fluff`, `tell me about` VOWELBIT). The one real remaining bug: **HHG terminal deaths printed their narrative then left the player alive where they died** (BETTER-LUCK / sleep / drunk / groggy / brick / ramp all call `_.thing.finish()` directly, bypassing the `<JIGS-UP>`→`death.py` respawn). Fixed with a **new game-neutral `GameConfig.skip_routines` knob** (HHG `{"FINISH"}`) + hand-written `verbs/hhg/thing/score/finish.py` that respawns at `player_start`. Verified live: demolition at Front Porch (turn 20) → respawn in Bedroom, `DEATHS=2`. HHG smoke **PASS**; **zork1 bootstrap byte-identical after regen (git-clean)**, smoke **289/350, 0 crashes**; importer **223** (ratcheted `FINISH` into the HHG coverage baseline). |

### Trick: reach the Heart of Gold without hand-driving the fragile beats

The babel-fish/poetry/airlock cascade is timing-sensitive to drive by hand. To get a live
session parked at the endgame frontier: run `hhg_smoke` (it resets, plays the whole proven
path, and **ends at "scooped up" → Dark**), then `hhg_session.py start` **without** `--reset`
— the smoke's MooSSH disconnects but the Adventurer persists in the post-airlock Dark with
Celery still up. From there: `listen` (repeat until the star drive reveals — needs
DARK-COUNTER > 3), `go south` → Entry Bay, then `wait` a few times for I-FORD → Bridge.

### Lesson: `<PRSO? ,P?DIR>` must compare `get_dobj_str()`, not `prso`

DjangoMOO never resolves a movement direction to an `Object`, and the `P?<dir>` zstate
atoms are never seeded — so any generated `prso == player.zstate_get('P?SOUTH')` is dead
code (always False). `_h_equal` already handled this for `<EQUAL? PRSO ,P?DIR>` (emits
`context.parser.get_dobj_str() == 'south'`); `_h_prso_p` (for `<PRSO? ,P?DIR>`) did not,
which is why DARK-FUNCTION's `go south` exit never fired and the Heart of Gold was
unreachable for the project's whole history. Fixed by mirroring `_h_equal`. When you see a
direction comparison that should work but silently doesn't, check that BOTH handlers carry
the direction-atom special case.

### Lesson: turn-counted daemon gates need +1-per-turn stepping

HHG's later acts (the Vogon poetry/airlock cascade) are driven by daemons gated on **exact-equality** turn-counters (`CAPTAIN-COUNTER == 6`, `GUARDS-COUNTER == 6`, `AIRLOCK-COUNTER == 4`). These only fire if the counter is advanced **one per turn**. `do_command` already ticks once per command, so any verb that *also* calls `clocker`→`tick` (V-WAIT did) makes that command step the counter +2 and a gate can be skipped on a wrong-parity start (counter runs away: 56, 176). The HHG `clocker` is now a no-op for exactly this reason (zork keeps its ticking variant — its smoke hand-counts a multi-tick `wait` and it has no exact-counter gate). When adding daemon-gated content, prefer single-step counters and never let a verb double-tick.

Add a row each session.

### Lesson: `RUNNING?` / C-TABLE is dead — daemons live in `zstate_queue`, not the clock table

Any ZIL routine that walks the `C-TABLE` / `C-INTS` / `C-RTN` clock-interrupt table (HHG's `RUNNING?`, and anything that reads `<INT R>` slots) is **dead** in this port — those globals are never populated. DjangoMOO schedules daemons in the per-player `zstate_queue` (turn-mode) and the System Object `_realtime_pts` registry (realtime). The auto-translated `RUNNING?` therefore always returned False, which silently killed the improbability-drive win (`<RUNNING? ,I-TEA>` gate). Two-part fix (HHG-only — zork has no `RUNNING?`): a translator `_h_running` handler emitting `_.thing.is_running('<kebab-name>')` (NOT `is_running(_.thing.i_foo())`, which *executes* the daemon), `RUNNING?` in `_SKIP_ROUTINES`, and a hand-written `verbs/hhg/thing/predicates/is_running.py` that checks the queue. **When you see a RUNNING?-gated branch that "should" fire but doesn't, suspect the C-TABLE.** To verify the win without the (post-ejection-unreachable) plotter, force the win-state via shell on the Adventurer — `zstate_drive_to_plotter=True`, `zstate_set('BROWNIAN-SOURCE', <tea obj>)`, `zstate_tea_counter=7`, append `{'name':'i-tea','fire_at_turn':moves+50,'recurring':1}` to `zstate_queue` — then `turn on switch`.

### Gotcha: don't poll for a mid-run `score`/`rank` line — wait for the END marker + a command count

A smoke prints `score` many times mid-run. A poll loop matching `"rank of"` / `"score is"` fires on the FIRST mid-game score and reports the smoke "done" while it's still running (saw a false "87/350 Novice" that was really move 92 of a 395-command run that finished 309/350 Master). Gate the wait on a true end-of-run signal **and** a command-count threshold, e.g. `grep -c "^>>> '" out` > 300 **and** `grep -qE "TIMING|slowest|did not contain"`. Same family as the concurrent-smoke gotcha: believe only the final summary.

### Lesson: the daemon clock has a same-tick cancel/self-re-queue race — DON'T fix it in shared `queue.py`

A recurring daemon that re-arms itself at the TOP of its body (`_.queue('self', -1)`) is **immortal** if another daemon `_.cancel`s it earlier in the same `due` batch: the cancel's `zstate_drop` tombstone only suppresses the tick loop's *auto*-re-queue, not the daemon's *explicit* self-`_.queue`. This is why HHG's I-ANNOUNCEMENT intercom follows you onto the Heart of Gold (I-GUARDS cancels it, it re-adds itself). The "obvious" fix — make the tick loop strip a tombstoned daemon's self-re-queue so a DISABLE always wins same-tick — is Rule-Zero-legal (queue.py is substrate) but **broke the Vogon cascade** (`__survive_vogons__` stalled): the act's daemons (I-GUARDS/I-CAPTAIN/GUARDS-TO-AIRLOCK/I-FORD/AIRLOCK) deliberately cancel and re-queue each other across one tick in a precise order, and "disable always wins" steamrolls it. **Rule: scope any daemon-lifecycle fix to the ONE offending daemon (an HHG override under `verbs/hhg/thing/daemons/`), never the shared clock — and smoke through the full poetry act before believing it.** (BUGS.md "Vogon intercom".)

### Lesson: a per-player `zstate_*` slot that's set during play MUST be re-seeded in the reset body

HHG's reset restores object positions/properties from a snapshot captured from the
**clean, pre-play world**.  `_snapshot_restore` only rewrites properties that exist
in the snapshot — it never deletes extras.  So any `zstate_*` slot the player only
acquires *during* play (counters, puzzle flags) is invisible to the snapshot and the
restore can **never clear it**.  Left un-reset, it carries across sessions and, when
it gates a daemon on exact equality (`== 6`, `== 4`), silently wedges that content
forever once a prior run pushes it past the gate.  This has now bitten three areas
(early bulldozer/prosser/vogon counters; dark-dream + babel-fish globals; the Vogon-
act guards/captain/airlock counters) — each fixed the same way: an explicit
`adventurer.set_property("zstate_…", <canonical default>)` in `_hhg_reset_state_body.py`.
When you add daemon-gated content that reads a new `zstate_*` global, add its reset
seed in the same change.  Symptom to watch for: a counter that's already non-zero at
`post-babel` / scene entry on a fresh `--reset` — that's stale state, not a live loop.

### Lesson: every non-`<JIGS-UP>` HHG death funnels through `FINISH` — and `FINISH` is shared

HHG has two death sinks. `<JIGS-UP msg>` (in `SDK_HEADS`) emits `_.jigs_up(msg)` → the System
Object `verbs/system/death.py`, which **respawns** at `player_start`. But BETTER-LUCK (Earth
demolition / sleep / clean), GET-DRUNK, I-GROGGY, BRICK-DEATH and RAMP-F all call
`_.thing.finish()` **directly**, and the canonical generated `FINISH` just prints an unsupported
`RESTART/RESTORE/QUIT` prompt and returns — so before 2026-06-03 those deaths printed their
narrative and left the player **alive where they died**. When a death "doesn't take," check
whether it routes through `<JIGS-UP>` or straight to `<FINISH>`.

The fix had to be **HHG-scoped because `FINISH` exists in both games** (Zork's `FINISH` is
terminal-only — its `JIGS-UP` respawns directly). A global `_SKIP_ROUTINES` entry would have
dropped Zork's `FINISH` too. The new pattern: **`GameConfig.skip_routines`** (a per-game set
unioned into `_SKIP_ROUTINES`) lets one game suppress a shared routine's auto-emit and supply
its own `verbs/<dataset>/…` override, leaving the other game's generated copy untouched. Use it
whenever a routine is shared but only one game needs a hand-written replacement; pair it with a
coverage-baseline ratchet (`uv run python moo/zil_import/tests/_collect_coverage_baseline.py`)
so the newly-skipped routine is recorded. Proof it's safe for the other game: **regenerate the
other game and confirm its bootstrap is git-clean** (byte-identical) — stronger than one
nondeterministic smoke.

## Reset & smoke: parity with zork-shakedown

The two shakedowns reach the same guarantees by different mechanisms. Audited 2026-05-30:

| Concern | zork-shakedown | hhg-shakedown | Status |
| --- | --- | --- | --- |
| Object-position restore | explicit per-object re-placement in `_reset_state_body.py` (code) | snapshot capture/restore in `_hhg_reset_state_body.py` | **Parity** — verified: a session that left every item in the Vogon Hold reset to canonical positions (gown→Bedroom, towel/satchel→Ford, Adventurer→Bedroom). |
| Visited-flag sweep | room `touchbit` sweep | `touchbit` + `revisitbit` + `ndescbit` sweep | **Parity** (hhg also clears `ndescbit` — the HOLD-F M-END / I-FORD gate). |
| Smoke reset call | `docker-compose run --rm webapp` running `_RESET_SNIPPET` (reset body only) | `docker exec django-moo-shell-1 … moo_init --sync` with Celery stop/start | **Intentional divergence** — hhg's matches its harness (`hhg_session.py --reset`) and is Celery-deadlock-safe; the full bootstrap re-seed is a few seconds slower but more robust. Don't "fix" it. |
| Coverage ratchet | `test_translator_coverage.py` | same test, same baseline | **Parity** — one test covers both games. |
| End-to-end smoke | `zork1_smoke.py` (350-cmd opener, score-based) | `hhg_smoke.py` (canonical path → babel fish, PASS/FAIL) | **Parity** — both walk the hardest reachable content. |
| Snapshot staleness | n/a (reset is regenerated code) | **hhg-only gotcha**: the snapshot must be re-captured (delete it, re-sync) after a regen that changes the world model. See the "Inner loop" note above. | hhg-specific; documented. |

Standalone operator helpers zork has that hhg does **not** (low priority — covered by other tools): `zork1_reset.py` (hhg: use `hhg_session.py --reset` or `moo_init --sync`), `zork1_spot.py` (hhg: drive `hhg_session.py send/read`), `zork1_save_state.py` (hhg: the reset body auto-captures the snapshot; force a re-capture by deleting the file and re-syncing). Add dedicated hhg equivalents only if the indirection becomes annoying.

## Connected harness vs isolated shell tests

Two ways to spot-test a translator/generator change:

1. **Connected harness** (`hhg-shakedown/scripts/hhg_session.py`) — long-lived SSH session through the full shell+celery+parser flow. Use this for "does this command do the right thing for a player" questions. Equivalent to a real player typing in MooSSH; catches dispatch / state / timing bugs.
2. **Isolated `manage.py shell -c`** with `parse.interpret(ctx, cmd)` inside `ContextManager(wiz, writer, site=hhg)` — bypasses SSH and most of the celery / shell handler stack, runs the parser directly. Use this for "does this command's *implementation* compile and dispatch" questions and for inspecting object/property state. **Don't** use it to verify player-facing behavior — bugs that surface only under real dispatch will be invisible.

The user has explicitly pushed back on substituting (2) for (1) when verifying a fix. Default to the harness; only drop to isolated shell when the harness is offline or when the question genuinely doesn't depend on the SSH/celery chain.

Harness gotchas:

- Always launch via Bash `run_in_background: true`. The shell `&` operator gives the harness a controlling terminal it doesn't want — when the spawning shell exits, the harness receives `:quit` and shuts down.
- `ContextManager(caller, writer)` defaults `site=None` and overrides any prior `ContextManager.set_site(hhg)`. For isolated shell tests, always pass `site=hhg` to the constructor — otherwise `obj.contents.all()` returns empty and the parser builds an incorrect search order.
- Multiple harness or smoke instances will fight over each other. After `kill <pid>`, run `ps -ef | grep hhg` to confirm only one parent + child remain.
- `start --reset` runs the world-state reset. Without `--reset` the harness reuses whatever state was on the wire, so if a previous run left the egg munged or the kitchen window open, that state persists. When in doubt, reset.
