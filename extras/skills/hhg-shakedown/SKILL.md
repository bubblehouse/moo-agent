---
name: hhg-shakedown
description: End-to-end ZIL→DjangoMOO debugging skill for The Hitchhiker's Guide to the Galaxy. Drive hhg.local through MooSSH to find translator/server bugs, OR pick a known failure and fix it inside moo/zil_import/ (translator/generator/SDK). Use when the user asks to shake down HHG, debug an hhg failure, or close a translation gap for HHG. Read references/rule-zero.md before any edit under moo/.
compatibility: Designed for Claude Code. Requires the django-moo repository, a running docker-compose stack, the moo-agent extension installed (provides moo.bootstrap.hhg), HHG ZIL source at /Users/philchristensen/Workspace/hitchhikersguide/, and the hhg.local Site initialised.
---

# HHG Shakedown

This skill covers the full Hitchhiker's Guide debugging loop: **find** bugs by playing the canonical world, then **fix** them inside `moo/zil_import/` and verify with the smoke harness. One skill, two modes. Patterned after `zork-shakedown` — share the translator/generator across both games, share the diagnosis vocabulary, capture HHG-specific findings here.

## Where files live

- **moo-agent** is the working directory for this skill. The HHG dataset (`moo/bootstrap/hhg/`), the ZIL translator (`moo/zil_import/`), and this skill itself all live here. Path references like `moo/bootstrap/hhg/...` and `moo/zil_import/...` are relative to the moo-agent repo root.
- **HHG ZIL source** lives outside the moo-agent repo at `/Users/philchristensen/Workspace/hitchhikersguide/`. Source is not under an open license; the regenerated `moo/bootstrap/hhg/` tree is gitignored.
- **django-moo** is the engine repo — `moo/core/`, `moo/sdk/`, `moo/shell/`, `moo/bootstrap/__init__.py`, and `moo/bootstrap/default/`. These are off-limits for fitting HHG-specific bugs (see Rule Zero below).

Both repos contribute to the `moo.*` namespace package, so `moo.bootstrap.hhg` resolves regardless of which working directory you're in — but edits and tests for ZIL translation work happen here.

## 🛑 RULE ZERO — READ BEFORE EVERY EDIT IN `moo/`

**DO NOT MODIFY `moo/` (OUTSIDE `moo/bootstrap/hhg/`) TO MAKE THE HHG BOOTSTRAP WORK.**

The user has stated outright that another violation will end the collaboration. Every translation gap must be solved inside `moo/zil_import/` (translator, generator, IR, or `verbs/`) or in the System Object's `do_command` verb. The full anti-pattern catalog is [references/rule-zero.md](references/rule-zero.md) — read it before starting work.

If you find yourself about to edit `moo/core/`, `moo/sdk/`, `moo/shell/`, `moo/bootstrap/__init__.py`, or `moo/bootstrap/default/`, **stop and ask the user first**. The default answer is no.

