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
# The sync's 099_reset_state.py will print "hhg reset: captured snapshot..." on first run
# (or "restored snapshot..." subsequently).  If you see "zork1 reset" instead, you
# regenerated without --game-config hhg — the wrong reset body shipped.  Fix the
# regen, delete /usr/app/snapshots/hhg-site-4.json, re-sync.

# 4. Spot-test ONLY the commands you care about (seconds, not minutes)
uv run python -m moo.zil_import.scripts.hhg_spot --reset \
    "look" "go north" "go east" "go west" "go west" "move rug" "open trap door"

# 5. Once spot passes, run the full smoke (~70s) and ALWAYS save its output to a file
uv run python -m moo.zil_import.scripts.hhg_smoke 2>&1 | tee /tmp/smoke.out
echo "exit=$?"; grep -c "did not contain" /tmp/smoke.out
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

No HHG smoke test exists yet. Until one lands, the headline metrics are:

- Translator pass: HHG ZIL → `moo/bootstrap/hhg/` completes without error, every `*.py` file parses.
- Bootstrap load: `moo_init --bootstrap hhg --sync --hostname hhg.local` exits 0.
- Opener: the five-step canonical opening sequence (see [coverage.md](coverage.md)) renders without traceback.

Once an HHG smoke harness exists, track its pass count here. Capture state changes after each fix:

| Date | Pass / Total | Notes |
| --- | --- | --- |

Add a row each session.

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
