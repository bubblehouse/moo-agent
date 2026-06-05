# Smoke Workflow (shared)

The game-neutral development loop for ZIL importer fixes. Substitute the
game's dataset slug for `<slug>` (`zork2`, `zork3`, …) and its ZIL source
path for `<src>` (`~/Workspace/<slug>/<manifest>.zil`). Per-game progress
tables and quirks live in each skill's own `references/completed-work.md`.

## Prerequisites

- Docker stack running: `docker-compose up -d` from the django-moo repo root.
- `<slug>.local` site initialised once:
  `docker exec django-moo-shell-1 sh -c '/usr/app/bin/python /usr/app/src/manage.py moo_init --bootstrap <slug> --hostname <slug>.local'`
  (subsequent runs use `--sync`).
- ZIL source available at `<src>`.
- `phil` user has a Player record on `<slug>.local` whose avatar points at
  the Wizard. Fix:

```bash
docker exec django-moo-shell-1 sh -c '/usr/app/bin/python /usr/app/src/manage.py shell -c "
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from moo.core.models.auth import Player
from moo.core.models.object import Object
phil = User.objects.get(username=\"phil\")
site = Site.objects.get(domain=\"<slug>.local\")
wiz = Object.global_objects.get(name=\"Wizard\", site=site)
p, _ = Player.objects.get_or_create(user=phil, site=site, defaults=dict(avatar=wiz, wizard=True))
p.avatar = wiz; p.wizard = True; p.save()
"'
```

## Inner loop (per-fix)

```bash
# 1. Edit something in moo/zil_import/ (game-neutral) or game_config.py /
#    moo/zil_import/verbs/<slug>/ (game-specific).

# 2. Regen the bootstrap from ZIL source.  IMPORTANT: --output MUST point
# to moo-agent/moo/bootstrap/<slug>, not django-moo/moo/bootstrap/<slug>.
# Docker mounts moo-agent's tree (compose.override.yml mounts
# ../moo-agent/moo:/usr/app/agent/moo:ro) and resolves moo.bootstrap.<slug>
# from there via PEP 420 namespace packaging.  Writing to django-moo's tree
# silently does nothing — Python imports the moo-agent copy.
uv run python -m moo.zil_import <src> \
    --game-config <slug> \
    --output /Users/philchristensen/Workspace/bubblehouse/moo-agent/moo/bootstrap/<slug>

# 3. Sync the regenerated bootstrap into the running <slug>.local DB
docker exec django-moo-shell-1 sh -c '/usr/app/bin/python /usr/app/src/manage.py moo_init --bootstrap <slug> --sync --hostname <slug>.local'

# 4. Spot-test ONLY the commands you care about (seconds, not minutes)
uv run python -m moo.zil_import.scripts.<slug>_spot --reset \
    "look" "go north" ...

# 5. Once spot passes, run the full opener-smoke and ALWAYS tee its output
uv run python -m moo.zil_import.scripts.<slug>_smoke 2>&1 | tee /tmp/smoke.out
echo "exit=$?"; grep -c "did not contain" /tmp/smoke.out
```

**Always tee the smoke output.** Smoke runs are slow (70-130s for a full
walkthrough). `tee /tmp/smoke.out` keeps the full transcript so subsequent
inspection is a `grep`, not a re-run.

```bash
grep "did not contain" /tmp/smoke.out | head -20      # failure list
grep -E "^>>> '" /tmp/smoke.out | head -30            # command sequence
```

## Reading smoke output

Cluster failures by output text to find systemic vs one-off bugs:

```bash
grep "actual:" /tmp/smoke.out | sed -E "s/.*actual: //" | sort | uniq -c | sort -rn | head -10
```

Common clusters:

- `You can't go that way.` — exit not found. Often a cascade.
- `I don't know how to do that.` — verb dispatch failed: the verb isn't
  registered, the dobj isn't resolved, or `--dspec` rejects the sentence.
- `There is no <X> here.` — dobj not in scope. Usually a cascade.
- `>>> ��` — mangled PREFIX output; a per-clause split dropped the
  substrate fall-through.

**Find the FIRST failure** — cascading failures often resolve once the
earliest root cause is fixed:

```bash
grep -nE ">>> '" /tmp/smoke.out | head -30
```

## Live parser introspection

When the smoke says `I don't know how to do that` and you want to know why:

```bash
docker exec django-moo-shell-1 sh -c '/usr/app/bin/python /usr/app/src/manage.py shell -c "
from moo.core.models.object import Object
from moo.core.code import ContextManager
from moo.core.parse import Parser, Lexer
from django.contrib.sites.models import Site
site = Site.objects.get(domain=\"<slug>.local\")
ContextManager.set_site(site)
wiz = Object.global_objects.get(site=site, name=\"Wizard\")
lex = Lexer(\"open trap door\")
parser = Parser(lex, wiz)
print(\"dobj_str={!r} dobj={}\".format(parser.dobj_str, parser.dobj))
for o in parser.get_search_order():
    print(\"  {!r}\".format(o.name))
"'
```

Note the `ContextManager.set_site(site)` call — without it, `get_property`
decodes object refs against the wrong site's `$nothing` and returns empty
lists. Inside the running shell server the site is always set during request
handling; this only matters for ad-hoc debugging.

## Test suites

```bash
uv run pytest moo/zil_import/tests/ -n auto      # importer unit tests
uv run pytest moo/ extras/ -n auto -q            # full repo (slow)
```

The leakage test (`moo/zil_import/tests/test_no_zmachine_leakage.py`)
catches Z-machine primitives that snuck into generated output. After ANY
shared translator/generator change, re-run the **zork1** smoke
(`moo/zil_import/scripts/zork1_smoke.py`) to confirm no cross-game
regression — many fixes live in shared code.

## Connected harness vs isolated shell tests

1. **Connected harness** (`scripts/<slug>_session.py`) — long-lived SSH
   session through the full shell+celery+parser flow. Use for "does this
   command do the right thing for a player." Catches dispatch/state/timing
   bugs. **Default to this.**
2. **Isolated `manage.py shell -c`** with `parse.interpret(ctx, cmd)` inside
   `ContextManager(wiz, writer, site=site)` — bypasses SSH and most of the
   celery/shell stack. Use only for "does this verb compile and dispatch"
   and for inspecting object/property state. The user has pushed back on
   substituting this for the harness when verifying a fix.

Harness gotchas:

- Always launch via Bash `run_in_background: true`. The shell `&` operator
  gives the harness a controlling terminal it doesn't want.
- For isolated shell tests, pass `site=site` to `ContextManager(...)` —
  otherwise `obj.contents.all()` returns empty and the parser builds a
  wrong search order.
- Multiple harness/smoke instances fight each other. After `kill <pid>`,
  confirm only one parent + child remain.
- Always `--reset` when in doubt — without it the harness reuses whatever
  state was last on the wire.

## Commit hygiene

The user does the commits. Don't run `git commit` / `git push`. Leave the
tree clean enough that `/git:grouped-commit` produces scoped commits.
