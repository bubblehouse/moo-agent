---
name: agent-trainer
description: Iteratively tune a running moo-agent by reading session logs, identifying behavioral errors or gaps, updating SOUL.md / baseline.md / brain.py, and restarting. Use when the user asks to improve agent behavior, fix agent errors, tune an agent, or review agent logs.
compatibility: DjangoMOO project (django-moo). Requires the moo-agent CLI and a running agent config under extras/agents/.
---

# Agent Trainer Skill

You are tuning a running moo-agent by reading its session logs, diagnosing errors, updating the right files, and restarting. This is an iterative loop — each restart should fix at least one class of error and introduce no regressions.

## The Mailmen

Two timer-based agents that write increasingly vitriolic letters to each other. No token chain — each agent wakes on its own timer, checks mail, and responds.

| Agent dir | Name | SSH user | Player class | Domain |
|-----------|------|----------|--------------|--------|
| `cliff/` | Cliff | `cliff` | $player | Condescending know-it-all letters to Newman |
| `newman/` | Newman | `newman` | $player | Paranoid conspiratorial replies to Cliff |

**Settings:** `idle_wakeup_seconds = 30` (Cliff) / `45` (Newman), `stall_timeout_seconds = 0`. Both use timer-based wakeup, not page-triggered.

Start/stop: `agentmux --group mailmen start` / `agentmux --group mailmen check`.

## The Tradesmen

The current agent roster is six specialized agents. Foreman orchestrates the token
chain; the five workers execute in the order Foreman dispatches.

| Agent dir | Name | SSH user | Player class | Domain |
|-----------|------|----------|--------------|--------|
| `foreman/` | Foreman | `foreman` | $player | Token orchestration, stall timer |
| `mason/` | Mason | `mason` | $player | Rooms, exits, descriptions |
| `tinker/` | Tinker | `tinker` | $programmer | Interactive `$thing` objects, secret exits via verbs |
| `joiner/` | Joiner | `joiner` | $player | `$furniture` and `$container` objects |
| `harbinger/` | Harbinger | `harbinger` | $programmer | One NPC per room |
| `stocker/` | Stocker | `stocker` | $programmer | Consumable items, dispensing objects, multi-use props |

**Token chain:** Foreman → Mason → Foreman → Tinker → Foreman → Joiner → Foreman →
Harbinger → Foreman → Stocker → Foreman → (loop). Start Foreman first; it pages Mason automatically.
Tinker, Harbinger, and Stocker need `$programmer` accounts because they use `@edit verb` and `@eval`.
All six workers (including Mason) must have `idle_wakeup_seconds = 0` — loading a prior session goal causes agents to call `done()` immediately on restart without doing any work.

## The Inspectors

Four specialized agents that audit an existing build and record observations. Used for
regression testing after verb/permission changes touch take/drop, exits, or descriptions.

| Agent dir | Name | SSH user | Player class | Domain |
|-----------|------|----------|--------------|--------|
| `foreman/` | Foreman | `foreman` | $player | Token orchestration (shared with Tradesmen) |
| `warden/` | Warden | `warden` | $player | Exit locking, doors, traversal |
| `quartermaster/` | Quartermaster | `quartermaster` | $player | Containers, take/drop, ownership |
| `archivist/` | Archivist | `archivist` | $player | Notes, books, paper records |

**Group config:** `extras/agents/groups/inspectors.conf` defines `SESSION="inspectors"`,
`AGENTS=(foreman quartermaster warden archivist)`, and `TOKEN_CHAIN` — which
is the order Foreman dispatches the token in.

**Reorder `TOKEN_CHAIN` when regression tests need prioritization.** When a specific
verb change needs validation first (e.g., new exit locking requires Warden first,
new container/take verbs require Quartermaster first), edit `TOKEN_CHAIN` in the
group conf before starting:

```bash
# warden,quartermaster,archivist   → tests locking first, then containers
# quartermaster,warden,archivist   → tests containers first, then locking
```

Start/stop: `agentmux --group inspectors start` / `agentmux --group inspectors check`.

**Auto-relay:** Foreman's relay is now deterministic (no LLM needed). Add `token_chain` to Foreman's
`settings.toml` — brain.py will automatically page the next agent when a done page arrives:

```toml
[agent]
token_chain = ["mason", "tinker", "joiner", "harbinger", "stocker"]
```

Without this, Foreman's LLM frequently relays back to the wrong agent or skips an agent in the chain.

When tuning a specific agent, substitute its directory name for `<name>` in all
workflow steps below.

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

### Step 1.5: Read and audit SOUL.patch.md

**Always read `SOUL.patch.md` before diagnosing.** The agent writes to this file autonomously and it accumulates stale, wrong, or contradictory facts across sessions. Bad entries are injected into the system prompt on every run and can override correct guidance.

```bash
cat extras/agents/<name>/SOUL.patch.md
```

Check for:

- **Wrong facts** — e.g., `"@edit ... with '...' is currently broken"` when it actually works. A single incorrect lesson can break an entire class of behavior for all future sessions.
- **Entries under the wrong section** — `## Verb Mapping` must only contain `intent -> command` pairs. Notes, typo corrections, and lessons do not belong there; they belong under `## Lessons Learned`.
- **Stale object IDs** — notes like "centrifuge ambiguity requires renaming #166" reference DB objects that no longer exist after a DB reset.
- **Session-specific observations** — "Dr. Aris's tell verb has a SyntaxError" is only relevant for the session where it happened.

If you find bad entries, clear the file to empty sections before restarting:

```markdown
## Lessons Learned

## Verb Mapping

## Rules of Engagement
```

### Step 1.75: Check per-cycle runtime

Run `agentmux stats` (or `agentmux --group <name> stats`) to see the wall-clock
cycle duration and work-per-cycle distribution for each agent. Each LLM cycle
emits a `[Cycle] duration=... tool_calls=... commands=... script_lines=...`
marker in its log; `agentmux stats` aggregates the most recent 3 logs per agent
(override with `--logs N`).

Compare against these soft targets:

| Agent class                               | avg cycle | max cycle | max commands/cycle |
|-------------------------------------------|-----------|-----------|--------------------|
| Orchestrators (Foreman)                   | < 20s     | < 60s     | < 3                |
| Builders (Mason, Tinker, Joiner, Stocker) | < 60s     | < 180s    | < 10               |
| Inspectors (Warden, Quartermaster, etc.)  | < 45s     | < 120s    | < 8                |

If an agent exceeds `max cycle` or its `max_cmds` column is > 15, it's doing too
much in one turn. Root causes are usually one of:

- SOUL.md encourages batching ("plan the whole room, then build it in one pass")
- Missing `PLAN:` / `DONE:` checkpoints that would break work into cycles
- Context bloat — SOUL.md + baseline.md + SOUL.patch.md > 8k tokens

Fix by trimming the agent's SOUL.md to narrow the per-turn scope, or by adding
an explicit "one <thing> per cycle" rule. Re-run `agentmux stats` after the
next few cycles to confirm the shift. A successful tuning pass should lower
`avg_dur` or `max_cmds` without leaving work undone.

**Foreman's stall detector also uses this data.** When Foreman's fixed
`stall_timeout_seconds` fires, it shells out to `agentmux cycle-age <agent>`
to check whether the target is still inside a plausible cycle. If
`age < max(stall_s, 3 × p95)` — the target is slow but alive — Foreman logs
`[Stall] <agent> elapsed=...s within 3×p95=...s — still cycling, skipping
re-page` and holds the page. Only when the target truly exceeds the adaptive
threshold (or the subprocess fails) does Foreman actually re-page.

To debug this pathway manually:

```bash
agentmux --group tradesmen cycle-age tinker   # prints "<age_s> <p95_s>"
```

`-1 -1.0` means no `[Cycle]` markers exist yet (agent hasn't completed a
cycle under the Phase 1 instrumentation) or fewer than 5 samples. In that
case Foreman falls back to the old fixed-timer behavior.

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

**`SOUL.patch.md`** — read it first (Step 1.5). If it contains wrong facts or misplaced entries, clear it to empty sections before restarting. Do not leave stale entries — they are injected into every future session.

`SOUL.patch.md` now supports three section types: `## Rules of Engagement` (reflexive rules), `## Verb Mapping` (intent aliases), and `## Lessons Learned` (free-form notes written via `SOUL_PATCH_NOTE:`). Lessons Learned content is merged into `soul.context` and injected into the system prompt on every session.

### Step 5: Kill and restart

To restart a single agent by name:

```bash
extras/skills/agent-trainer/scripts/agentmux restart <name>
# e.g.: agentmux restart mason
```

This kills the process, sends Ctrl-C to the pane, and relaunches it. The tmux session must already exist.

Confirm the new log file appeared:

```bash
ls -t extras/agents/<name>/logs/ | head -3
```

To restart **all six agents** at once, use the `agentmux` script:

```bash
# After a Docker server restart (shell container already running):
extras/skills/agent-trainer/scripts/agentmux start

# If SSH connections are stale (agents hang at "Connecting...") and the shell is not freshly started:
extras/skills/agent-trainer/scripts/agentmux start --restart-shell

# Restart a single agent by name (session must already exist):
extras/skills/agent-trainer/scripts/agentmux restart mason
```

**Do not use `--restart-shell` after a Docker server restart.** The shell container is already running on port 8022; restarting it causes an "address already in use" race condition.

## DB Refresh Procedure

After refreshing the database, run `moo_init --sync` to recreate agent accounts, then flush Redis, then purge old logs/builds before starting agents:

```bash
# 1. Recreate agent accounts (passwords, Player records, MOO objects)
docker compose exec webapp bin/python src/manage.py moo_init --sync

# 2. Flush Redis — stale Celery tasks reference old object PKs and spam Object.DoesNotExist
docker compose exec redis redis-cli FLUSHDB

# 3. Purge stale logs, build yamls, and traversal plans for all agents
for a in foreman mason tinker joiner harbinger stocker; do
  rm -f extras/agents/$a/logs/*.log
  rm -f extras/agents/$a/builds/*.yaml
  > extras/agents/$a/builds/traversal_plan.txt
done

# 4. Review and clear SOUL.patch.md files — stale #N references from old DB are injected on every run
for a in foreman mason tinker joiner harbinger stocker; do
  cat extras/agents/$a/SOUL.patch.md  # audit for object IDs like #123
done

# 5. Start agents
extras/skills/agent-trainer/scripts/agentmux start
```

**Agent SSH accounts and password hashing:** `moo/bootstrap/default.py` creates agent Django users with `get_or_create` + `set_password()`. If agents fail with "Permission denied" after a DB reset, the passwords may be stored as raw strings (a past bug where `defaults=dict(password=...)` was used instead). Fix by running:

```bash
docker compose exec webapp bin/python src/manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
for username, password in [('foreman','Jk2mR7nXpW5q'),('mason','Mxq7vB2nKpL4'),
    ('tinker','Pw9cX3mZrT6y'),('joiner','Hn4kD8sQvY2f'),
    ('harbinger','Bt6wF5jRcU3e'),('stocker','Vn5sL9eJwA7k')]:
    u, _ = User.objects.get_or_create(username=username)
    u.set_password(password); u.save(); print(f'{username}: hashed')
"
```

A correctly hashed password starts with `pbkdf2_sha256$`. Raw strings (the bug) look exactly like the password itself.

**Note:** The agents use `asyncssh` internally — not the system `ssh` command. Testing auth with `ssh -p 8022 user@localhost` from the host is useful for diagnosis but is not the same code path the agents use. Confirm auth works by checking the shell container logs for `Auth for user X succeeded` after an agent connects.

### Step 6: Monitor

**Always create a cron job immediately after restarting** so stalls are caught automatically:

```
CronCreate every 5 minutes: run .claude/skills/agent-trainer/scripts/agentmux check
```

`agentmux check` kills and restarts any agent whose last log entry is more than 8 minutes old, and is a no-op when everything is healthy.

**False positive on fresh start:** Immediately after `agentmux start`, agents show `CRASHED (Ns)` if they haven't yet written a timestamped log line. This is harmless — the restart just gives them a clean slate. After one LLM cycle the log will have a timestamp and subsequent checks will show `OK`.

The cron job is session-only — recreate it whenever you start a new conversation with an agent running.

Then verify the first cycle manually:

- The agent connected and loaded its soul
- It completed at least one LLM cycle without an error
- Any previously failing pattern now produces a `[server_error]` and returns control to the LLM

Repeat from Step 1.

## Running All Six Agents with agentmux

Use `.claude/skills/agent-trainer/scripts/agentmux` to manage agent sessions. It handles all tmux setup
reliably — do not use raw `tmux` commands to start agents.

agentmux supports named groups via `--group <name>` (default: `tradesmen`). Group definitions live in `extras/agents/groups/<name>.conf` (shell-sourceable, defines `SESSION`, `AGENTS`, `STALE_SECONDS`).