The shared `moo/zil_import/` IS in scope; the bare minimum for HHG-only changes goes under `moo/zil_import/verbs/hhg/` (per-game override directory, mirrors `verbs/zork1/`). Translator/generator changes that affect both games are appropriate when the change is genuinely game-neutral.

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
| `HHG-FEASIBILITY.md` | The 2026-05-24 scan that landed HHG translation. Read this first for context on what's been done. |
| `BUGS.md` | Open bugs found via shakedown. Newest first. Each entry has hypothesis + workaround. |
| `TODO.md` | Bugs deferred because they need a moo-core change (Rule Zero blocks them). |
| `FEATURES.md` | Coverage map of HHG-specific features (identity switches, Babel fish, improbability drive, …) and probes. |
| `scripts/hhg_session.py` | Long-lived MooSSH harness for shakedown sessions against `hhg.local`. |
| `references/rule-zero.md` | The no-moo-core-edits constraint, with anti-patterns already attempted (and reverted). Read this first. |
| `references/coverage.md` | Master list of HHG rooms/verbs/objects/probes to exercise during shakedown. Tick when verified. |
| `references/known-quirks.md` | Pre-existing limitations; don't re-report. |
| `references/smoke-workflow.md` | Regen + sync + smoke + spot-test commands. The fix-loop reference. |
| `references/completed-work.md` | Translator/generator/SDK fixes that landed (don't re-do these; build on them). |

## Mode 1 — Shakedown (find bugs)

You are an HHG player who happens to be a MOO engine debugger. Drive **one** SSH session that stays open from start to finish; every command goes through it.

### Driving the session

```bash
# Always include --reset for a fresh session.
extras/skills/hhg-shakedown/scripts/hhg_session.py start --reset

# Send commands and read responses
extras/skills/hhg-shakedown/scripts/hhg_session.py send "look"
extras/skills/hhg-shakedown/scripts/hhg_session.py read --tail 30

# "show me everything since the last `look`"
extras/skills/hhg-shakedown/scripts/hhg_session.py since "look"

# Always stop cleanly at the end of the session
extras/skills/hhg-shakedown/scripts/hhg_session.py stop
```

**Run `start` with `Bash run_in_background: true`** — the harness is a long-running daemon and won't return until `stop`.

If `read` shows `[harness] error:`, the SSH connection probably dropped. Run `status`. If "not running", restart with `start --reset` and note the disconnect in `BUGS.md` if it looks like a real engine crash.

### Canonical HHG opener

HHG's `GO` routine (`misc.zil:179`) sets the player in BEDROOM as Arthur, lying down, with three queued startup daemons (`I-HOUSEWRECK` at 20 ticks, `I-THING` at 21, `I-VOGONS` at 50). The first puzzle is escaping the bedroom before the bulldozers arrive at tick 20.

The opening sequence to verify after each regen:

1. `look` — bedroom description (washbasin, chair, dressing gown, window, phone)
2. `examine gown` — should mention pockets
3. `take aspirin` — needed to cure HEADACHE flag
4. `south` (or `out`) — exit bedroom toward front porch
5. `look` — front porch (description should branch on IDENTITY-FLAG)
6. (~20 ticks elapse) — `I-HOUSEWRECK` interrupt fires; bulldozer arrives

If any of these fail, that's the first wall to investigate.

### Bug-logging workflow

Trigger conditions — log to `BUGS.md` if you see any of:

- `Traceback` / `SyntaxError` / `AttributeError` / `PermissionError` in a server response
- A canonical HHG command rejected as `I don't know how to do that` (cross-reference `references/known-quirks.md` first)
- A room missing an exit its description claims
- A verb returning blatantly wrong text (e.g., the bedroom returns Arthur's response when IDENTITY-FLAG isn't Arthur)
- Hint-named objects unresolvable by the parser (the global-scenery class of bug)
- The connection drops without you sending `@quit`
- The protagonist-identity machinery breaks (Ford branch dispatches as Arthur, or vice versa)

When one fires:

1. **Grep first.** Check both `BUGS.md` and `references/known-quirks.md` — if already there, just `[x]` the existing checkbox if it's still reproducible.
2. **Append a new entry at the top of `BUGS.md`** in this format:

   ```markdown
   - [ ] **<one-line summary>** (room: `<Room Name>`, command: `<command>`, identity: `<arthur|ford|trillian|zaphod>`)
     - **Response**: `<verbatim, trimmed to 5 lines max>`
     - **Hypothesis**: <1-2 sentence guess: translator? generator? bootstrap state? IDENTITY-FLAG seed? sandbox? parser?>
     - **Workaround**: <what you did to keep moving>
   ```

3. **Don't try to fix it during shakedown.** Workaround and continue. Fixing is Mode 2.
4. **Don't restart the session for every bug.** Bugs are more useful in the context of a long session.

### Coverage workflow

`references/coverage.md` is the master to-do list. Walk it section by section:

1. **Bedroom escape first.** The opening sequence above. Each successful step ticks a box. This is the "smoke test" until a proper one exists.
2. **Front porch / outside.** Verify the IDENTITY-FLAG branches print the right description.
3. **Bulldozer interrupt.** Wait the 20 ticks (or check daemon scheduling); verify the demolition fires.
4. **Vogon Hold and Heart of Gold.** Later-game rooms; require state machines to have stepped through prior events.

After every ~30 commands, glance at `coverage.md` and tick anything you've completed (only what you've actually verified).

### Session shape

- **Length**: 100-300 commands for HHG (game is denser per-room than Zork; fewer commands cover more state).
- **Cadence**: send → read → think → send. One command per turn unless chaining obvious-success steps.
- **Periodic summary**: every ~30 commands, write a one-paragraph status to chat.

