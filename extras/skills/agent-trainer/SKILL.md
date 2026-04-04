---
name: agent-trainer
description: Iteratively tune a running moo-agent by reading session logs, identifying behavioral errors or gaps, updating SOUL.md / baseline.md / brain.py, and restarting. Use when the user asks to improve agent behavior, fix agent errors, tune an agent, or review agent logs.
compatibility: DjangoMOO project (django-moo). Requires the moo-agent CLI and a running agent config under extras/agents/.
---

# Agent Trainer Skill

You are tuning a running moo-agent by reading its session logs, diagnosing errors, updating the right files, and restarting. This is an iterative loop — each restart should fix at least one class of error and introduce no regressions.

## Architecture Overview

See [references/architecture.md](references/architecture.md) for the full layout. Short version:

| File | Purpose |
|------|---------|
| `extras/agents/<name>/SOUL.md` | Agent persona, mission, behavioral rules, verb mappings — agent-specific |
| `extras/agents/baseline.md` | Shared context injected before SOUL — MOO command syntax, sandbox rules, gotchas |
| `extras/agents/<name>/SOUL.patch.md` | Append-only runtime patch; agent writes new rules here |
| `extras/agents/<name>/settings.toml` | SSH config, model name, max tokens |
| `extras/agents/<name>/logs/` | Session logs, one file per run, named by timestamp |
| `moo/agent/brain.py` | Perception-action loop; `_ERROR_PREFIXES` controls what the agent treats as an error |

## Workflow

### Step 1: Read the most recent log

```bash
ls -t extras/agents/<name>/logs/ | head -3
tail -n 100 extras/agents/<name>/logs/<latest>.log
```

Read the full log if it is short. For long logs, read the tail plus any `[server_error]` lines:

```bash
grep -n "server_error\|LLM error\|Error detected" extras/agents/<name>/logs/<latest>.log
```

### Step 2: Check whether the agent is still running

```bash
ps aux | grep moo-agent | grep -v grep
```

If the agent has crashed or is stuck in an LLM error retry loop (60-second wakeup, repeated `[LLM error]` entries), kill it before editing files.

### Step 3: Diagnose each problem

Classify each issue into one of three categories:

**A. Undetected game error** — the server returned an error message but the agent didn't notice. Fix: add the error prefix to `_ERROR_PREFIXES` in `moo/agent/brain.py`.

**B. Missing or wrong guidance** — the agent attempted something incorrectly because the rules weren't clear enough. Fix: add or sharpen the relevant rule in `baseline.md` (universal MOO syntax) or `SOUL.md` (agent-specific behavior).

**C. Infrastructure bug** — crash, hang, or incorrect loop behavior in the agent code itself. Fix: edit `moo/agent/brain.py`, `cli.py`, `connection.py`, or `soul.py`.

See [references/error-patterns.md](references/error-patterns.md) for a catalog of known patterns.

### Step 4: Edit the right file

**`_ERROR_PREFIXES` in `brain.py`** — add the exact string prefix that appears at the start of the undetected error line:

```python
_ERROR_PREFIXES = (
    ...
    "Huh?",          # unrecognized verb
    "There is no ",  # name-based lookup failure
)
```

**`extras/agents/baseline.md`** — add rules that apply to any agent. Use plain prose under a `##` heading. Concrete examples beat abstract descriptions. Mark critical constraints in bold.

**`extras/agents/<name>/SOUL.md`** — add rules specific to this agent's domain. Unknown `## Subsections` under `# Persona` are folded into context and sent to the LLM, so any new section will be included automatically.

**Do not edit `SOUL.patch.md`** — that file is agent-writable. Read it to understand what the agent has learned, but leave it alone.

`SOUL.patch.md` now supports three section types: `## Rules of Engagement` (reflexive rules), `## Verb Mapping` (intent aliases), and `## Lessons Learned` (free-form notes written via `SOUL_PATCH_NOTE:`). Lessons Learned content is merged into `soul.context` and injected into the system prompt on every session.

### Step 5: Kill and restart

```bash
# Kill by PID (from ps output above)
kill <PID>

# Restart in background
uv run moo-agent run extras/agents/<name> > /tmp/moo-agent-<name>.log 2>&1 &
echo "PID: $!"
```

Confirm the new log file appeared:

```bash
ls -t extras/agents/<name>/logs/ | head -3
```

### Step 6: Monitor

Set a background timer and check the log in 3–5 minutes. Verify:

- The agent connected and loaded its soul
- It completed at least one LLM cycle without an error
- Any previously failing pattern now produces a `[server_error]` and returns control to the LLM

Repeat from Step 1.

## What to Change Where

