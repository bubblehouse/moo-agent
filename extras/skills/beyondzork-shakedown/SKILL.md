---
name: beyondzork-shakedown
description: Scaffold for a future Beyond Zork (The Coconut of Quendor) ZIL→DjangoMOO port. Beyond Zork is an XZIP-era title the importer does not yet translate — this skill is a placeholder until the importer is extended. Use when the user asks to assess Beyond Zork feasibility or begin extending the importer for later Z-machine versions. Read BEYONDZORK-FEASIBILITY.md first.
compatibility: Designed for Claude Code. Requires the django-moo repository and the moo-agent extension. NOTE — no beyondzork bootstrap has been generated; the importer targets the classic EZIP family and has not been validated against XZIP/YZIP titles.
---

# Beyond Zork Shakedown (scaffold-only)

> ⚠️ **This skill is a placeholder.** No `moo/bootstrap/beyondzork/` dataset has
> been generated. Beyond Zork (`beyond.zil`, `<VERSION XZIP>`) is a later
> Z-machine generation than the EZIP-family titles the importer was built for
> (Zork 1/2/3) and validated on (HHG). A real port requires first extending
> `moo/zil_import/` to handle XZIP — that work has not started.
>
> **Before doing anything here, read [BEYONDZORK-FEASIBILITY.md](BEYONDZORK-FEASIBILITY.md).**

## What exists today

- `BEYONDZORK_CONFIG` stub in `moo/zil_import/game_config.py` (banner, manifest
  `beyond.zil`, license blurb). NPC maps and truncation tables are empty.
- This skill tree, mirroring the active shakedown skills, so that once the
  importer supports XZIP the find→fix loop is ready to use.
- A shared session harness wrapper at `scripts/beyondzork_session.py` (works
  the moment a `beyondzork.local` site exists — but there's nothing to connect
  to until a bootstrap is generated).

## What's blocked

- **Regen.** `uv run python -m moo.zil_import beyond.zil --game-config
  beyondzork` is expected to fail or produce a broken dataset until the importer
  models XZIP's parser/syntax/object-table differences. Do not attempt a real
  port casually — capture findings in the feasibility doc instead.

## When the user wants to proceed

1. Read [BEYONDZORK-FEASIBILITY.md](BEYONDZORK-FEASIBILITY.md).
2. Run a single throwaway regen to capture concrete failures into that doc.
3. Scope the importer changes (all game-neutral, in `moo/zil_import/`) and
   present them — **Rule Zero still applies**: no django-moo core edits. See
   [../_shared/references/rule-zero.md](../_shared/references/rule-zero.md).
4. Once a bootstrap generates, this skill converts to a full shakedown skill
   patterned on `zork2-shakedown` (Mode 1 find / Mode 2 fix), using
   [../_shared/references/smoke-workflow.md](../_shared/references/smoke-workflow.md)
   with `<slug>` = `beyondzork`.

## Files in this skill

| File | Purpose |
|---|---|
| `BEYONDZORK-FEASIBILITY.md` | The XZIP-gap assessment. Start here. |
| `BUGS.md` / `TODO.md` / `FEATURES.md` | Empty placeholders for the future port. |
| `references/coverage.md` | Scaffold-only note. |
| `references/known-quirks.md` / `completed-work.md` | Empty placeholders. |
| `scripts/beyondzork_session.py` | Shared-harness wrapper (unusable until a bootstrap + site exist). |
