---
name: zorkzero-shakedown
description: Scaffold for a future Zork Zero (The Revenge of Megaboz) ZIL→DjangoMOO port. Zork Zero is a YZIP-era title the importer does not yet translate — this skill is a placeholder until the importer is extended. Use when the user asks to assess Zork Zero feasibility or begin extending the importer for YZIP. Read ZORKZERO-FEASIBILITY.md first.
compatibility: Designed for Claude Code. Requires the django-moo repository and the moo-agent extension. NOTE — no zorkzero bootstrap has been generated; the importer targets the classic EZIP family and has not been validated against YZIP titles.
---

# Zork Zero Shakedown (scaffold-only)

> ⚠️ **This skill is a placeholder.** No `moo/bootstrap/zorkzero/` dataset has
> been generated. Zork Zero (`zork0.zil`, `<VERSION YZIP>`) is a later
> Z-machine generation than the EZIP-family titles the importer was built for
> (Zork 1/2/3) and validated on (HHG). A real port requires first extending
> `moo/zil_import/` to handle YZIP — that work has not started.
>
> **Before doing anything here, read [ZORKZERO-FEASIBILITY.md](ZORKZERO-FEASIBILITY.md).**

## What exists today

- `ZORKZERO_CONFIG` stub in `moo/zil_import/game_config.py` (banner, manifest
  `zork0.zil`, license blurb). NPC maps and truncation tables are empty.
- This skill tree, mirroring the active shakedown skills, so that once the
  importer supports YZIP the find→fix loop is ready to use.
- A shared session harness wrapper at `scripts/zorkzero_session.py` (works
  the moment a `zorkzero.local` site exists — but there's nothing to connect
  to until a bootstrap is generated).

## What's blocked

- **Regen.** `uv run python -m moo.zil_import zork0.zil --game-config
  zorkzero` is expected to fail or produce a broken dataset until the importer
  models YZIP's parser/syntax/object-table differences. Do not attempt a real
  port casually — capture findings in the feasibility doc instead.

## When the user wants to proceed

1. Read [ZORKZERO-FEASIBILITY.md](ZORKZERO-FEASIBILITY.md).
2. Run a single throwaway regen to capture concrete failures into that doc.
3. Scope the importer changes (all game-neutral, in `moo/zil_import/`) and
   present them — **Rule Zero still applies**: no django-moo core edits. See
   [../_shared/references/rule-zero.md](../_shared/references/rule-zero.md).
4. Once a bootstrap generates, this skill converts to a full shakedown skill
   patterned on `zork2-shakedown` (Mode 1 find / Mode 2 fix), using
   [../_shared/references/smoke-workflow.md](../_shared/references/smoke-workflow.md)
   with `<slug>` = `zorkzero`.

## Files in this skill

| File | Purpose |
|---|---|
| `ZORKZERO-FEASIBILITY.md` | The YZIP-gap assessment. Start here. |
| `BUGS.md` / `TODO.md` / `FEATURES.md` | Empty placeholders for the future port. |
| `references/coverage.md` | Scaffold-only note. |
| `references/known-quirks.md` / `completed-work.md` | Empty placeholders. |
| `scripts/zorkzero_session.py` | Shared-harness wrapper (unusable until a bootstrap + site exist). |
