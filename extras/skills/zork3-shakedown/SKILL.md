---
name: zork3-shakedown
description: End-to-end ZIL→DjangoMOO debugging skill for Zork III (The Dungeon Master). Drive zork3.local through MooSSH to find translator/server bugs, OR pick a known failure and fix it inside moo/zil_import/ (translator/generator/SDK/config). Use when the user asks to shake down Zork III, raise its smoke pass count, debug a zork3 failure, or close a translation gap for Zork III. Read ../_shared/references/rule-zero.md before any edit under moo/.
compatibility: Designed for Claude Code. Requires the django-moo repository, a running docker-compose stack, the moo-agent extension installed (provides moo.bootstrap.zork3), Zork III ZIL source at /Users/philchristensen/Workspace/zork3/, and the zork3.local Site initialised.
---

# Zork III Shakedown

The full Zork III debugging loop: **find** bugs by playing the canonical
world, then **fix** them inside `moo/zil_import/` and verify with the smoke
harness. One skill, two modes. Patterned after `zork-shakedown` — Zork III is
the same classic-engine family as Zork 1, so the translator/generator and the
diagnosis vocabulary are shared; this skill captures the Zork-II-specific
findings.

## Where files live

- **moo-agent** is the working directory. The Zork III dataset
  (`moo/bootstrap/zork3/`, gitignored generated output), the ZIL importer
  (`moo/zil_import/`), and this skill all live here.
- **Zork III ZIL source** is at `/Users/philchristensen/Workspace/zork3/`.
  Manifest is `zork3.zil` (`<INSERT-FILE>` pulls in `3dungeon.zil`,
  `3actions.zil`, and the shared `g*.zil` parser files). `ZORK-NUMBER` is 3.
- **django-moo** is the engine repo (`moo/core/`, `moo/sdk/`, `moo/shell/`,
  `moo/bootstrap/__init__.py`, `moo/bootstrap/default/`) — off-limits for
  fitting game-specific bugs (Rule Zero).

Both repos contribute to the `moo.*` namespace package, so
`moo.bootstrap.zork3` resolves regardless of working directory.

## 🛑 RULE ZERO — READ BEFORE EVERY EDIT IN `moo/`

**DO NOT MODIFY `moo/` (OUTSIDE `moo/bootstrap/zork3/`) TO MAKE THE ZORK II BOOTSTRAP WORK.**

Another violation ends the collaboration. Every translation gap is solved
inside `moo/zil_import/` (game-neutral translator/generator/IR), in
`game_config.py` (the `ZORK3_CONFIG` knobs), in `moo/zil_import/verbs/zork3/`
(per-game overrides), or in the System Object's `do_command` verb. The full
anti-pattern catalog is [../_shared/references/rule-zero.md](../_shared/references/rule-zero.md)
— read it first.

If you're about to edit `moo/core/`, `moo/sdk/`, `moo/shell/`,
`moo/bootstrap/__init__.py`, or `moo/bootstrap/default/`, **stop and ask**.
Default answer: no. Also keep `moo/zil_import/` itself game-neutral — Zork-II
specifics belong in `game_config.py` / `verbs/zork3/`, never hardcoded into
the importer.

## ✍️ This skill is self-updating

Every session, end by updating this skill's files with what you learned:

- New failure mode found via shakedown → [BUGS.md](BUGS.md).
- Bug needing a moo-core change → [TODO.md](TODO.md) with the rationale.
- Translator/generator/SDK/config fix that landed → [references/completed-work.md](references/completed-work.md).
- Pre-existing limitation surfaced → [references/known-quirks.md](references/known-quirks.md).
- A new game-side mechanic mapped → [FEATURES.md](FEATURES.md) / [references/coverage.md](references/coverage.md).

## Files in this skill

| File | Purpose |
|---|---|
| `BUGS.md` | Open bugs found via shakedown. Newest first. |
| `TODO.md` | Bugs deferred because they need a moo-core change. |
| `FEATURES.md` | Zork-II-specific mechanics to exercise. |
| `references/coverage.md` | Master room/verb/probe checklist. Tick when verified. |
| `references/known-quirks.md` | Pre-existing limitations; don't re-report. |
| `references/completed-work.md` | Fixes that landed + smoke-progress table. |
| `scripts/zork3_session.py` | Thin wrapper around the shared MooSSH harness. |
| `../_shared/references/rule-zero.md` | The no-moo-core-edits constraint. Read first. |
| `../_shared/references/smoke-workflow.md` | Regen + sync + smoke + spot-test loop. |

