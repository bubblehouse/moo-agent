---
name: agent-trainer
description: Iteratively tune a running moo-agent by reading session logs, identifying behavioral errors or gaps, updating SOUL.md / baseline.md / brain.py, and restarting. Use when the user asks to improve agent behavior, fix agent errors, tune an agent, or review agent logs.
compatibility: DjangoMOO project (django-moo). Requires the moo-agent CLI and a running agent config under extras/agents/.
---

# Agent Trainer Skill

You are tuning a running moo-agent by reading its session logs, diagnosing errors, updating the right files, and restarting. This is an iterative loop — each restart should fix at least one class of error and introduce no regressions.

## The Tradesmen

The current agent roster is five specialized agents. Foreman orchestrates the token
chain; the four workers execute in the order Foreman dispatches.

| Agent dir | Name | SSH user | Player class | Domain |
|-----------|------|----------|--------------|--------|
| `foreman/` | Foreman | `foreman` | $player | Token orchestration, stall detection |
| `mason/` | Mason | `mason` | $player | Rooms, exits, descriptions |
| `tinker/` | Tinker | `tinker` | $programmer | Interactive `$thing` objects, secret exits via verbs |
| `joiner/` | Joiner | `joiner` | $player | `$furniture` and `$container` objects |
| `harbinger/` | Harbinger | `harbinger` | $programmer | One NPC per room |

**Token chain:** Foreman → Mason → Foreman → Tinker → Foreman → Joiner → Foreman →
Harbinger → Foreman → (loop). Start Foreman first; it pages Mason automatically.
Tinker and Harbinger need `$programmer` accounts because they use `@edit verb` and `@eval`.

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

**Always create a cron job immediately after restarting** so stalls are caught automatically:

```
CronCreate every 5 minutes:
  Check tail -5 of the latest log.
  If the last entry is more than 8 minutes old, kill and restart the agent.
```

The cron job is session-only — recreate it whenever you start a new conversation with an agent running.

Then verify the first cycle manually:

- The agent connected and loaded its soul
- It completed at least one LLM cycle without an error
- Any previously failing pattern now produces a `[server_error]` and returns control to the LLM

Repeat from Step 1.

## Running All Five Agents with tmux

This creates a 2×3 grid session with one pane per agent. Start Foreman first —
it pages Mason automatically to begin the chain.

```bash
# Create the session and start Foreman in the first pane
tmux new-session -d -s tradesmen
tmux send-keys -t tradesmen:0.0 "uv run moo-agent run extras/agents/foreman" Enter

# Split right → Tinker (pane 1)
tmux split-window -h -t tradesmen:0.0
tmux send-keys -t tradesmen:0.1 "uv run moo-agent run extras/agents/tinker" Enter

# Split Foreman's pane vertically → Mason (pane 2, middle-left)
tmux split-window -v -t tradesmen:0.0
tmux send-keys -t tradesmen:0.2 "uv run moo-agent run extras/agents/mason" Enter

# Split Tinker's pane vertically → Joiner (pane 3, middle-right)
tmux split-window -v -t tradesmen:0.1
tmux send-keys -t tradesmen:0.3 "uv run moo-agent run extras/agents/joiner" Enter

# Split Mason's pane vertically → Harbinger (pane 4, bottom-left)
tmux split-window -v -t tradesmen:0.2
tmux send-keys -t tradesmen:0.4 "uv run moo-agent run extras/agents/harbinger" Enter

# Attach
tmux attach -t tradesmen
```

Layout result:

```
┌──────────────┬──────────────┐
│ foreman      │ tinker       │
├──────────────┼──────────────┤
│ mason        │ joiner       │
├──────────────┤              │
│ harbinger    │              │
└──────────────┴──────────────┘
```

Pane index mapping: 0=Foreman, 1=Tinker, 2=Mason, 3=Joiner, 4=Harbinger.

Each pane runs the full TUI (prompt_toolkit). The TUI adapts to pane size.

To kill the session: `tmux kill-session -t tradesmen`

To restart a single agent after editing its SOUL.md, send `Ctrl-C` to that pane
and rerun:

```bash
# Send Ctrl-C to Mason's pane (pane 2), then restart
tmux send-keys -t tradesmen:0.2 C-c "" Enter
tmux send-keys -t tradesmen:0.2 "uv run moo-agent run extras/agents/mason" Enter
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
for a in foreman mason tinker joiner harbinger; do
  echo "=== $a ==="; grep server_error extras/agents/$a/logs/$(ls -t extras/agents/$a/logs/ | head -1)
done
```

### Iterate through all five logs in sequence

```bash
for a in foreman mason tinker joiner harbinger; do
  echo; echo "=== $a — last 20 lines ==="; tail -20 extras/agents/$a/logs/$(ls -t extras/agents/$a/logs/ | head -1)
done
```

### Type an instruction into a specific agent's TUI

Each TUI has an input field at the bottom. From outside tmux:

```bash
# Send a goal instruction to Harbinger (pane 4)
tmux send-keys -t tradesmen:0.4 "visit all rooms and report how many NPCs you placed" Enter
```

The instruction appears as `[operator]` in the log and is injected into the
agent's next LLM cycle.

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
| Agent spends many cycles inspecting exits/rooms without building | World-state confusion spiral after navigation failures — often triggered by recovering from "There is already an exit in that direction" error during Expansion Pass | Not reliably self-correcting; after 3+ consecutive `@show here` cycles with no navigation, kill and restart. Fresh context breaks the spiral. |
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
| Agent log shows "Connecting to localhost:8022…" for 45+ seconds, never connects | Stale SSH connections from rapid kill/restart not cleaned up by the shell service | `docker restart django-moo-shell-1`; wait 5s; then restart the agent in its tmux pane. Also restart any other agents whose logs stopped receiving server events. |
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

## Principles

- **One fix per problem, minimum surface area.** Don't rewrite sections when a sentence will do.
- **Concrete beats abstract.** "Never use underscores in quoted names" is better than "use correct name formatting".
- **Test by reading the next log.** If the pattern reappears unchanged, the fix didn't reach the LLM — check that the section is under a recognized heading and is being included in the system prompt.
- **brain.py fixes take effect immediately on restart.** SOUL.md and baseline.md fixes require the soul to be reloaded, which also happens on restart.
- **Always audit `SOUL.patch.md` before restarting.** One wrong lesson injected into every session does more damage than a bad SOUL.md rule. Stale entries, wrong facts, and misplaced section items all compound silently. Clear the file if it's corrupt — it will rebuild from real observations.
