# Error Pattern Catalog

Known agent error patterns, their root causes, and fixes applied.

## Undetected game errors

These are server responses that look like errors to a human but weren't caught by `_ERROR_PREFIXES`. The agent continued as if the command succeeded, often hallucinating that it had worked.

### "There is already an exit in that direction."

**Trigger:** Agent runs `@dig <dir> to "New Room"` when an exit already exists in that direction.

**Why it matters:** `@dig` silently fails — the room is never created. But the script continues, and subsequent commands try to `@move` objects to "New Room" (which doesn't exist), causing cascading "There is no X here" failures.

**Fix:** Added `"There is already an exit"` to `_ERROR_PREFIXES` in `brain.py`. Now the script halts and returns control to the LLM when this happens.

### "There is no X here."

**Trigger:** Name-based object lookup when the object is not in the agent's current location or inventory.

**Common cause:** Agent creates an object (puts it in inventory), moves it to a room with `@move`, then tries to `@describe "object name"` — but the object is now in the room, not in inventory. Or: agent uses underscores in the name (`"heavy_power_cable"` instead of `"heavy power cable"`).

**Fix:** Added `"There is no "` to `_ERROR_PREFIXES`. Also added to `baseline.md`:

- #N reference rule: use `#N` for all subsequent operations after `@create`
- Explicit underscore warning: never use underscores in quoted names

### "Huh? I don't understand that command."

**Trigger:** Player types a command for which no verb exists anywhere in the search order.

**Path:** Parser → `NoSuchVerbError` → `$room.huh` → `$room.huh2` → `player.tell("Huh? I don't understand that command.")`. Delivered via `tell()` (Kombu), wrapped in OUTPUTPREFIX/OUTPUTSUFFIX, visible to agent.

**Why it wasn't caught:** The prefix check is `startswith("I don't understand")` — but the actual string starts with `"Huh?"`. The prefix must match the beginning of the line exactly.

**Fix:** Added `"Huh?"` to `_ERROR_PREFIXES`.

**Agent behavior before fix:** Agent tried `speak Arthur` (no `speak` verb existed), got no visible error in the log, continued as if the NPC had responded. The Celery task returned `[]` (correct — `huh2` uses `tell()`, not `print()`).

---

## Guidance gaps

These are cases where the agent had no error but made a wrong choice because the rules weren't explicit enough.

### Underscore in quoted names

**Pattern:** Agent generates `@describe "sample_box"` instead of `@describe "sample box"`.

**Why it happens:** The model interpolates variable-name-style identifiers when constructing command strings inside a chain of operations.

**Fix:** Added to `baseline.md` under `#N Object References`:
> Never use underscores in quoted object names. Object names use spaces, not underscores. `"heavy_power_cable"` will always fail — use `"heavy power cable"`.

### Multiple `@create` in one SCRIPT

**Pattern:** Agent queues 9 commands including 3 `@create` calls in a single SCRIPT. Later commands reference earlier creates by name — which works as long as the names are correct — but violates the CRITICAL baseline rule about `@create` being a standalone COMMAND.

**Why it happens:** The model optimizes for fewer LLM cycles and batches everything together.

**Fix:** Rule already existed as CRITICAL in `baseline.md`. Reinforced by adding underscore warning immediately after (the underscore errors only occur when names are used inside scripts, so proximity helps).

### Wrong NPC interaction pattern (`speak`)

**Pattern:** Agent attempts `speak Arthur` expecting dialogue, but `speak` doesn't exist as a verb.

**Root cause:** Agent assumed a `speak` verb would be built-in, similar to how `say` is built-in.

**Fix:** Added `## NPCs` section to agent `SOUL.md` explaining that:

- NPCs respond to `say` via a `tell` verb override, not a custom `speak` verb
- `say` calls `obj.tell()` on every object in the room — overriding `tell` on the NPC is how it "hears"
- Exact code pattern for the `tell` override provided
- `speak`, `talk`, `greet` do not exist

### Room spelling inconsistency

**Pattern:** Agent digs `"The Armory"`, then tries to move to `"The Armoury"` (added a 'u').

**Fix:** Added to `baseline.md`:
> Use exact spelling when referencing rooms. If you dug `"The Armory"`, you must reference it as `"The Armory"` — not `"The Armoury"`, not `"Armory"`. Copy the exact string from your `@dig` command.

### Room renamed instead of dug

**Pattern:** Agent tries `@dig north to "New Room"` but north already has an exit. Goes north, finds itself in The Laboratory. Renames The Laboratory to "New Room" via `@eval` instead of picking a different direction.

**Root cause:** When a dig fails because the direction is taken, the agent didn't check where `go north` actually led before deciding what to do.

**Fix:** Added to `baseline.md`:
> Check existing exits before digging. Run `@show here` and check the exits list. If the direction is occupied, pick a different direction or skip the dig entirely.

### Agent skips verb testing

**Pattern:** Agent creates a verb with `@edit verb X on #N with "..."` then immediately advances to the next goal without calling the verb. Broken verbs go undetected.

**Root cause:** The verb testing rule existed but read as a guideline rather than a hard requirement.

**Fix:** Rewrote `## Verb Testing` in `baseline.md` with **REQUIRED** framing and restructured the example to put the test call in the same `SCRIPT:` as the `@edit` — making it structurally inseparable from creation.

### `obj.name` assignment not persisted

**Pattern:** Agent runs `@eval obj = lookup(79); obj.name = "New Name"` but the rename doesn't stick. On the next `@show`, the old name is still there.

**Root cause:** `name` is a Django model field (`CharField`), not a MOO property. Python attribute assignment only mutates the in-memory instance. Without `obj.save()`, the change is lost when the Celery task ends.

**Fix:** Added `## 'name' is a Model Field — Always Call obj.save()` to `baseline.md`. Also applies to `obvious`, `owner`, and any other intrinsic model field.

### Shebang `--dspec` silently ignored

**Pattern:** Agent writes `#!moo verb switch --dspec any` in verb code, but the verb ends up with `direct_object='none'` in the database. Calling `switch monitors` then fails with "The verb 'switch' doesn't take a direct object."

**Root cause:** `parse_shebang()` requires `--on <parent>` to be present — it's a required argument. Without it, `parse_shebang()` returns `None` and `at_edit.py` falls back to `dspec='none'`. The shebang line is silently ignored rather than raising an error.

**Diagnosis:** Check the verb in the database: `docker exec django-moo-webapp-1 bin/python src/manage.py shell -c "from moo.core.models import Object; v = Object.objects.get(pk=N).verbs.first(); print(v.direct_object, v.code)"`. If `direct_object='none'` despite the shebang, `--on` is missing.

**Fix:** Added to `baseline.md` under `## Verb Dispatch`:
> The shebang requires `--on` to be parsed. Always include `--on $thing` (or the object's parent class) as a placeholder — the `--on` value doesn't affect where the verb is created.
> Correct: `#!moo verb switch --on $thing --dspec any`

### `@describe "Room Name"` fails after rename

**Pattern:** Agent renames a room from "The Armory" to "The Surveillance Center" via `obj.name = ...; obj.save()`. Then in the same or next script, runs `@describe "The Surveillance Center" as "..."` — fails with "There is no 'The Surveillance Center' here."

**Root cause:** Name-based lookup via `@describe` uses the parser's local-area search (caller → inventory → location → dobj). After a rename, the room's name is updated but it's not "here" — the agent is standing inside it, so `@describe here` is the correct form.

**Fix:** Agent self-corrected to `@describe here as "..."`. Added to `baseline.md` as part of the "exact spelling" room guidance block — after renaming, always use `here` or `#N` to reference the current room.

### `import lookup` in `@eval`

**Pattern:** Agent writes `@eval "import lookup; print(lookup('X').name if lookup('X') else 'Not Found')"`. Fails with `Error: Restricted: lookup`.

**Root cause:** `lookup` is a function pre-injected into the `@eval` namespace, not a Python module. Also: `lookup()` raises `NoSuchObjectError` on miss — it never returns `None`, so a `None` check is always wrong.

**Fix:** Added to `baseline.md`:
> Never write `import` statements in `@eval` — all SDK names are injected directly. `import lookup` fails because `lookup` is a function, not a module.
> `lookup()` raises `NoSuchObjectError` on miss — use `try/except NoSuchObjectError`, not a None check.

### Investigation spiral after world-state confusion

**Pattern:** Agent gets confused about which rooms exist (e.g., after a series of name-mismatch failures). Instead of moving on, it issues `@realm $room`, then `@show #72`, `@show #74`, `@show #73`… cycling through exits one by one for many LLM rounds without making progress.

**Root cause:** Each failed navigation leaves the agent uncertain about the world map. The LLM tries to resolve the uncertainty by inspecting everything it can find, but each inspection produces more data without a clear decision point.

**Observation:** The agent did eventually self-terminate the spiral and move on. No code fix made; the behavior is slow but self-correcting. If it recurs badly, add SOUL.md guidance: cap investigation to 2 `@show` calls, then pick a fresh direction and build something new.

### DONE summary hallucination after failed command

**Pattern:** A SCRIPT fails partway through (e.g., `@move` returns "There is no X here"). The agent's DONE line still summarises the whole script as if it succeeded: "Populated The Armoury with a weapon rack and tactical gear." The next LLM cycle treats this as ground truth and continues building on a false premise.

**Root cause:** The DONE line is written by the LLM before seeing the server responses. When a script is interrupted by an error, the LLM reconstructs the summary from its own intent rather than the actual output.

**Observed consequence:** The false DONE summary feeds back into the next goal, causing the agent to reference objects/rooms that were never successfully created, leading to further errors.

**No fix applied yet.** Potential mitigation: require the LLM to check the last server response before writing DONE, or add a brain-level rule that suppresses DONE on error-interrupted scripts.

### Missing aliases and `@obvious`

**Pattern:** Agent creates objects, describes them, moves them — but never adds aliases or marks them obvious. Objects are effectively invisible and unlookupable by players.

**Fix:** Added `## Aliases` section to `baseline.md` and updated the build example to include `@obvious` and multiple `@alias` calls in the placement SCRIPT.

### Recursive `tell` on NPCs via `announce_all`

**Pattern:** Agent writes a `tell` verb override on an NPC that calls `this.location.announce_all(...)` to broadcast the NPC's response. The world freezes with a `RecursionError: maximum recursion depth exceeded` in Django's ORM.

**Root cause:** `announce_all` calls `tell` on every object in the room — including the NPC itself. `tell` fires again, calls `announce_all` again, infinite loop.

**Fix:** Use `announce_all_but(this, message)` instead. It skips the object passed as the first argument. Also fixed the NPC `tell` example in `SOUL.md` and added `## NPC 'tell' Overrides` to `baseline.md`.

### Verbs on objects inside containers are unreachable

**Pattern:** Agent places an interactive object (e.g. `coolant leak`) inside a container (e.g. `coolant reservoir`), adds a verb to it, then tests it — gets "I don't know how to do that." or "Huh?" repeatedly. Agent tries `@move me to "coolant reservoir"` (fails — can't teleport into a container) and hallucinates success.

**Root cause:** The parser searches: caller → inventory → location (room's direct contents) → dobj → pobj. Objects nested inside containers are not in the room's direct contents and will never match a verb dispatch.

**Fix:** Added to `baseline.md`: put interactive objects directly in the room, not inside containers. If a mechanic requires a container, put the verb on the container itself.

### `try/except` cannot be inlined with semicolons

**Pattern:** Agent writes a verb with `try: <stuff>; except Exception as e: print(e)` on a single line or across a `\n` boundary without proper indentation. Verb saves successfully but throws `SyntaxError` at runtime.

**Root cause:** Python `try/except` requires proper block structure. Semicolon-chaining doesn't create blocks. A `try:` clause on one line followed by `except:` on the next (without indentation) is a `SyntaxError`.

**Fix:** Added to `baseline.md`. Keep inline verb code simple — avoid `try/except` unless each block is on its own properly-indented `\n`-separated line.

### Malformed shebang now errors explicitly

**Pattern (historical):** Agent wrote `--dsppec` instead of `--dspec`. `parse_shebang()` caught the `SystemExit` from argparse and returned `None`. `at_edit.py` silently fell back to `direct_object='none'`. Verb saved with "Created verb X" but never dispatched correctly.

**Fix (server-side):** `at_edit.py` now detects a `#!moo verb` shebang that fails to parse and returns `"Error: malformed shebang — check --dspec/--ispec spelling and --on argument."` Brain catches this via `_ERROR_PREFIXES` and halts the script. No longer a silent failure.

### Missing `\n` after shebang line merges shebang with first import

**Pattern:** Agent writes `"#!moo verb foo --on #42 --dspec any\import random\n..."` — the `\n` after the shebang is missing, so the shebang and first import are joined: `#!moo verb foo --on #42 --dspec any\import random`. `shlex.split` sees the `\` before `i` as an escape sequence and raises `ValueError: No escaped character`. Server returns a full traceback starting with `"An error occurred"`.

**Why it recurs:** The model copies the `\n` separator for subsequent lines but omits it immediately after the shebang, treating the shebang as a comment that doesn't need its own line terminator.

**Fix:** Added `"An error occurred"` to `_ERROR_PREFIXES` in `brain.py` so the traceback halts the script. Added to `baseline.md`: the shebang line requires its own `\n` just like every other line — `"#!moo verb foo --on #42 --dspec any\nprint('hi')"`.

### `print(queryset)` causes `kombu.exceptions.EncodeError`

**Pattern:** Agent runs `@eval "print(context.player.location.contents.all())"`. Server returns a long `EncodeError` traceback: `Unserializable object ... of type QuerySet`.

**Root cause:** The Celery result backend can't serialize a Django QuerySet. `print()` receives the queryset object, which Kombu tries to serialize as the task result and fails.

**Fix:** Agent self-corrected immediately to `print([obj.name for obj in context.player.location.contents.all()])`. Added to guidance: always convert querysets to lists of names/IDs before printing.

### `lookup` not imported in verb code — NameError at runtime

**Pattern:** Agent writes a verb that calls `lookup("#418")` without importing it. The verb saves successfully ("Created verb X on #N"), but at runtime fails with `NameError: name 'lookup' is not defined`. Because the error is inside the verb's output (not the `@edit` command), it appears as a `[server]` line that the agent may not recognise as an error.

**Root cause:** Unlike `@eval`, verb code has no pre-injected names. Every SDK function must be imported explicitly at the top of the verb.

**Fix:** Added to `baseline.md` with a WRONG/RIGHT example:

```
WRONG: pump = lookup("#418")
RIGHT: from moo.sdk import lookup
       pump = lookup("#418")
```

Also applies to `context`, `write`, `create`, and all other SDK names.

**Recurrence:** Happened 3 times in a single session despite baseline guidance. The model knows the rule but forgets it when composing inter-object verbs that reference other objects by ID.

---

### `$note` in inventory intercepts `@edit verb` — silent wrong-object dispatch

**Pattern:** Agent runs `@edit verb foo on #N with "..."` and gets back "Text set on #M (note)" — the verb was set on a note object instead of the intended target. The agent sees "Text set" and treats it as success.

**Root cause:** `$note` (#13) has an `@edit` verb with `--dspec any`. When a note is in the wizard's inventory, it wins the verb dispatch (inventory is searched before dobj). The command is silently re-routed to the note.

**Detection:** Look for "Text set on #M (note)" where M is not the intended target.

**Workarounds:**

1. Move notes out of wizard inventory: `Object.objects.filter(pk=NOTE_PK).update(location_id=ROOM_PK)` via Django shell
2. Check wizard inventory: `@eval "print([str(o) for o in context.player.contents.all()])"`

**Prevention:** Added to `baseline.md` — if `@edit verb` returns "Text set" instead of "Created/Set verb", a note is intercepting. Move the note first.

---

### `obj.description = "..."` in `@eval` — silent no-op

**Pattern:** Agent runs `@eval "obj = lookup(412); obj.description = 'New text.'; obj.save(); print('Done')"`. Gets "Done" back and believes the description changed. On next `look` or `@show`, the description is unchanged.

**Root cause:** `description` is a MOO **Property** stored in the database, not a Django model field. Assigning to `obj.description` sets a transient Python attribute discarded when the Celery task ends.

**Fix:** Added to `baseline.md`:

```
WRONG: @eval "obj = lookup(412); obj.description = 'New text.'; obj.save()"
RIGHT: @eval "obj = lookup(412); obj.set_property('description', 'New text.'); print('Done')"
```

Use `set_property`/`get_property` for all MOO properties. Only `name`, `obvious`, `owner`, and `unique_name` are true model fields that `obj.save()` persists.

---

### Name collision — `@alias`/`@edit verb` lands on older object with same name

**Pattern:** Agent creates "control console" (#434), then runs `@alias "control console" as "panel"`. Server responds "Added alias 'panel' to #113 (control console)". The alias was added to an older object in a different room sharing the same name.

**Root cause:** Name-based lookup finds the first match across the world — an older object with the same name in a different room wins because it was found first in the search order.

**Detection:** Server response shows a different `#N` than expected.

**Fix:** Always use `#N` for all operations after `@create`. The `@create` response gives you `#N` — use it for every subsequent `@alias`, `@describe`, `@edit`, `@move`, and `@obvious` call on that object.

**Recovery (Django shell):** `v.origin = Object.objects.get(pk=CORRECT_PK); v.save()`

---

### Post-completion inference stall

**Pattern:** Agent successfully completes a sub-goal, writes a DONE summary, then takes 7–15 minutes without producing a new goal. Process is still running; log is frozen.

**Root cause:** Open-ended "what should I build next?" generation is expensive. After a satisfying sub-goal the KV cache is large and next-token probabilities spread thin, causing slow sampling.

**Distinguish from crash:** Process still shows in `ps aux`. No `[LLM error]` in log. SSH session still open (no "Disconnected" line).

**Most common triggers:** After `@show` (verbose output fills context), after completing an interactive verb system end-to-end, after a DONE hallucination following an error.

**Fix:** Kill and restart. The fresh session resumes from last goal with smaller starting context.

---

### Intermediate DONE hallucination — assuming server output before seeing it

**Pattern:** Agent queues multiple commands, one fails mid-script, but the DONE thought summarises intent as if everything succeeded. Subsequent goals reference objects/state from the hallucinated success.

**Observed variant:** Agent writes "Assuming the output reveals `#415 (cracked gauge)`:" then immediately acts on `#415` (an exit, not the gauge) without waiting for server confirmation.

**Root cause:** The DONE summary is written by the LLM using its own intent, before actual server responses are processed.

**No code fix.** Inject corrective goals when the log shows the agent acting on hallucinated state for 2+ consecutive cycles.

---

### `BUILD_PLAN:` emitted repeatedly — agent never builds

**Pattern:** Agent emits `BUILD_PLAN:` 5+ times in a session (one per wakeup cycle) without ever issuing `@dig`, `@create`, or any MOO commands.

**Root cause:** `_save_build_plan` only saved the YAML file and logged a thought. It set no follow-up goal or memory. The `DONE:` handler clears `_current_goal`, so any goal set in `_save_build_plan` was immediately wiped. On the next wakeup, the LLM saw an empty goal and replanned.

**Fix:** Set `_memory_summary` inside `_save_build_plan`. Unlike `_current_goal`, `_memory_summary` survives `DONE:` clearing — it's prepended to every subsequent LLM user message as `[Earlier context: ...]`. The injected message explicitly says "BUILD_PLAN saved, do not re-emit, start building NOW."

---

### Agent ignores BUILD_PLAN room list — invents new rooms mid-session

**Pattern:** Agent emits a valid 8-room BUILD_PLAN and saves it to a YAML file. Then it proceeds to build rooms with different names than those in the plan ("The Larder" instead of "The Wine Cellar"), chaining them in a line without hub branching.

**Root cause:** `_save_build_plan` saved the file but didn't populate `_current_plan`. Without a "Remaining plan: ..." line in every LLM user message, the agent had no reminder of the plan's room names and improvised.

**Fix:** In `_save_build_plan`, extract room names from the YAML with `re.findall(r"^\s*-\s+name:\s*[\"']?([^\"'\n]+)[\"']?", expanded, re.MULTILINE)` and assign to `self._current_plan`. Every subsequent LLM cycle then shows `Remaining plan: Room A | Room B | ...` — the agent follows the list instead of inventing.

---

### Agent revisits completed rooms — `_current_plan` never shrinks

**Pattern:** After building The Laboratory, the agent returns to inspect it on every cycle instead of progressing to the next room. "The Laboratory" stays at position 0 in the "Remaining plan:" line.

**Root cause:** `_current_plan` is set from the BUILD_PLAN and never shrinks. The agent sees its completed room at the top of the list and treats it as still needing work.

**Fix:** Added `## Tracking Plan Progress` to `SOUL.md` explaining the `PLAN:` directive. After completing each room, the agent should emit `PLAN: RoomB | RoomC | RoomD` (with completed rooms removed). `brain.py` already handles `PLAN:` — it sets `_current_plan` to the pipe-delimited list.

---

### `\"` inside `@edit verb ... with "..."` stores broken verb code

**Pattern:** Agent writes `@edit verb tell on #N with "... f'{this.name} says: \"{line}\"')"`. Server responds "Created verb tell on #N" — success. But at runtime (when `go <dir>` triggers `announce_all_but`), the verb crashes with `SyntaxError: unterminated string literal at statement: '"import random'`.

**Root cause:** The MOO parser does not support `\"` escaping inside `with "..."` strings. The `\"` terminates the outer string prematurely. Everything after the first `\"` is treated as unquoted text. The stored verb code begins with `"import random` (a literal leading `"`), which is a Python syntax error.

**Detection:** `SyntaxError: unterminated string literal (detected at line 1) at statement: '"import random'`. The leading `"` in `'"import random'` is the tell.

**Fix:** Remove all `"` characters from the verb code inside `with "..."`. Use:

- Single-quoted f-strings: `f'{this.name} says: {line}'` (no inner `"`)
- String concatenation: `this.name + ' says: ' + line`

The SOUL.md NPC tell example was updated. The original example had `f'{this.name} says: \"{line}\"'` — replaced with `f'{this.name} says: {line}'`.

---

### SOUL.patch.md contains wrong or misplaced entries — corrupts all future sessions

**Pattern:** `SOUL.patch.md` accumulates entries across sessions that are:

- Factually wrong: `"@edit ... with '...' is currently broken"` (it works fine)
- Stale after DB reset: `"centrifuge ambiguity requires renaming #166"` (those objects no longer exist)
- Under the wrong section: typo corrections and lessons under `## Verb Mapping` instead of `## Lessons Learned`

**Impact:** All `## Lessons Learned` content is merged into `soul.context` and injected into every future session's system prompt. A single wrong entry like `"@edit ... is broken"` caused the agent to stop creating verbs entirely.

**Root cause:** The agent writes `SOUL_PATCH_NOTE:` entries freely without checking section headers. No validation prevents bad entries from accumulating.

**Fix:** Read `SOUL.patch.md` at the start of every training session (Step 1.5 in the workflow). Check for wrong facts, stale IDs, and misplaced entries. If found, clear the file to empty sections before restarting. The trainer is the last line of defense.

---

## Infrastructure issues

### GPU OOM misdiagnosed as context overflow

**Symptom:** LM Studio logs show `ggml_metal_synchronize: error: command buffer 0 failed with status 5 — Insufficient Memory (kIOGPUCommandBufferCallbackErrorOutOfMemory)`. Agent gets `Error code: 400 - {'error': 'Compute error.'}`.

**Cause:** Metal GPU ran out of VRAM during inference. The model weights + KV cache for a large `n_ctx` slot exhaust available GPU memory. This is distinct from a context window overflow.

**Distinguish from real context overflow:** A true context overflow shows `n_keep: N >= n_ctx: M` in LM Studio debug logs, where N > M. GPU OOM shows `Insufficient Memory` / `kIOGPUCommandBufferCallbackErrorOutOfMemory`.

**Fix:** Reduce `n_ctx` in LM Studio (e.g. 65536 → 32768), or reduce GPU layer count to free VRAM. Kill and restart the agent after changing LM Studio settings.

---

## New features (brain.py)

### `SOUL_PATCH_NOTE` directive

**Added:** `SOUL_PATCH_NOTE: <text>` is now a recognized LLM directive alongside `SOUL_PATCH_RULE` and `SOUL_PATCH_VERB`.

**Behavior:** The note is appended to `## Lessons Learned` in `SOUL.patch.md` as a bullet. On every subsequent session, the Lessons Learned section is merged into `soul.context` and injected into the system prompt. This allows the agent to accumulate factual discoveries across sessions without trainer intervention.

**When to emit:** The `_PATCH_INSTRUCTIONS` prompt tells the agent to emit a note immediately after a self-correction — not after multiple repetitions. Example output:

```
SOUL_PATCH_NOTE: obj.name is a model field — always call obj.save() after assigning it
```

**Implementation files:** `moo/agent/brain.py` (`_PATCH_NOTE_RE`, `_apply_patch`), `moo/agent/soul.py` (`append_patch`, `_parse_md_file` flush handler, `parse_soul` context merge).

---

## Infrastructure issues (agent runtime)

### TUI crash kills agent when run headless

**Symptom:** Agent connects, then immediately disconnects. No log entries after "Connected."

**Cause:** `MooTUI` uses prompt_toolkit which requires a real TTY. When the agent runs as a background process (`> file &`), stdin is not a TTY. `tui.run()` raised `OSError: Invalid argument`. Because `asyncio.wait(return_when=FIRST_COMPLETED)`, the crashing TUI task completing first cancelled the brain task.

**Fix (`cli.py`):** Only create `MooTUI` if `sys.stdin.isatty()`. Only add the TUI task to the wait set if it exists.

### SOUL.md bullet points silently dropped

**Symptom:** Added a `## Room Layout` section with bullet points to `SOUL.md`, but the guidance never reached the LLM.

**Cause:** `soul.py`'s list handler only stored items that parsed as `pattern -> command` (rules) or `intent -> command` (verb mappings). All other list items were silently discarded instead of accumulated into `body_lines`.

**Fix (`soul.py`):** Non-special list items (those without `->` that aren't in a rules/verbs section) are now appended to `body_lines` as `f"- {raw}"`.

### LLM 400 error with `<|channel>thought` tokens

**Symptom:** `[LLM error] Error code: 400 - {'error': 'Failed to parse input at pos 0: <|channel>thought\n...`

**Cause:** The model (Gemma 4 26B via LM Studio) leaked internal chain-of-thought tokens into its response. LM Studio returned a 400 error.

**Brain behavior:** 400 is not retried (only 529 is). The cycle aborts and the 60-second wakeup will try again. If the model keeps producing malformed output, the agent is effectively stuck.

**Fix:** Kill and restart. Context-dependent — the model usually self-corrects on a fresh session. No code change made; this is a model/LM Studio behavior issue.

---

## Tool harness (2026-04-04)

### LM Studio tool call in SCRIPT: block uses Python function syntax

**Symptom:** Agent correctly uses tool calls for some operations but puts `move_object(obj="#44", destination="#41")` inside a `SCRIPT:` block instead of using tool call syntax. The brain sends this verbatim to the MOO server, which responds "Huh?".

**Root cause:** Gemma 4 emits a mix of native tool calls and SCRIPT: text blocks. When it decides to batch several operations, it sometimes puts them in a SCRIPT: block using Python function call syntax instead of raw MOO commands.

**Fix (`brain.py`):** `_handle_script_line()` now tries `parse_tool_line()` on each pipe-split step. If a step matches a known tool name (using the new `_BARE_CALL_RE` bare function call regex), it's expanded via `spec.translate()` before being queued. Unknown steps pass through as raw MOO commands.

**Fix (`tools.py`):** Added `_BARE_CALL_RE = re.compile(r"^(\w+)\s*\(([^)]*)\)\s*$")` and updated `parse_tool_line()` to accept a `known_names` set parameter. Bare calls are only matched when `known_names` is provided, preventing false positives on MOO commands that contain parentheses.

### LM Studio response truncated at max_tokens creates object with `"name` (quote in name)

**Symptom:** Server creates object `Created #45 ("marble)` — the name includes an opening quote.

**Root cause:** LLM response was truncated at the 512-token limit. The `create_object` tool call arg `name="marble pedestal"` was cut off mid-string, leaving `name="marble` (no closing quote). The tool's `translate()` produced `@create "marble` (unmatched quote), which the parser accepted without error.

**Fix (parser, `moo/core/parse.py`):** Added `_check_quotes()` function called in `Lexer.__init__()`. Counts unescaped `"` characters; if the count is odd, raises `UsageError('Unmatched quote in command.')`. The agent now receives an error response and can retry with a corrected name.

**Note:** This is a defense-in-depth fix. The primary cause (LLM truncation) is addressed by keeping `max_tokens=512` reasonable and monitoring for runaway context. The parser fix prevents silent data corruption when any truncated command reaches the server.

### Agent replans on restart — emits BUILD_PLAN: mid-session

**Symptom:** After a restart, the agent's `_current_plan` is empty. The user message shows no "Remaining plan:" line. The LLM concludes the plan is missing and emits a new (partial) `BUILD_PLAN:` with fewer rooms than the original, potentially forgetting already-built rooms.

**Root cause:** `Brain.__init__()` initialized `_current_plan = []` unconditionally. The plan was only populated when the LLM emitted a `BUILD_PLAN:` directive, not from disk.

**Fix (`brain.py`):** Added `_load_latest_build_plan()` called in `__init__()` after state initialization. Reads the most recent `builds/*.yaml` file and extracts room names into `_current_plan`. On a clean resume, the agent sees "Remaining plan: ..." in its first user message and continues from where it left off without re-planning.

**Caveat:** The loaded plan contains all rooms, including already-built ones. The agent's `PLAN:` directives (emitted after each room completion) advance `_current_plan` normally, so completed rooms will be trimmed as the session progresses. The agent may still attempt to build already-built rooms on the first cycle of a fresh resume; `@dig` will return "There is already an exit in that direction." and `_ERROR_PREFIXES` will catch it.

### Context size causes KV cache exhaustion — inference stalls 5-15 min

**Symptom:** After 2-4 rooms built, LLM inference takes 5-15 minutes per cycle. Agent appears frozen. No error in the log — just a long gap between the last server response and the next thought.

**Root cause:** The total system prompt was ~2200 lines across SOUL.md, baseline.md, and four reference files (moo-commands.md, object-model.md, room-description-principles.md, verb-patterns.md). At ~5 tokens/line, this is ~10k tokens of system prompt on every call. LM Studio recomputes the KV cache for the full context on every inference call.

**Mitigations applied (2026-04-04):**

- Removed `moo-commands.md` from SOUL.md `## Context` references (368 lines) — tool schemas encode command syntax
- Removed `## $furniture Placement`, `## \`obvious\` is a Model Field`, long`## Aliases` from `baseline.md` (~50 lines) — replaced by `move_object`,`make_obvious`,`alias` tools
- Replaced `## Response Format` (37 lines) with a 10-line tool-aware version — the old SCRIPT:/COMMAND: examples conflicted with tool-use instructions
- Replaced `## Core Command Syntax` (35 lines) with a 10-line "Non-Tool Commands" section covering only @eval, @recycle, @tunnel
- Reduced `memory_window_lines` from 50 → 20
- Added `max_tokens: 512` to settings.toml
- Added `cache_type_k: "q8_0"` and `cache_type_v: "q8_0"` to LM Studio `extra_body`

**If stall recurs:** Kill the agent and restart. A fresh context (new session) takes 2-3 min/cycle instead of 15+. Long-running sessions accumulate KV state and slow down even with quantization.

### Multi-agent token passing: page + done() as two thought lines — neither dispatched

**Symptom:** Mason's log shows it emitted both `page(...)` and `done(...)` as thought lines but neither was executed. Agent exits without paging successor.

**Root cause:** Brain's single-line fallback required exactly one non-empty thought line. Two bare tool calls in one response → neither dispatched.

**Fix:** Extended fallback: if ALL non-empty thought lines parse as valid tool calls, process them in order. Located in `brain.py` `_handle_llm_response()`.

---

### `@create` fails with `PermissionError: Can't change owner at creation time`

**Symptom:** Celery logs show `PermissionError: Can't change owner at creation time` when a non-wizard player (Tinker, Joiner) runs `@create`.

**Root cause:** `@create` is a wizard-owned verb. Inside it, `ContextManager.get("caller")` returns Wizard. `Object.save()` checks `self.owner != caller` at creation — the new object's owner is the player, but caller is Wizard → permission error.

**Fix:** Wrap `create()` in `set_task_perms(context.player)` inside `at_create.py`. This sets `caller = context.player` for the duration of the call.

---

### `PermissionError: not allowed to 'derive'` for non-wizard players

**Symptom:** Tinker (or any non-wizard) gets `PermissionError: #22 (Tinker) is not allowed to 'derive' on #4 (Root Class)` when running `@create X from "$thing"`.

**Root cause:** `derive` ACL was only granted to Wizard on system classes by default.

**Fix:** Grant `derive` to `everyone` on all system classes. Applied immediately via Django shell and added to `default.py` bootstrap for future resets.

---

### `NameError: name 'lookup' is not defined` in `@move` error path

**Symptom:** Celery logs show `NameError: name 'lookup' is not defined` after a failed `@move` command.

**Root cause:** `at_move.py` error-handling path calls `lookup(dobj_str, return_first=False)` but `lookup` was not imported.

**Fix:** Add `lookup` to the import in `at_move.py`: `from moo.sdk import context, lookup`.

---

### Traversal plan lost on restart — agent visits one room then passes token

**Symptom:** After a restart, a traversal agent (Tinker, Joiner, Harbinger) visits only one room then pages its successor, ignoring the rest of the plan.

**Root cause:** `_current_plan` was in-memory only. On restart it was empty, so the agent thought the plan was complete after the first room.

**Fix:** Added `_save_traversal_plan()` (writes to `builds/traversal_plan.txt` on every `PLAN:` update) and `_load_traversal_plan()` (called in `__init__` after `_load_latest_build_plan()` if plan is still empty). Traversal agents that don't emit `BUILD_PLAN:` now resume correctly.

---

### `idle_wakeup_seconds = 0` deadlocks agent after token received

**Symptom:** Agent receives token page, emits `GOAL:` with no command in the first cycle, then freezes indefinitely — no further LLM cycles fire.

**Root cause:** With `idle_wakeup_seconds = 0`, the only trigger for a new LLM cycle is an incoming page. After the first cycle produces only `GOAL:`, no timer fires and no page arrives → permanent freeze.

**Fix:** Set `idle_wakeup_seconds = 60` in `settings.toml` for Tinker and Joiner as a safety valve. The 60-second timer fires and retries if the first post-token cycle stalls.

---

### Multi-line `SCRIPT:` blocks silently discarded

**Symptom:** Agent emits a `SCRIPT:` on one line followed by commands on the next lines. None of the commands execute.

**Root cause:** `_SCRIPT_RE` requires pipe-delimited content on the same line as `SCRIPT:`. A bare `SCRIPT:` line matches nothing; subsequent lines fall through as thoughts.

**Fix:** Guidance only — added WRONG/RIGHT examples to `baseline.md` `## Response Format`. The correct form is: `SCRIPT: @create "name" | @alias #N as "x" | @describe #N as "..."`.

---

### Joiner uses `@eval` — blocked for `$player` accounts

**Symptom:** Joiner attempts `@eval ...` and gets `Huh? I don't understand that command.`

**Root cause:** `@eval` is a `$programmer`-class verb. Joiner is a `$player`, so the verb is not dispatched.

**Fix:** Added warning to `joiner/SOUL.md` `## Common Pitfalls`: `@eval` is not available — use tools (`describe`, `alias`, `make_obvious`) and `@create X from Y in #N` for placement.

---

### `$furniture` cannot be moved after creation — `@move` returns "cannot be moved"

**Symptom:** Joiner creates furniture, then tries `@move #N to #M` or `move_object(...)` — server returns `#N cannot be moved.`

**Root cause:** `$furniture.moveto` verb returns `False` for non-wizards unconditionally — furniture is fixed in place by design.

**Fix (SOUL.md):** Joiner must use `@create "name" from "$furniture" in #ROOM` to place furniture directly at creation time via ORM, bypassing `moveto`. Added to `joiner/SOUL.md` `## Placement` and `SOUL.patch.md`.

**Fix (at_create.py):** Restructured `@create` to resolve the `in` location before calling `create()`, passing it as `location=` to the ORM directly. This also required supporting `@create X from Y in #N` as a first-class usage pattern (was previously only supported for "void").

---

### `enterfunc` Celery task fails with `Object.DoesNotExist` after `@create X in #N`

**Symptom:** Celery CRITICAL: `DecodeError(DoesNotExist('Object matching query does not exist.'))` for `invoke_verb enterfunc` task immediately after a successful `@create`.

**Root cause:** `Object.save()` dispatches the `enterfunc` Celery task synchronously (line 870 of `object.py`) before the enclosing `@create` task's database transaction commits. The Celery worker picks up `enterfunc`, tries to deserialize the new object via `Object.objects.get(pk=N)`, and fails because the transaction hasn't committed yet. This race was latent — only surfaced when `@create X in #N` started placing objects directly in rooms (triggering `enterfunc`), rather than in player inventory (rooms have `enterfunc`, players don't).

**Fix:** Wrapped both `enterfunc` and `exitfunc` dispatches in `transaction.on_commit()` in `object.py`:

```python
_enterfunc = self.location.get_verb("enterfunc")
_self = self
transaction.on_commit(lambda: invoke(_self, verb=_enterfunc))
```

---

### `@move me to #N` crashes Celery with `AttributeError: 'NoneType' object has no attribute 'pk'`

**Symptom:** `server_error` traceback ending in `caller_id=context.caller.pk` / `AttributeError: 'NoneType' object has no attribute 'pk'` when Joiner (or any agent) runs `@move me to #N`. Move itself succeeds (object relocates) but the Celery task raises an exception.

**Root cause:** `code.ContextManager` was nested *inside* `transaction.atomic()` in `parse_command` and `parse_code` tasks. When `ContextManager.__exit__` ran (at the end of the inner `with`), it reset `context.caller = None`. Then `transaction.atomic().__exit__` fired the `on_commit` hooks — but by then `context.caller` was already None. The `invoke()` call inside the `exitfunc` on_commit lambda then crashed on `context.caller.pk`.

**Fix (`moo/core/tasks.py`):** Swapped nesting so `code.ContextManager` is the *outer* context and `transaction.atomic()` is the *inner* one. The `Object.objects.get(pk=caller_id)` fetch was moved above both:

```python
caller = Object.objects.get(pk=caller_id)
with code.ContextManager(caller, output.append, task_id=task_id) as ctx:
    with transaction.atomic():
        parse.interpret(ctx, line)
```

Now `context.caller` is still set when `transaction.atomic()` exits and fires `on_commit` hooks.

Applied to both `parse_command` and `parse_code` tasks. Requires Celery worker restart (`docker restart django-moo-celery-1`).

---

## Agent helper verb patterns (2026-04-06)

### Agent uses `@show here` instead of `survey()` — context overload

**Pattern:** Agent calls `show(target="here")` or emits `SCRIPT: @show here` to inspect the current room. The response is ~40 lines covering the full object graph. After 1–2 rooms, context fills and the agent stalls or loses earlier plan steps.

**Why it matters:** `survey()` returns ~5 lines (room name + id, exits, contents count). `@show here` returns 40+ lines including raw property values, parent chains, and verb listings — none of which the agent needs for navigation or building.

**Fix:** Replace `show(target="here")` with `survey()` in agent guidance. `inspect_room → @survey here` in Verb Mapping. Added to `baseline.md` World Inspection table.

---

### Agent chains `go` commands for long-range navigation — fills context before work begins

**Pattern:** Agent emits 4–6 `go(<direction>)` calls to cross the world to a target room. Each hop fills context with look output. By the time the agent arrives, it has consumed enough tokens that plan steps start falling out of the rolling window.

**Why it matters:** A 3-room chain (`go north → go east → go up`) costs 3 tool calls + 3 server responses. `teleport(destination="#N")` costs 1.

**Fix:** Add `teleport` to all traversal agent tool lists. Update `## Room Traversal` to use `teleport(destination="#N")` for inter-room movement. Add `teleport_to → teleport #N` to Verb Mapping.

---

### Agent uses `@dig` + `go` + `@tunnel` as three separate steps (Mason)

**Pattern:** Mason emits `dig(direction="north", room_name="The Vault")`, then `go(direction="north")`, then `tunnel(direction="south", destination="#N")`. This three-step pattern has a common failure: forgetting `tunnel`, using the wrong return direction, or losing `#N` between cycles. Results in exits wired in only one direction.

**Why it matters:** `@burrow` is an atomic operation — one call creates the forward exit, the new room, moves the agent inside, and wires the return exit automatically.

**Fix:** Replace `dig` + `go` + `tunnel` with `burrow` in Mason's build procedure. `burrow(direction, room_name)` infers the return direction automatically via the `_OPPOSITES` dict. Remove `dig`, `go`, `tunnel` from Mason's primary tool list (retained as fallback only).

---

### Agent uses `@realm $room` for room discovery

**Pattern:** Agent emits `SCRIPT: @realm $room` to list all room instances. Output is unformatted and includes system classes (`$room`, `$exit`) alongside real room instances, requiring the agent to filter mentally. Also slower — `@realm` does a full class traversal on every call.

**Fix:** Replace `@realm $room` with `rooms()` tool call. `@rooms` filters out system class objects automatically (those registered as properties on System Object #1) and returns only true room instances. Updated in all traversal agents' `## Room Traversal` sections. `list_rooms → @rooms` in Verb Mapping.

---

### `burrow` fails with "There is already an exit in that direction" — agent not checking first

**Pattern:** Mason calls `burrow(direction="north", room_name="The Vault")` but north already has an exit. `@burrow` returns an error and no room is created. Agent may retry in the same direction or stall.

**Root cause:** Same underlying issue as the old `@dig` collision, now surfaced by `@burrow`.

**Fix:** `## Pre-Build Checklist` in `SOUL.md` updated: call `exits()` before `burrow()` to check occupied directions. `exits()` returns only exit names and destinations — ~2 lines — not the full room graph.

---

### `describe` called before `burrow` moves agent — overwrites origin room description

**Pattern:** Agent calls `describe(target="here", text="...")` immediately after planning a room, before calling `burrow`. The description is applied to the current (origin) room, not the new room. The origin room's description is overwritten with the wrong text.

**Root cause:** Old guidance said `go()` → `describe()`. After switching to `burrow()`, the agent may still think it needs to navigate manually. `burrow()` moves the agent automatically — `describe()` should be called right after `burrow()` output is received.

**Fix:** Added to `## Common Pitfalls` and `## Build Planning` in `SOUL.md`: "`burrow` moves you into the new room automatically — call `describe` immediately after `burrow`, do NOT call `go()` first."

---

### `confunc.py` calls `move()` — agents stay locationless on connect

**Pattern:** All four agents connect but remain in void (locationless). Any verb that calls `context.player.location.match_exit()` fails immediately with `AttributeError: 'NoneType' object has no attribute 'match_exit'`. `@burrow` and `@dig` both fail this way.

**Root cause:** `confunc.py` called `context.player.move(lab)` but the method is `moveto`, not `move`. The attribute doesn't exist on the Object model.

**Fix:** Changed `context.player.move(lab)` → `context.player.moveto(lab)` in `moo/bootstrap/default_verbs/player/confunc.py`.

---

### `at_rooms.py` fails with `ImportError: Restricted: json`

**Pattern:** `@rooms` verb raises `ImportError: Restricted: json` when run. The verb never returns its room listing.

**Root cause:** The original `at_rooms.py` imported `moojson` from `moo.sdk`. The RestrictedPython sandbox blocks imports whose name contains "json" (interpreted as the stdlib `json` module). Specifically `moojson.loads()` triggered the restriction.

**Fix:** Rewrote `at_rooms.py` to use only `context`, `lookup`, and `open_paginator` from `moo.sdk`. Removed the system-class filtering logic that required `moojson` and `Property`/`Object` model imports — just list all descendants of `$room` excluding the class itself.

---

### Test SSH commands leave stale exits blocking agent's first `@burrow`

**Pattern:** After testing `@burrow` via `moo_ssh.py` as wizard, a test room and exit are created in The Laboratory. When agents start, Mason's first `@burrow north` fails with "There is already an exit north from this room." even though no real rooms have been built yet.

**Root cause:** `@recycle <room>` deletes the room object but does NOT update the source room's `exits` property — the stale exit object reference remains. The exit object itself must also be recycled separately, and the source room's `exits` property must be manually cleared.

**Fix:** Before running agents after any test session: run `@eval "lookup(19).set_property('exits', [])"` to clear The Laboratory's exits, and `@recycle #N` for any stale exit objects. Check with `@show here` to confirm exits list is empty.