| Symptom | Root cause | Fix |
|---------|-----------|-----|
| Agent continues after "Huh?" or "There is no X here" | Error prefix not in `_ERROR_PREFIXES` | Add prefix to `brain.py` |
| Agent continues after "There is already an exit in that direction" | Error prefix not in `_ERROR_PREFIXES` | Add prefix to `brain.py` |
| Agent uses `"foo_bar"` instead of `"foo bar"` | Guidance not emphatic enough | Strengthen rule in `baseline.md` |
| Agent puts multiple `@create` in one SCRIPT | Guideline not followed | Mark rule CRITICAL in `baseline.md`, add bad/good example |
| Agent creates object but skips `@alias`/`@obvious` | Rule missing | Add to `baseline.md` |
| Agent uses nonexistent verb (e.g. `speak NPC`) | Wrong mental model | Add correct pattern to `SOUL.md` |
| Agent renames a room instead of digging a new one | Navigation confusion | Add navigation check guidance to `SOUL.md` |
| Agent uses `import lookup` in `@eval` | Wrong mental model about pre-injected names | Add explicit "no import in @eval" rule to `baseline.md` |
| Agent writes `if lookup(x) else` None-check pattern | Doesn't know `lookup` raises, not returns None | Add `try/except NoSuchObjectError` example to `baseline.md` |
| Agent spends many cycles inspecting exits/rooms without building | World-state confusion spiral after navigation failures | Self-correcting; if persistent, add SOUL.md cap (2 @show max, then pick fresh direction) |
| Agent's DONE summary claims success after a mid-script error | LLM writes DONE from intent, not from actual output | No fix yet; see error-patterns.md |
| LLM 400 error with internal tokens in response | Model leaking chat tokens | Transient; kill and restart |
| Agent TUI crashes when run headless | `sys.stdin.isatty()` not checked | Fix in `cli.py` |
| Agent assigns `obj.name = "..."` but rename doesn't persist | `name` is a Django model field — requires `obj.save()` | Add to `baseline.md` under a "model fields" section |
| Agent tries `@dig <dir>` without checking if exit exists | Doesn't inspect room state before acting | Add "check exits before digging" rule to `baseline.md` |
| Agent creates verb then skips testing it | Verb testing rule not emphatic enough | Reframe as REQUIRED with test call in the same `SCRIPT:` as `@edit` |
| Verb has `--dspec any` in shebang but `direct_object='none'` in DB | `parse_shebang` requires `--on` — without it, or with a typo'd flag, `at_edit.py` returns `"Error: malformed shebang"` and the verb is not saved | `"Error: malformed"` is in `_ERROR_PREFIXES`; fix is to add `--on $thing` to the shebang |
| Agent calls `switch monitors` but gets "verb doesn't take a direct object" | Verb shebang missing `--dspec any` (or `--on` so it parses) | Fix shebang guidance; verify via `docker exec django-moo-webapp-1 bin/python src/manage.py shell` |
| Agent uses `@describe "Room Name"` after renaming a room | Name-based lookup fails — object isn't "here" after rename | Use `@describe here as ...` or `@describe #N as ...` instead |
| Verb code gets `NameError: name 'lookup' is not defined` at runtime | `lookup` (and all SDK names) must be explicitly imported in verb code — unlike `@eval` | Add `from moo.sdk import lookup` (or `context`, etc.) to top of verb; add to `baseline.md` |
| `@edit verb X on #N` returns "Text set on #M (note)" instead of "Created verb" | A `$note` in wizard's inventory wins dispatch over the intended dobj | Move notes out of inventory via Django shell: `Object.objects.filter(pk=NOTE_PK).update(location_id=ROOM_PK)` |
| `@eval "obj.description = '...'; obj.save()"` has no effect | `description` is a MOO Property, not a model field — attribute assignment is discarded | Use `obj.set_property('description', '...')` instead; add to `baseline.md` |
| `@alias "name"` or `@edit verb` lands on wrong object (#113 instead of #434) | Name collision — older object with same name found first in parser search | Always use `#N` for all operations after `@create`; recover via `v.origin = Object.objects.get(pk=N); v.save()` in Django shell |
| Agent stalls 7–15 min after completing a sub-goal, log frozen | Long open-ended "what next?" inference exhausts KV cache | Kill and restart; fresh context generates faster |
| Agent acts on hallucinated `#N` ("Assuming output reveals #415 (cracked gauge)") | LLM writes DONE and next actions from intent before seeing server responses | Inject corrective goal when agent acts on wrong `#N` for 2+ consecutive cycles |

## Principles

- **One fix per problem, minimum surface area.** Don't rewrite sections when a sentence will do.
- **Concrete beats abstract.** "Never use underscores in quoted names" is better than "use correct name formatting".
- **Test by reading the next log.** If the pattern reappears unchanged, the fix didn't reach the LLM — check that the section is under a recognized heading and is being included in the system prompt.
- **brain.py fixes take effect immediately on restart.** SOUL.md and baseline.md fixes require the soul to be reloaded, which also happens on restart.
- **Don't touch `SOUL.patch.md`.** It reflects the agent's own learned state. Reading it is fine.