## Mode 1 — Shakedown (find bugs)

You are a Zork III player who happens to be a MOO engine debugger. Drive
**one** SSH session open from start to finish.

```bash
# Always include --reset for a fresh session.
extras/skills/zork3-shakedown/scripts/zork3_session.py start --reset
extras/skills/zork3-shakedown/scripts/zork3_session.py send "look"
extras/skills/zork3-shakedown/scripts/zork3_session.py read --tail 30
extras/skills/zork3-shakedown/scripts/zork3_session.py since "look"
extras/skills/zork3-shakedown/scripts/zork3_session.py stop
```

**Run `start` with `Bash run_in_background: true`** — it's a long-running
daemon and won't return until `stop`. If `read` shows `[harness] error:`, the
SSH connection probably dropped — run `status`, restart with `start --reset`,
and note a real engine crash in `BUGS.md`.

### Canonical Zork III opener

Zork III famously opens with the player falling through darkness onto the
Endless Stair, carrying nothing. The first session should map the actual
opening room and exits from `3dungeon.zil` and tick them into
`references/coverage.md` — Zork III's map and starting inventory are unlike
either prior game, so don't assume the West-of-House sequence.

### Bug-logging workflow

Log to `BUGS.md` (newest at top) on any of: `Traceback` / `SyntaxError` /
`AttributeError` / `PermissionError` in a response; a canonical command
rejected as `I don't know how to do that` (grep `known-quirks.md` first); a
room missing an exit its description claims; a verb returning blatantly wrong
text; hint-named objects the parser can't resolve; an unprompted connection
drop; a score increment that fires wrong. Use the entry format in
[../zork-shakedown/BUGS.md](../zork-shakedown/BUGS.md). Don't fix during
shakedown — workaround and continue; don't restart per bug.

## Mode 2 — Fix (translator/generator/SDK/config)

The smoke test (`moo/zil_import/scripts/zork3_smoke.py`) drives a canonical
command sequence and reports pass/total. Closing that gap is the metric.

### Before you start

1. Read [../_shared/references/rule-zero.md](../_shared/references/rule-zero.md).
2. Read [references/completed-work.md](references/completed-work.md) — don't re-do landed fixes.
3. Read [BUGS.md](BUGS.md) — open bugs with game-side fix paths.
4. Read [../_shared/references/smoke-workflow.md](../_shared/references/smoke-workflow.md) — the regen/sync/smoke loop (substitute `<slug>` = `zork3`).
5. Skim `moo/zil_import/AGENTS.md` for the importer's design rules.

### The work loop

1. **Pick one failure category.** Cascading failures often share a root cause.
2. **Locate the cause.** Most live in `moo/zil_import/translator/` (verb-body
   emission), `moo/zil_import/generator/` (bootstrap layout), `game_config.py`
   (`ZORK3_CONFIG` — NPC atom map, synonym/adjective 6-char truncations,
   exit-condition overrides), or `moo/zil_import/verbs/zork3/` (runtime shims).
3. **Edit only inside the allowed surface.** Can't fix without core? Stop and ask.
4. **Regen + sync** (see smoke-workflow.md):
   `uv run python -m moo.zil_import ~/Workspace/zork3/zork3.zil --game-config zork3 --output .../moo-agent/moo/bootstrap/zork3`
   then `moo_init --bootstrap zork3 --sync --hostname zork3.local`.
5. **Spot-test** with `zork3_spot.py`, then run the full `zork3_smoke.py`.
6. **Cross-check the zork1 smoke** after any shared translator/generator
   change — many fixes live in shared code and can regress Zork 1.

## When something needs a core change

Stop work on it, move the bug from `BUGS.md` to `TODO.md` with the gap, why no
game-side workaround exists, and the minimal core API that would close it.
Present it; wait for explicit approval. Do not edit core preemptively.

## Memory entries that govern this work

- `feedback_zil_translator_no_core_changes` — Rule Zero.
- `feedback_zil_importer_game_agnostic` — keep `moo/zil_import/` game-neutral.
- `feedback_zil_verbs_organized_by_owner` — verb-tree layout convention.
- `feedback_smoke_tee` — always `tee /tmp/smoke.out`.
- `reference_site_pk_layout` — which Site PK is `zork3.local`.
