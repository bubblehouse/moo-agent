---
name: zork-shakedown
description: End-to-end ZIL→DjangoMOO debugging skill. Drive zork1.local through MooSSH to find translator/server bugs, OR pick a known failure and fix it inside extras/zil_import/ (translator/generator/SDK). Use when the user asks to shake down Zork, raise the smoke pass count, debug a zork1 failure, or close a translation gap. Read references/rule-zero.md before any edit under moo/.
compatibility: Designed for Claude Code. Requires the django-moo repository, a running docker-compose stack, the moo-agent extension installed (provides moo.bootstrap.zork1), and the zork1.local Site initialised.
---

# Zork Shakedown

This skill covers the full Zork debugging loop: **find** bugs by playing the canonical world, then **fix** them inside `extras/zil_import/` and verify with the smoke harness. One skill, two modes.

## Where files live

- **moo-agent** is the working directory for this skill. The Zork dataset (`moo/bootstrap/zork1/`), the ZIL translator (`extras/zil_import/`), and this skill itself all live here. Path references like `moo/bootstrap/zork1/...` and `extras/zil_import/...` are relative to the moo-agent repo root.
- **django-moo** is the engine repo — `moo/core/`, `moo/sdk/`, `moo/shell/`, `moo/bootstrap/__init__.py`, and `moo/bootstrap/default/`. These are off-limits for fitting Zork-specific bugs (see Rule Zero below).

Both repos contribute to the `moo.*` namespace package, so the same `moo.bootstrap.zork1` resolves regardless of which working directory you're in — but edits and tests for ZIL translation work happen here.

## 🛑 RULE ZERO — READ BEFORE EVERY EDIT IN `moo/`

**DO NOT MODIFY `moo/` (OUTSIDE `moo/bootstrap/zork1/`) TO MAKE THE ZORK BOOTSTRAP WORK.**

The user has stated outright that another violation will end the collaboration. Every translation gap must be solved inside `extras/zil_import/` (translator, generator, IR, or `verbs/`) or in the System Object's `do_command` verb. The full anti-pattern catalog is [references/rule-zero.md](references/rule-zero.md) — read it before starting work.

If you find yourself about to edit `moo/core/`, `moo/sdk/`, `moo/shell/`, `moo/bootstrap/__init__.py`, or `moo/bootstrap/default/`, **stop and ask the user first**. The default answer is no.

## ✍️ This skill is self-updating

Every session, the final step is to update this skill's own files with anything you learned that wasn't already documented:

- A new failure mode found via shakedown → add to [BUGS.md](BUGS.md).
- A bug that needs a moo-core change → add to [TODO.md](TODO.md) with the rationale.
- A new translator/generator/SDK fix that landed → add to [references/completed-work.md](references/completed-work.md).
- A new smoke-workflow trick → add to [references/smoke-workflow.md](references/smoke-workflow.md).
- A pre-existing limitation that surfaced → add to [references/known-quirks.md](references/known-quirks.md) so the next session doesn't re-report it.
- A new boundary case where the temptation to edit moo-core arose → add to [references/rule-zero.md](references/rule-zero.md).

The skill compounds value only if each session leaves it sharper than it found it.

## Files in this skill