```bash
# Tradesmen (default group)
agentmux start                         # Start all six agents in a 3×2 grid
agentmux start --restart-shell         # Also restart django-moo-shell-1 first (clears stale SSH)
agentmux stop                          # Kill all agents and close the session
agentmux restart                       # Stop then start
agentmux status                        # Show last log line + age + stall flag for each agent
agentmux check                         # Kill and restart any stalled agents
agentmux stats                         # Per-agent cycle runtime + work-per-cycle stats
agentmux stats --logs 5                # Widen the window to the last 5 logs per agent
agentmux cycle-age tinker              # Print "<age_s> <p95_s>" for one agent (used by Foreman's hybrid stall check)
tmux attach -t tradesmen               # Attach to the running session

# Mailmen group
agentmux --group mailmen start
agentmux --group mailmen check
agentmux --group mailmen restart cliff # Restart a single agent within the group
tmux attach -t mailmen
```

**When to use `--restart-shell`:** Only when SSH connections are stale (agents hang at "Connecting...") and the shell container is not already freshly started. After a Docker server restart, the shell container is already running on port 8022 — using `--restart-shell` will kill and restart it, causing an "address already in use" race condition as the old process releases the port. In that case, use plain `agentmux start`.

Layout result:

```
┌──────────────┬──────────────┬──────────────┐
│ foreman      │ mason        │ tinker       │
├──────────────┼──────────────┼──────────────┤
│ joiner       │ harbinger    │ stocker      │
└──────────────┴──────────────┴──────────────┘
```

Pane index mapping: 0=Foreman, 1=Mason, 2=Tinker, 3=Joiner, 4=Harbinger, 5=Stocker.

Each pane runs the full TUI (prompt_toolkit). The TUI adapts to pane size.

To restart a single agent after editing its SOUL.md:

```bash
# Send Ctrl-C to Mason's pane (pane 1), then restart
tmux send-keys -t tradesmen:0.1 C-c "" Enter
tmux send-keys -t tradesmen:0.1 "uv run moo-agent run extras/agents/mason" Enter
```

## Inspecting Running Agents

### Navigate between panes

Inside the tmux session:

- `Ctrl+B` then arrow key — move to adjacent pane
- `Ctrl+B q` — flash pane numbers; press a number to jump to that pane
- `Ctrl+B o` — cycle forward through all panes in order

Each pane shows the agent's live TUI. Use `Escape` to enter scroll mode and
browse past output. Press `Escape` again to return to live autoscroll.

### Read a specific agent's log from outside tmux

```bash
# Most recent log for mason
tail -n 50 extras/agents/mason/logs/$(ls -t extras/agents/mason/logs/ | head -1)

# All server errors across all agents in last run
for a in foreman mason tinker joiner harbinger stocker; do
  echo "=== $a ==="; grep server_error extras/agents/$a/logs/$(ls -t extras/agents/$a/logs/ | head -1)
done
```

### Iterate through all six logs in sequence

```bash
for a in foreman mason tinker joiner harbinger stocker; do
  echo; echo "=== $a — last 20 lines ==="; tail -20 extras/agents/$a/logs/$(ls -t extras/agents/$a/logs/ | head -1)
done
```

### Type an instruction into a specific agent's TUI

Each TUI has an input field at the bottom. From outside tmux:

```bash
# Send a goal instruction to Harbinger (pane 4)
tmux send-keys -t tradesmen:0.4 "visit all rooms and report how many NPCs you placed" Enter

# Send a goal instruction to Stocker (pane 5)
tmux send-keys -t tradesmen:0.5 "visit all rooms and report how many items you placed" Enter
```

The instruction appears as `[operator]` in the log and is injected into the
agent's next LLM cycle.

## What to Change Where

