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

### Lesson: turn-counted daemon gates need +1-per-turn stepping

HHG's later acts (the Vogon poetry/airlock cascade) are driven by daemons gated on **exact-equality** turn-counters (`CAPTAIN-COUNTER == 6`, `GUARDS-COUNTER == 6`, `AIRLOCK-COUNTER == 4`). These only fire if the counter is advanced **one per turn**. `do_command` already ticks once per command, so any verb that *also* calls `clocker`→`tick` (V-WAIT did) makes that command step the counter +2 and a gate can be skipped on a wrong-parity start (counter runs away: 56, 176). The HHG `clocker` is now a no-op for exactly this reason (zork keeps its ticking variant — its smoke hand-counts a multi-tick `wait` and it has no exact-counter gate). When adding daemon-gated content, prefer single-step counters and never let a verb double-tick.

Add a row each session.

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