### End-of-session deliverables

Before stopping the session:

1. Tick the right boxes in `coverage.md`.
2. Make sure `BUGS.md` is current — every bug has an entry; hypotheses are filled in.
3. One-paragraph chat summary: rooms reached, identities tried, top 3 most-impactful bugs found, % coverage ticked.
4. `stop` the session.

If a `BUGS.md` item turns out to be already-known, move it to `known-quirks.md`.

## Mode 2 — Fix (translator/generator/SDK)

No HHG-specific smoke test exists yet; we use the opener (above) as the smoke until a proper one lands.

### Before you start

1. Read [references/rule-zero.md](references/rule-zero.md) — the prohibition list and anti-patterns already committed and reverted.
2. Read [HHG-FEASIBILITY.md](HHG-FEASIBILITY.md) — what the feasibility scan landed; the Bucket A bugs already fixed.
3. Read [references/completed-work.md](references/completed-work.md) — what landed in `moo/zil_import/`. Don't re-do these.
4. Read [BUGS.md](BUGS.md) — open bugs.
5. Read [references/smoke-workflow.md](references/smoke-workflow.md) — how to regen, sync, and interpret failures.
6. Skim `moo/zil_import/AGENTS.md` for the importer's design rules.

### The work loop

1. **Pick one failure.** Cascading failures often share a root cause (e.g., IDENTITY-FLAG being None nukes every identity-conditional branch).
2. **Locate the cause.**
   - Translator gaps → `moo/zil_import/translator/`
   - Generator emit bugs → `moo/zil_import/generator/`
   - HHG-specific overrides → `moo/zil_import/verbs/hhg/` (parallel to `verbs/zork1/`)
   - World-state init → `moo/zil_import/scripts/_hhg_reset_state_body.py`
3. **Edit only inside `moo/zil_import/`.** If you can't see how to fix without touching moo-core, **stop and ask** — don't paper over the gap.
4. **Regen + sync.** See [smoke-workflow.md](references/smoke-workflow.md).
5. **Drive the opener** through the connected harness to verify.

### Investigating a failure

Look at the response text:

- **"I don't know how to do that."** — parser couldn't dispatch. Either the verb isn't registered, the dobj isn't resolved, or `--dspec` rejects the sentence shape.
- **"You can't go that way."** — `walk` SDK couldn't find a matching exit.
- **Wrong identity branch** — `player.zstate_get('IDENTITY-FLAG')` is returning None (initial seed missing) or wrong Object (set somewhere it shouldn't be).
- **Traceback / "An error occurred while executing the command."** — verb body errored. Look at the file path and line in the traceback.

## When something can't be solved without core changes

If a translation gap genuinely requires a moo-core change:

1. **Stop work on it.**
2. Move the bug from `BUGS.md` to `TODO.md` with: what the gap is, why no game-side workaround exists, what minimal core API would close it.
3. Present the writeup to the user. **Do not edit moo-core preemptively.**
4. Wait for explicit approval.

## Risks

1. **State pollution.** Each shakedown session changes the world. Always `--reset` at start.
2. **Stale SSH sessions.** If you crash the harness without `stop`, the server-side session lingers. Always `stop` cleanly.
3. **Connection drop loops.** If `start` succeeds but the next `send` returns `[harness] error: EOF`, the server is in trouble. Don't hammer it — stop, check `docker logs --tail 50 django-moo-shell-1`, escalate to the user.
4. **Scope creep.** If a puzzle takes more than 5 turns to figure out, log it as a bug and move on.
5. **Cross-game regressions.** Many fixes live in shared translator/generator code. After any such change, re-run the zork1 smoke at `moo/zil_import/scripts/zork1_smoke.py` to confirm no regression on Zork's pass count.

## Memory entries that govern this work

- `feedback_zil_translator_no_core_changes` — Rule Zero (no moo-core changes for ZIL).
- `feedback_zil_importer_game_agnostic` — keep `moo/zil_import/` game-neutral.
- `feedback_smoke_tee` — always `tee /tmp/smoke.out` so re-inspection is a `grep`, not a re-run.
- `feedback_docker_compose_never_down` — postgres has no named volume. Use `docker exec`, never `down`.