| Symptom | Root cause | Fix |
|---------|-----------|-----|
| `agentmux stats` shows avg cycle over target or max_cmds > 15 | SOUL.md encourages batching; per-turn scope too wide | Narrow per-turn scope in SOUL.md ("one object per cycle"); re-run `agentmux stats` after a few cycles to confirm the shift |
| Agent continues after "Huh?" or "There is no X here" | Error prefix not in `_ERROR_PREFIXES` | Add prefix to `brain.py` |
| Agent continues after "There is already an exit in that direction" | Error prefix not in `_ERROR_PREFIXES` | Add prefix to `brain.py` |
| Agent uses `"foo_bar"` instead of `"foo bar"` | Guidance not emphatic enough | Strengthen rule in `baseline.md` |
| Agent puts multiple `@create` in one SCRIPT | Guideline not followed | Mark rule CRITICAL in `baseline.md`, add bad/good example |
| Agent creates object but skips `@alias`/`@obvious` | Rule missing | Add to `baseline.md` |
| Agent uses nonexistent verb (e.g. `speak NPC`) | Wrong mental model | Add correct pattern to `SOUL.md` |
| Agent renames a room instead of digging a new one | Navigation confusion | Add navigation check guidance to `SOUL.md` |
| Agent uses `import lookup` in `@eval` | Wrong mental model about pre-injected names | Add explicit "no import in @eval" rule to `baseline.md` |
| Agent writes `if lookup(x) else` None-check pattern | Doesn't know `lookup` raises, not returns None | Add `try/except NoSuchObjectError` example to `baseline.md` |
| Agent spends many cycles inspecting exits/rooms without building | World-state confusion spiral after navigation failures — often triggered by recovering from "There is already an exit in that direction" error during Expansion Pass | Not reliably self-correcting; after 3+ consecutive `@show here` cycles with no navigation, kill and restart. Fresh context breaks the spiral. |
| Agent's DONE summary claims success after a mid-script error | LLM writes DONE from intent, not from actual output | No fix yet; see error-patterns.md |
| LLM 400 error with internal tokens in response | Model leaking chat tokens | Transient; kill and restart |
| `<\|endoftext\|>` appears inside a `COMMAND:` or `SCRIPT:` directive | LM Studio model leaks BOS/EOS tokens into assistant output | Already handled in `brain.py` — stripped before directive parsing. If a new model reintroduces this, add the token to the `.replace()` call near the top of the response-cleaning block. |
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
| Agent log shows "Connecting to localhost:8022…" for 45+ seconds, never connects | Stale SSH connections from rapid kill/restart not cleaned up by the shell service | `.claude/skills/agent-trainer/scripts/agentmux restart --restart-shell` — restarts the shell container and all agents in one step. |
| Agent fires LLM cycles despite `--delay 0` CLI flag; page-triggered mode not active | `--delay 0` sets startup delay, not `idle_wakeup_seconds`; page-triggered mode requires `idle_wakeup_seconds = 0` in `settings.toml` | Set `idle_wakeup_seconds = 0` in the agent's `settings.toml`; `--delay` is a separate startup-pause parameter |
| Agent acts on hallucinated `#N` ("Assuming output reveals #415 (cracked gauge)") | LLM writes DONE and next actions from intent before seeing server responses | Inject corrective goal when agent acts on wrong `#N` for 2+ consecutive cycles |
| Agent emits `BUILD_PLAN:` 5+ times without ever building | `_save_build_plan` didn't set follow-up state; LLM re-plans on every wakeup | Set `_memory_summary` in `_save_build_plan` to tell agent to start building |
| Agent ignores `BUILD_PLAN` room list, invents new room names mid-session | `_current_plan` not populated from BUILD_PLAN YAML | `_save_build_plan` now extracts room names via regex and sets `_current_plan` |
| Agent keeps revisiting completed rooms, never progresses to next | `_current_plan` never shrinks — completed room stays at top of list | Add `PLAN: remaining \| rooms` directive to SOUL.md; agent emits it after each room |
| Agent uses `@describe "Room Name"` — fails "There is no X here" | Rooms can't be found by name; must use `here` or `#N` | Add rule to `baseline.md`; use `@describe here as "..."` for current room |
| After failed `@dig`, agent goes through existing exit and overwrites wrong room | Didn't confirm room identity before describing | Add pre-build `@show here` checklist to SOUL.md covering dig, describe, create |
| `\"` inside `@edit verb ... with "..."` stores broken verb code (SyntaxError at runtime) | `\"` terminates the outer string prematurely; stored code starts with `"` | Fix SOUL.md NPC tell example to avoid `\"` — use `f'{this.name} says: {line}'` |
| `SOUL.patch.md` has lessons under `## Verb Mapping` section | Agent writes SOUL_PATCH_NOTE anywhere; section headers are not enforced | Read and audit patch file at session start (Step 1.5); clear if corrupt |
| `SOUL.patch.md` has wrong fact that disables a working feature | Agent wrote incorrect lesson from misdiagnosed error | Clear patch file before restart; the dangerous false entry was `"@edit ... with '...' is currently broken"` |
| Agent puts tool call syntax (`move_object(...)`) in a `SCRIPT:` block | LM Studio model mixes tool-call format with SCRIPT: text dispatch | `_handle_script_line()` now tries `parse_tool_line(step, known_names)` on each step; bare calls matching a known tool are expanded via `spec.translate()` |
| Server creates object with `"name` — quote is part of the name | LLM response truncated mid-tool-call, sending unmatched-quote command to parser | `_check_quotes()` added to `Lexer.__init__()` in `parse.py`; raises `UsageError('Unmatched quote in command.')` when unescaped `"` count is odd |
| Agent emits new `BUILD_PLAN:` on restart, forgets original plan and prior rooms | `Brain.__init__()` reset `_current_plan = []`; no plan loaded from disk | `_load_latest_build_plan()` now called in `__init__()` — reads most recent `builds/*.yaml` and populates `_current_plan` |
| Inference stalls 5-15 min — system prompt too large for KV cache | Total system prompt ~10k tokens (SOUL + baseline + 4 reference files) | Remove redundant reference files from `## Context` when tools cover the syntax; trim `baseline.md` sections replaced by tools (aliases, obvious, furniture placement, Response Format) |
| `_load_latest_build_plan()` loads a truncated/partial yaml, giving agent a 2-room plan | LLM response truncated mid-`BUILD_PLAN:` — yaml file was written incomplete | Delete stale `builds/*.yaml` files before restart when prior sessions used different manor names or builds were abandoned; agent will re-plan from current world state |
| Agent emits second `BUILD_PLAN:` mid-session with fewer rooms, overwriting original plan | No guard on `_save_build_plan()` — any mid-session re-plan replaces `_current_plan` | Added `if self._current_plan: return` guard at top of `_save_build_plan()` in `brain.py` |
| Agent passes room ID (`#41`) as direction to `go()` | Agent confuses "navigate to room #41" with the `go()` direction API | `_go()` in `tools.py` validates direction against `_VALID_DIRECTIONS`; returns `say ERROR:` for room IDs or unknown strings |
| Agent emits bare `GOAL` or `DONE` as a MOO command | Single-line fallback dispatcher treated keyword-only lines as commands | Added `_BARE_DIRECTIVES` set in `brain.py`; bare directive words are filtered from the single-line command fallback |
| Gemma emits identical tool call batch twice in one response | Model-level duplication; same `(name, input)` pairs appear twice in `tool_calls` | Added deduplication loop in `_llm_cycle()` before processing `llm_resp.tool_calls`: skip any `(name, str(input))` key already seen |
| Only first tool call per LLM cycle executes; rest wait for idle wakeup | Celery-based verbs (@create, @obvious, @alias) return no output within PREFIX/SUFFIX window — `pending_drain` never set — wakeup fires new LLM cycle discarding queue | Added fallback drain path in `run()` timeout handler: if `_script_queue` non-empty and status != THINKING, drain without waiting for output |
| `@edit #N/verb with "..."` returns "I don't understand you." | Wrong `@edit` syntax — actual syntax is `@edit verb <name> on <obj> with <content>` | Fixed `_write_verb()` in `tools.py` to generate `@edit verb {verb} on {obj} with {quoted}` |
| `@show here` on a room doesn't list room contents (no object IDs visible) | `at_show.py` shows properties but not `obj.contents.all()` | Added Contents: section to `at_show.py`: `for item in obj.contents.all(): print(f"    {item}")` — update DB with Django shell: `Verb.objects.get(pk=125).code += contents_code; v.save()` |
| `BUILD_PLAN:` multi-line YAML only saves first line to `.yaml` file | `_BUILD_PLAN_RE = r"^BUILD_PLAN:\s*(.+)$"` only matches one line; subsequent YAML lines fall through as thoughts | Replaced single-line regex with state-machine accumulator in `_llm_cycle()`: collect lines after `BUILD_PLAN:` until next directive, then call `_save_build_plan(joined)` |
| After `AmbiguousObjectError` on `@alias`, agent creates a new object with a different name instead of using `#N` | Agent treats the collision as a naming problem rather than a "use `#N`" problem; creates "industrial generator", "heavy industrial generator", etc. in a loop | Add to SOUL.md `## Common Pitfalls`: after `AmbiguousObjectError`, skip the failing `@alias` and use `#N` from the preceding `@create` output — never create a replacement object |
| `@write_verb tell on #N with "..."` crashes with `Object.DoesNotExist` | Agent used tool name as a MOO command (`@write_verb`) in a SCRIPT: block, and `#N` was hallucinated before the `@create` that would assign it | Add to SOUL.md: `@write_verb` is not a MOO command — use the `write_verb` tool; never reference `#N` until you have seen it in a `[server]` response |
| `@move X to $furniture_object` → `PermissionError: #N did not accept #M` | `$furniture` has no container behavior — only `$container` can hold objects | Add to SOUL.md/baseline.md: use `$container` for any object meant to hold other objects; `$furniture` is for seating/tables and cannot accept contents |
| `@tunnel south to #29 done.` → `There is no '#29 done.' here.` | LLM appends `done.` (from a nearby DONE: directive or inline commentary) as part of the command text | Added defensive strip in `_handle_script_line()` in `brain.py`: for any step starting with `@tunnel`, `re.sub(r"\s+done\.?\s*$", "", step, flags=re.IGNORECASE)` |
| LLM emits `<tool_call>{"name": "go", "arguments": {...}}</tool_call>` XML but tool never executes | LM Studio fallback only parsed `TOOL:` directives; XML tool-call blocks were logged as `[thought]` and discarded | Added `_XML_TOOL_CALL_RE` regex and a first-pass XML parser in the LM Studio fallback before `TOOL:` line parsing in `brain.py` |
| LLM emits `<call:go(direction='north')>` self-closing tag → "Huh?" | Existing XML stripper only handles `<tag>content</tag>`; `<call:name(args)>` has a colon in the tag name and no closing tag | Added `_CALL_TAG_RE` + `_CALL_TAG_ARG_RE` regexes and Fallback 2 in LM Studio text processing: matches `<call:name(...)>`, parses `key='value'` args, appends to `tool_calls` |
| Page-triggered agents (`idle_wakeup_seconds=0`) start working immediately on restart, ignoring token protocol | Two causes: (1) `_current_goal = prior_goal` bypassed the `not self._current_goal` gate; (2) `_wakeup_loop` fires on every 1s tick when `wakeup_s == 0` because `remaining = 0 - elapsed` is always negative | Fix both in `brain.py`: (1) set `_current_goal = ""` when `idle_wakeup_seconds == 0`; (2) add `if wakeup_s == 0: return` at the top of `_wakeup_loop` |
| Token-passing idle agents fire LLM cycles on every server output line despite `idle_wakeup_seconds = 0` | `pending_llm = True` was set unconditionally for all server text; wakeup loop guard only blocked the periodic timer | Added page-triggered mode in `brain.py`: when `idle_wakeup_seconds == 0`, only set `pending_llm = True` when text contains `"pages,"` (the token delivery signal) |
| Agent emits text `DONE:` repeatedly after plan exhausted; never pages successor; LLM cycles stop permanently | Guard `not (self._plan_exhausted and not self._current_goal)` fired when text `DONE:` cleared `_current_goal`, before the token page was sent | Added `_session_done` flag (set only by `done()` tool call, not text DONE:); changed guard to `not self._session_done`; updated plan-exhausted memory summary to say "page your successor, then call done()" |
| All four agents fire LLM cycles simultaneously, exhausting GPU KV cache | 4 concurrent large-prompt requests (~11–13k tokens each) saturate KV memory | Use `idle_wakeup_seconds = 0` in settings.toml for all non-Mason agents; move token protocol to baseline.md; each agent begins work only after seeing `<predecessor> pages, "Token:` |
| `@realm $room` output never appears in agent context; agent hangs waiting | Celery verb `print()` output arrives after the PREFIX/SUFFIX window and is never captured | Inject the room list via the tmux operator interface; note in SOUL.md that the agent should NOT wait for server output after `@realm` |
| Agent emits `PLAN:` as bullet points or numbered list; `_current_plan` stays empty; agent re-calls `@realm $room` mid-traversal | `_PLAN_RE` only matches `PLAN: item1 \| item2` on one line; multi-line/bullet format silently fails, so the LLM never sees "Remaining plan:" in context | Fix SOUL.md: require pipe-separated single-line format `PLAN: #6 \| #19 \| #26 \| ...` with bold warning against bullets; add "Never call `@realm $room` again after initial discovery" |
| `@create "X"` creates objects owned by Wizard; agent then can't `set_property` or `@obvious` them | `at_create.py` calls `create(name)` which defaults `owner=context.caller`; verb owned by Wizard so `context.caller` = Wizard | Fix `at_create.py`: pass `owner=context.player`; reload with `@reload @create on $player` |
| `say "message"` appears as "Wizard: message" to others; speaker sees "You: message" attributed to Wizard | `say.py` used `context.caller` for the `tell` and the name; verb on `$room` is Wizard-owned so `context.caller` = Wizard | Fix `say.py`: replace both `context.caller` with `context.player`; reload with `@reload say on $room` |
| After `@create`, agent loops creating duplicates on each PermissionError | Agent sees `PermissionError: #N did not accept #M` and treats it as total failure; object WAS created and is in inventory | Add to SOUL.patch.md: PermissionError after `@create` is not a failure — use `move_object({'destination': 'here', 'obj': '#M'})`. Root cause fixed by `owner=context.player` in `at_create.py` |
| After DB reset, SOUL.patch.md entries reference stale object IDs (#N) from prior sessions | DB reset reassigns all PKs; old patch entries become wrong | Before restarting after a DB reset: purge `logs/` and `builds/`, then review SOUL.patch.md for `#N` references and remove them |
| After DB reset, `builds/traversal_plan.txt` has stale room IDs from prior session | `_load_traversal_plan()` runs after `_load_latest_build_plan()` if no yaml found; loads stale plan; agent surveys old rooms and calls done instantly | Before restarting after a DB reset: clear `builds/traversal_plan.txt` for all agents (`> extras/agents/$a/builds/traversal_plan.txt`) in addition to deleting `builds/*.yaml` |
| Foreman resumes with stale prior goal ("Monitor rolling window for X done") after DB reset | `_read_prior_session()` extracts last goal from prior log; for Foreman (`idle_wakeup_seconds > 0`) this is loaded as `_current_goal`; Foreman waits for a done page that will never arrive | Inject operator goal into Foreman pane immediately after startup: "Fresh session after DB reset. Ignore prior goals. Start the chain now: page Mason to begin." |
| Worker agents see `They pages, "Token: Foreman start."` but SOUL.md says to match `Foreman pages, "Token:` — token is missed | `page.py` substitutes `player.psc` ("They") for the sender's name when the sender's name appears in the message body (e.g., "Token: Foreman start." contains "Foreman") | Update worker SOUL.md Token Protocol: match any `pages, "Token:` regardless of sender prefix; note pronoun substitution behavior |
| `@reload verb on $obj` produces no output | `at_reload.py` is intentionally silent on success | Absence of output = success. Use `MooSSH` with `phil`/`qw12er34`: `moo.run('@reload verb on $obj')` — empty string back is correct |
| Agent calls `tunnel` as a tool and gets `[Tool] Unknown tool 'tunnel' — skipping.`; return exits never wired | `@tunnel` was documented as a SCRIPT: command only; LM Studio model emits it as a bare tool call, which brain.py skips if the name is not in the registry | Add `tunnel` to `BUILDER_TOOLS` in `tools.py` with `_tunnel()` → `@tunnel {direction} to {destination}`; update SOUL.md to list `tunnel` under `## Tools` and remove the non-tool-command section |
| `describe(target="here", text="...")` sent verbatim to MOO server → `Huh?` | Single-line LLM fallback in `_llm_cycle()` took the bare tool-call text and dispatched it without trying `parse_tool_line()` | Fix the single-line fallback path (lines ~729–744 of `brain.py`) to call `parse_tool_line(candidate, known_names=tool_names)` before sending; translate via `spec.translate()` if it matches |
| Agent calls `describe` before `go` after `dig`; origin room description overwritten with new room's text | `describe(target="here")` writes to the current room; if the agent hasn't navigated yet, it overwrites the origin | Add to SOUL.md `## Common Pitfalls` and build sequence: "Never call `describe` before `go`. You must be inside the new room before describing it." |
| Model emits `<action>go north</action>` → `Huh?` | LM Studio model wraps commands in XML-style tags; brain dispatches the raw tagged text | Added `re.sub(r"^<\w+>(.*)</\w+>$", r"\1", line.strip())` to the line-processing loop in `_llm_cycle()` alongside the existing bold-marker strip |
| `[server] Global output suffix set to:` shows empty value in log/TUI | Suffix token in server's confirmation message is consumed by the delimiter parser; the value never reaches the log | Store `on_output` as `self._on_output` in `MooConnection.__init__`; call it with the prefix and suffix strings immediately after `setup_delimiters()`, before suppression is enabled |
| Agent accounts (Mason/Tinker/Joiner/Harbinger) pollute test assertions by receiving `tell()` messages from the lab | Agents bootstrapped with `location=lab` are in the lab during tests; movement and drop verbs notify all occupants | Set `location=None` for all agent objects in `default.py`; add `player/confunc.py` to move locationless players to "The Laboratory" on connect |
| LLM writes multi-line text in `page` tool `message` arg; second line dispatched as raw MOO command → "Huh?" | MOO processes each newline as a separate command; if LLM includes `\nPLAN: ...` in the message, the `PLAN:` line is sent to the server | Strip newlines from `message` in `_page()` in `tools.py`: `message = args.get("message", "").replace("\n", " ").strip()` |
| `@obvious #N` on a room → `PermissionError` | `obvious` is an attribute on objects, not rooms — it is silently ignored on rooms even if it could be set | Add to relevant SOUL.md files: never call `make_obvious` on a room; only call it on objects (`$thing`, `$furniture`, `$container`, NPCs) that the agent itself created |
| LLM emits multiple `[Done] Built Room X` thoughts at the same timestamp before commands execute; token page carries only the rooms actually tracked by `_rooms_built` | LLM plans the full build sequence speculatively in one thought batch, emitting Done markers before the corresponding tool calls run; `_rooms_built` correctly reflects only actual server responses | No brain.py fix needed — `_rooms_built` is accurate. Root cause is LLM over-planning; SOUL.md should reinforce "emit `PLAN:` and `done()` only after seeing server confirmation for each room" |
| Foreman relays to wrong agent (e.g. "Token relayed to tinker." after Tinker done) or skips an agent in the chain | Foreman's LLM confuses "who I just relayed from" with "who I should relay to next"; rolling window shows last relay target, model pattern-matches | Fixed: add `token_chain = ["mason","tinker","joiner","harbinger","stocker"]` to Foreman's `[agent]` settings.toml — brain.py auto-relays deterministically without LLM inference |
| Worker "done" pages carry a single-room `Rooms: #N` list that overwrites Foreman's full room plan | brain.py injected `_current_plan` (e.g. `["#128"]` = last room visited) into the done page; Foreman stored that truncated list and passed it forward to all subsequent agents | Fixed in brain.py: (1) don't inject room list when paging Foreman (`target.lower() != "foreman"` guard); (2) only update `_current_plan` from an incoming page if the new list is at least as large as the current one |
| Mason loads stale build YAML on restart, immediately pages Foreman done without building new rooms | `_load_latest_build_plan()` at startup populates `_current_plan` from the previous session's YAML; `_save_build_plan()` guard rejects the new BUILD_PLAN as a duplicate; LLM concludes plan is complete | Fixed in brain.py: `_current_plan = []` is cleared in the token-reset path so Mason starts fresh; also BUILD_PLAN allowed to override when `_current_plan` contains only room IDs (all values start with `#`) |
| Agent sets GOAL: with no action taken; stalls forever with `idle_wakeup_seconds = 0` | Local Gemma model often splits goal-setting and action into two LLM responses; second response never fires without an external trigger | Fixed in brain.py: `_goal_only_count` counter — when a cycle sets a goal but queues no commands, up to 3 follow-up cycles are auto-scheduled; counter resets on real server output |
| `@create X from "$thing"` returns "Created #133 / Transmuted #133 to #13 (Generic Thing)"; Tinker subsequently uses `#13` for `@obvious`, `write_verb`, etc. | LLM sees `#13` in the transmute line and treats it as the new object's ID; `#13` is the parent class ($thing), not the created object | Add to Tinker's SOUL.md `## Common Pitfalls`: "When `@create` returns `Created #N … Transmuted #N to #M`, the object ID is `#N`. `#M` is the parent class — never use it for subsequent operations." |
| `create_object(name="...", parent="...")` sent as raw text → "Huh?"; agent loops creating duplicates | LLM outputs `create_object(...)` as prose in a multi-line response; brain.py single-line fallback only handles it when the entire response is one line | Remind via operator injection: "Use `@create \"name\" from \"$thing\"` as a COMMAND — `create_object` is a tool call and must appear in the JSON tool_calls block, not as text." |
| Agent calls `done()` in the same tool batch as `burrow`/`describe`/`teleport`/`@create`; Foreman stall-pages but agent is silent | `_session_done = True` after `done()`; page-triggered agent ignores all subsequent pages including stall alerts. `done()` does not automatically page Foreman — the explicit `page()` call was skipped | Inject operator goal into the stalled pane: "You called done() without page() first. Page foreman now: page(target=\"foreman\", message=\"Token: X done.\")". Then add "Never batch done() with other tool calls" to that agent's SOUL.md ## Common Pitfalls. |
| Worker agent continues firing LLM cycles and creating objects after calling `done()` (e.g. Harbinger creating 10+ unauthorized NPCs post-done) | `_session_done = True` blocks the `idle_wakeup_seconds > 0` timer wakeup but not the queued-output wakeup; `enqueue_output()` lines arriving after `done()` (server confirmations, page echoes) re-trigger the loop | Fix in `brain.py`: in `run()` output-processing path, skip `pending_llm = True` when `self._session_done` is already set. Both wakeup paths must check `_session_done`. |
| Agent crashes or is killed before calling `done()`; fresh restart receives no token; work halts | Fresh agent waits silently with `idle_wakeup_seconds = 0`; token is lost unless Foreman re-pages | Expected recovery: Foreman's stall timer will page the agent ("Stall alert: you hold the token") within its stall interval. Fresh agent treats this as the token and resumes. No manual intervention needed unless stall interval is disabled. Note: Foreman's "stall monitor" is a misnomer — it's a plain timer, not a state observer. It fires on a fixed interval regardless of whether the target is actually stalled. |
| Mason expansion pass creates rooms with duplicate names — e.g. two rooms both named "The Laboratory" | Mason calls `burrow()` without first checking whether a room with that name already exists in `rooms()` output; expansion SOUL.md does not require a name-uniqueness check | Add to Mason's SOUL.md `## Expansion Pass`: before calling `burrow()` for any new room, scan `rooms()` output for the intended name. If it exists, choose a different name. |
| Stocker repeatedly puts `move_object(obj="#N" destination="#M")` inside a `SCRIPT:` block → "There is no 'obj=\"#N\" destination=\"#M\"' here." | Rule already exists in SOUL.md and baseline.md; Stocker still reverts to SCRIPT form after a tool error causes context reset mid-session | Strengthen in Stocker's SOUL.md `## Common Pitfalls`: add a CRITICAL block with explicit wrong/right example. Also add `move_object` to Stocker's `## Tools` list so it appears as a named tool in the system prompt. |

| Soul name shows "(unnamed)" on connect | SOUL.md top-level heading is `# AgentName` instead of a `# Name` section | soul.py sets `soul.name` only when `h1 == "name"` — use `# Name\n\nAgentName` (H1 "Name", body text is the name) not `# Cliff` as the H1 |
| Agent sends `@mail once` → Usage error | Mission text said "Run `@mail` once" — LLM sent it literally | Remove "once" (and other adverbs) from mission COMMAND examples; the LLM reads prose modifiers as part of the command |
| `@reply N "body"` → "Usage: @reply N  (N is the message number)" | Missing `with` keyword — correct form is `@reply N with "body"` | Added `"Usage:"` to `_ERROR_PREFIXES`; add a `## Verb Mapping` entry to SOUL.patch.md: `reply to message -> @reply 1 with "body"` |
| Timer-based agent wakes up each cycle, outputs `[goal] done`, does nothing | Stale prior-session goal context: LLM reads "I already completed my task" and short-circuits | Kill and restart; fresh context breaks the loop. If persistent, set `idle_wakeup_seconds = 0` and use page-triggered mode instead |
| `say "text"` succeeds (player sees output) but produces `[server_error]` afterwards; reply arrives next cycle | An NPC in the room errors on `tell` because it has no active SSH connection; `say` calls `announce_all_but()` which calls `tell` on every object including NPCs | Expected behavior; not a bug. Agents recover in the next LLM cycle. To eliminate: move agents to a room with no NPCs |
| Log freezes at `[action] @mail` after rapidly restarting the same agent | Stale SSH connection — server sent PREFIX/SUFFIX OK but subsequent commands hang | `agentmux --group <name> restart --restart-shell` — clears the shell container and all agents |
| Single-agent rapid restarts cause subsequent commands to hang silently | Each `agentmux restart <agent>` kills the process but the SSH session may persist on the server side; the new connection shares the same socket until the shell container recycles it | If a single agent's log freezes mid-command after restart, do a full group restart with `--restart-shell` to clear all connections |
| Timer-based agent skips `@mail` (or other mandatory first command), jumps straight to mid-cycle action on restart | `_read_prior_session()` injects prior session goal + summary; LLM resumes from stale mid-cycle context and skips the first step | Fixed in `cli.py`: when `config.agent.idle_wakeup_seconds > 0`, suppress both `prior_summary` and `prior_goal` — timer-based agents always start fresh |
| Timer-based agent recaps prior cycle ("Replied to X") every wakeup without taking action | Rolling window from previous cycle persists into next wakeup; LLM sees its own prior output and concludes task is done | Fixed in `brain.py` `_wakeup_loop`: clear `self._window` and `self._current_goal` before each timer-fired LLM cycle — every wakeup starts with an empty window |
| Timer-based agent sends `"body"` (or other placeholder) as reply content | Verb mapping example `reply to message -> @reply 1 with "body text here"` used literally | Update verb mapping to `@reply N with "Dear X, [write full letter here — never use placeholder text]"`; include the NEVER note explicitly |
| Timer-based agent sends two replies per wakeup (replies to message #1, then re-checks @mail and replies to #2) | After replying, LLM sees remaining unread messages and continues instead of stopping | Step 2 in Mission must say "Then go directly to step 5. Do not re-check the mailbox. Do not read other unread messages." |
| Cleanup deletes the message just replied to instead of the oldest one | Step 2 says "delete `<highest_n>`" but LLM conflates "the message I just handled" with "the one to delete" | In Mission step 2: explicitly say "the LARGEST number at the bottom of the listing — never the one you just replied to" |
| Agent runs `@mail` repeatedly (5+ times) when there are 0 unread messages | "Read every unread message" instruction from step 2 bleeds into step 4 — LLM loops trying to read when nothing is unread | In step 4 (no unread): explicitly say "do NOT read any messages" before the delete instruction |
| Agent deletes multiple messages per cycle (e.g. deletes #15, #14, #13 in one session) | No explicit upper bound on cleanup; LLM interprets "clean up" as clearing the whole backlog | Add patch note: "Only ONE `@mail delete` per wakeup. Never delete multiple messages in the same session." |
| Mailbox count stays permanently high despite cleanup running each cycle | 1:1 message exchange rate (each reply generates a new inbound) exactly cancels the one-per-cycle delete; backlog from a buggy period never drains | Expected steady state when exchange rate ≥ cleanup rate. To drain, the agent must delete more than one per cycle during backlog periods. |
| `Player.MultipleObjectsReturned` in celery logs; `tell.py` crashes when sending to a player object | `is_connected()` in `object.py` uses `Player.objects.get(avatar=self)` — fails when two User accounts share the same avatar (e.g. `phil` and `wizard` both pointing to Wizard #5) | Changed to `Player.objects.filter(avatar=self)` + `any(cache.get(...))` — returns True if any associated user has an active connection |
| `moo_init --sync` appears to hang at `Syncing bootstrap 'default' against existing database...` | Not hanging — the command only prints one line on success, then exits silently | Wait for the shell prompt to return; do not kill the process. Verify with `echo $?` — exit 0 means success |
| First agent in `TOKEN_CHAIN` is not connected when Foreman starts; token dispatch is silently lost | Foreman's `Connected` handler auto-dispatches the token once; if the target isn't up yet, the page returns `<Agent> is not currently logged in.` | Already handled in `brain.py` (lines ~421–432): Foreman clears `_token_dispatched_at` on "not currently logged in", then re-pages when it sees `<Agent> has connected.` No action needed — just confirm the re-page fires after the target connects. Documented in Foreman's SOUL.md under "How the Chain Works" so the LLM understands the flow if invoked. |
| Foreman's auto re-page at connect never fires; chain stuck after initial "X is not currently logged in" | The room where agents live (e.g. The Agency) has a custom silent `confunc` that skips `announce_all_but`, so `<Name> has connected.` broadcasts never reach Foreman's buffer. Without those broadcasts, the handler at [brain.py:426-432](moo/agent/brain.py#L426) has nothing to match on. | Remove any custom `confunc` from the room agents live in so it falls back to `$room.confunc`, which calls `this.announce_all_but(player, f"{player} has connected.")`. Delete the DB verb row too (`Verb.objects.filter(origin=agency, names__name='confunc').delete()`) — removing from the bootstrap file alone doesn't remove existing rows. |
| `[Config] Unknown tool names ignored: ['grant_write']` appears at agent startup | Agent's SOUL.md lists `grant_write` under `## Tools`, but `grant_write` is a MOO verb not an agent-side tool in `BUILDER_TOOLS` | Non-fatal — agents can still invoke `grant_write #N` as a MOO COMMAND. To silence the warning, remove `grant_write` from `## Tools` in SOUL.md (keep it as a COMMAND example elsewhere), or add a ToolSpec to `BUILDER_TOOLS` in `tools.py` if the LLM benefits from structured tool-call form |
| LLM emits `<survey target="#283">` as a raw thought line; no tool call dispatched; agent goes silent until external nudge | Self-closing XML tool-call form with a `target=` attribute — similar shape to the `<call:name(args)>` pattern but not matched by `_CALL_TAG_RE` (which expects a colon in the tag name). Model treats it as inline markup and the fallback logs it as `[thought]`. Only recovers when Foreman's stall timer pages the agent, which re-prompts the LLM and it retries with a proper tool call. | Add a new fallback in `brain.py` LM Studio text processing: match `<\w+\s+\w+="[^"]*"\s*/?>` (a self-closing tag with one or more attributes), treat the tag name as the tool name, each attribute as a kwarg. Parallel to Fallback 2 (`<call:name(...)>`) and Fallback 3 (XML tool_call blocks). Until fixed, recovery is automatic via Foreman's timer-based stall nudge — no operator intervention needed. |
| Agent hits `[LLM error] Error code: 400 - Failed to parse input at pos 0: <\|channel>thought\n...` and retry-loops forever | Harmony-format chat-template token leaked from a prior LLM response into `_memory_summary` (via `_summarize_window`) or the rolling window. On the next request, LM Studio's template expander sees `<\|channel>` at position 0 of the rendered prompt and rejects it as an invalid special token. Every retry re-sends the poisoned summary, reproducing the same 400. Only `<\|endoftext\|>` was being stripped in `brain.py` `_call_llm`; other Harmony markers (`<\|channel\|>`, `<\|channel>`, `<\|im_start\|>`, `<\|start\|>`, `<\|message\|>`, `<\|end\|>`) all pass through. | Added `_SPECIAL_TOKEN_RE = re.compile(r"<\\\|[A-Za-z_][A-Za-z0-9_]*\\\|?>")` in `brain.py`. Apply `.sub("", text)` to the LLM response text on both the LM Studio path (line 751) and the Anthropic/Bedrock path (line 779). Also scrub in `cli.py` `_read_prior_session` when building the prior-session summary from log files — a poisoned log line must not re-poison the next session on restart. |
| Agent repeatedly emits `[Tool] Unknown tool 'exits' — skipping.` but the actual work gets blocked; no recovery | Agent's SOUL.md claimed `survey()` output contains `[exit #N]` IDs (it does not — only destination room IDs appear). LLM tries to follow the protocol step, can't find the advertised IDs, and hallucinates a nonexistent `exits(target="#N")` tool to fetch them. `get_tool()` returns `None`, brain logs `[Tool] Unknown tool 'exits' — skipping.`, and the agent re-plans the same failing step on the next cycle. | Fix the SOUL.md instruction to describe the actual path: `survey()` only confirms exits exist; emit `@show #<room_id>` and read the `exits:` property (format: `{"o#NNN": "<direction> from ..."}` — the ID after `o` is the exit object ID). Add an explicit "Never invent or call an `exits()` tool" line so the LLM doesn't repeat the hallucination. General principle: any time a SOUL.md step claims output-format knowledge, verify by reading a real log before shipping — an LLM instructed to "note the [exit #N] ID from survey output" will fabricate a tool to extract what it was told would be there. |

## Principles

- **One fix per problem, minimum surface area.** Don't rewrite sections when a sentence will do.
- **Concrete beats abstract.** "Never use underscores in quoted names" is better than "use correct name formatting".
- **Test by reading the next log.** If the pattern reappears unchanged, the fix didn't reach the LLM — check that the section is under a recognized heading and is being included in the system prompt.
- **brain.py fixes take effect immediately on restart.** SOUL.md and baseline.md fixes require the soul to be reloaded, which also happens on restart.
- **Always audit `SOUL.patch.md` before restarting.** One wrong lesson injected into every session does more damage than a bad SOUL.md rule. Stale entries, wrong facts, and misplaced section items all compound silently. Clear the file if it's corrupt — it will rebuild from real observations.