| File | Purpose |
|---|---|
| `BUGS.md` | Open bugs found via shakedown. Newest first. Each entry has hypothesis + workaround. |
| `TODO.md` | Bugs deferred because they need a moo-core change (Rule Zero blocks them). |
| `scripts/zork_session.py` | Long-lived MooSSH harness for shakedown sessions. |
| `references/rule-zero.md` | The no-moo-core-edits constraint, with anti-patterns already attempted (and reverted). Read this first. |
| `references/coverage.md` | Master list of rooms/verbs/objects/probes to exercise during shakedown. Tick when verified. |
| `references/known-quirks.md` | Pre-existing limitations; don't re-report. |
| `references/smoke-workflow.md` | Regen + sync + smoke + spot-test commands. The fix-loop reference. |
| `references/completed-work.md` | Translator/generator/SDK fixes that landed (don't re-do these; build on them). |

## Mode 1 — Shakedown (find bugs)

You are a Zork I player who happens to be a MOO engine debugger. Drive **one** SSH session that stays open from start to finish; every command goes through it.

### Driving the session

All paths below are `extras/skills/zork-shakedown/`.

```bash
# Always include --reset for a fresh session.
extras/skills/zork-shakedown/scripts/zork_session.py start --reset

# Send commands and read responses
extras/skills/zork-shakedown/scripts/zork_session.py send "look"
extras/skills/zork-shakedown/scripts/zork_session.py read --tail 30

# "show me everything since the last `look`"
extras/skills/zork-shakedown/scripts/zork_session.py since "look"

# Always stop cleanly at the end of the session
extras/skills/zork-shakedown/scripts/zork_session.py stop
```

**Run `start` with `Bash run_in_background: true`** — the harness is a long-running daemon and won't return until `stop`.

If `read` shows `[harness] error:`, the SSH connection probably dropped. Run `status`. If "not running", restart with `start --reset` and note the disconnect in `BUGS.md` if it looks like a real engine crash.

### Bug-logging workflow

Trigger conditions — log to `BUGS.md` if you see any of:

- `Traceback` / `SyntaxError` / `AttributeError` / `PermissionError` in a server response
- A canonical Zork command rejected as `I don't know how to do that` (cross-reference `references/known-quirks.md` first)
- A room missing an exit its description claims (e.g., "a path leads east" but `go east` fails)
- A verb returning blatantly wrong text (player listed as occupant; description printed twice; `desc` returns `ldesc`)
- Hint-named objects unresolvable by the parser (the global-scenery class of bug)
- The connection drops without you sending `@quit`
- Score increments incorrectly (deposited treasure but no points, or vice versa)

When one fires:

1. **Grep first.** Check both `BUGS.md` and `references/known-quirks.md` — if already there, just `[x]` the existing checkbox if it's still reproducible.
2. **Append a new entry at the top of `BUGS.md`** in this format:

   ```markdown
   - [ ] **<one-line summary>** (room: `<Room Name>`, command: `<command>`)
     - **Response**: `<verbatim, trimmed to 5 lines max>`
     - **Hypothesis**: <1-2 sentence guess: translator? generator? bootstrap state? sandbox? parser?>
     - **Workaround**: <what you did to keep moving>
   ```

3. **Don't try to fix it during shakedown.** Workaround and continue. Fixing is Mode 2.
4. **Don't restart the session for every bug.** Bugs are more useful in the context of a long session.

### Coverage workflow

`references/coverage.md` is the master to-do list. Walk it section by section:

1. **Movement section first.** Try the canonical opening sequence (West of House → north → east → west through the kitchen window → up to attic → down to Living Room → move rug → open trap door → light lantern → down to Cellar). Each successful step ticks a box.
2. **Verb section second.** As you encounter situations, exercise the listed verbs naturally — don't force them.
3. **Failure-mode probes last.** These are checks that things fail correctly: SW from West of House blocked (WON-FLAG), `climb walls` at End of Rainbow fails, dark rooms without light → grue. Failures here that *don't* match the expected failure are bugs.

After every ~30 commands, glance at `coverage.md` and tick anything you've completed (only what you've actually verified).

### Session shape

- **Length**: 200-400 commands, 1-2 hours. Past 2 hours, value-per-command falls off.
- **Cadence**: send → read → think → send. One command per turn unless chaining obvious-success steps.
- **Periodic summary**: every ~30 commands, write a one-paragraph status to chat.

### End-of-session deliverables

Before stopping the session:

1. Tick the right boxes in `coverage.md`.
2. Make sure `BUGS.md` is current — every bug has an entry; hypotheses are filled in.
3. One-paragraph chat summary: rooms reached, treasures collected, top 3 most-impactful bugs found, % coverage ticked.
4. `stop` the session.

If a `BUGS.md` item turns out to be already-known, move it to `known-quirks.md`.

## Mode 2 — Fix (translator/generator/SDK)

The smoke test (`extras/zil_import/scripts/zork1_smoke.py`) drives the canonical Zork command sequence and reports a pass/total count. The metric you care about is closing the gap between current pass count and 350.

### Before you start

1. Read [references/rule-zero.md](references/rule-zero.md) — the prohibition list and anti-patterns already committed and reverted.
2. Read [references/completed-work.md](references/completed-work.md) — what landed in `extras/zil_import/`. Don't re-do these.
3. Read [BUGS.md](BUGS.md) — open bugs and translation gaps with game-side fix paths. The "Translation gaps" and "Structural polish backlog" sections list game-side improvements that don't surface as single-command bugs.
4. Read [references/smoke-workflow.md](references/smoke-workflow.md) — how to regen, sync, run the smoke (and the spot-test variant), and interpret failures.
5. Skim `extras/zil_import/AGENTS.md` for the importer's design rules.

### The work loop

