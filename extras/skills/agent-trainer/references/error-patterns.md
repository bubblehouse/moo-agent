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