1. **Pick one failure category.** Don't fan out — cascading failures often share a root cause.
2. **Locate the cause in `extras/zil_import/`.** Most live in `translator.py` (verb-body emission) or `generator.py` (bootstrap layout). Some live in `verbs/` (runtime impedance shims).
3. **Edit only inside `extras/zil_import/`.** If you can't see how to fix without touching moo-core, **stop and ask** — don't paper over the gap.
4. **Regen + sync.** See [smoke-workflow.md](references/smoke-workflow.md) for the exact commands. The headline is `uv run python -m extras.zil_import …` then `docker exec … moo_init --bootstrap zork1 --sync`.
5. **Spot-test the change** with `extras/zil_import/scripts/zork1_spot.py` (seconds), before the full smoke (~70-130s).
6. **Run the full smoke** when the spot passes — confirm no regression in adjacent commands.

### Investigating a smoke failure

The smoke output groups failures by command. Look at the response text:

- **"I don't know how to do that."** — parser couldn't dispatch. Either the verb isn't registered, the dobj isn't resolved, or `--dspec` rejects the sentence shape.
- **"You can't go that way."** — `walk` SDK couldn't find a matching exit. Often a cascade from earlier failures (player isn't where the smoke assumes).
- **Mangled `>>> ��`** — PREFIX delimiter fired but verb body produced no usable output (often a per-clause split that drops the substrate fall-through).
- **`There is no <X> here.`** — dobj resolution failed because the player isn't in the right room. Cascade from earlier movement failures.
- **Traceback / "An error occurred while executing the command."** — verb body errored. Look at the file path and line in the traceback; the bug is in the translator's emission for that ZIL form.

See [BUGS.md](BUGS.md) (Translation gaps section) and [smoke-workflow.md](references/smoke-workflow.md) for diagnosis recipes.

### Connected harness vs isolated shell tests

Two ways to spot-test a translator/generator change:

1. **Connected harness** (`scripts/zork_session.py` from Mode 1) — long-lived SSH session through the full shell+celery+parser flow. Use this to answer "does this command do the right thing for a player." Catches dispatch / state / timing bugs.
2. **Isolated `manage.py shell -c`** with `parse.interpret(ctx, cmd)` inside `ContextManager(wiz, writer, site=zork)` — bypasses SSH and most of the celery / shell handler stack. Use this only for "does this verb's *implementation* compile and dispatch" questions.

Default to the harness. Only drop to isolated shell when the harness is offline or when the question genuinely doesn't depend on the SSH/celery chain.

## When something can't be solved without core changes

If a translation gap genuinely requires a moo-core change:

1. **Stop work on it.**
2. Move the bug from `BUGS.md` to `TODO.md` with: what the gap is, why no game-side workaround exists, what minimal core API would close it.
3. Present the writeup to the user. **Do not edit moo-core preemptively.**
4. Wait for explicit approval.

The user has approved exactly one moo-core change since this work began (the `get_pronoun_object` location-name fallback in `moo/core/parse.py`). Anything beyond that is a new conversation.

## Risks

1. **State pollution.** Each shakedown session changes the world (windows opened, treasures deposited). Always `--reset` at start. The reset is fast.
2. **Stale SSH sessions.** If you crash the harness without `stop`, the server-side session lingers. Pile-up causes problems. Always `stop` cleanly.
3. **Connection drop loops.** If `start` succeeds but the next `send` returns `[harness] error: EOF`, the server is in trouble. Don't hammer it — stop, check `docker logs --tail 50 django-moo-shell-1`, escalate to the user.
4. **Scope creep in shakedown.** If a puzzle takes more than 5 turns to figure out, log it as a bug and move on.
5. **Scope creep in fix mode.** If a "small" fix wants to spread into moo-core, stop and re-read [rule-zero.md](references/rule-zero.md).

## Memory entries that govern this work

- `feedback_zil_translator_no_core_changes` — Rule Zero (no moo-core changes for ZIL).
- `feedback_zil_importer_game_agnostic` — keep `extras/zil_import/` game-neutral; no Zork-specific tables in the importer itself.
- `feedback_zork1_all_generated` — `moo/bootstrap/zork1/` is generated output; never hand-edit, always fix at source.
- `feedback_zil_no_system_aliases_for_on` — don't pollute `$/_` with per-object atom aliases just to support `--on`.
- `feedback_zil_verbs_organized_by_owner` — verb-tree layout convention.
- `feedback_smoke_tee` — always `tee /tmp/smoke.out` so re-inspection is a `grep`, not a re-run.

## Cascade failures — diagnosis tip

A LOT of "You can't go that way" and "There is no `<X>` here" failures are
cascades from earlier movement / scenery failures. Don't try to fix
cascading symptoms one by one — find the earliest root cause in the smoke
trace and fix that first; re-run smoke; see what cascade resolved.
