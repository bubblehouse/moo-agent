# Multi-Game ZIL Porting Plan

Bring three more ZIL games into DjangoMOO alongside `zork1` and `hhg`:
**zork2, zork3, beyondzork**. Scaffold all three; drive **zork2**
to a working bootstrap now. Created 2026-06-04. (Zork Zero was dropped on
2026-06-06 — its v6/YZIP bitmap engine is out of scope for the foreseeable
future.)

## Decisions (locked)

- **Shared parameterized session harness** — one core module, thin per-game
  wrappers. No more byte-for-byte 290-line copies.
- **beyondzork: scaffold + feasibility only.** It is XZIP (Z-machine v5):
  character-cell display (colored text + a split-screen stats/map window) plus
  an RPG layer and a custom parser. No regen attempt yet — mirrors how HHG
  began with `HHG-FEASIBILITY.md`. See `beyondzork-shakedown/BEYONDZORK-FEASIBILITY.md`.

## Source survey

| Game | Manifest | ZORK-NUMBER | Z-machine | Files | Risk |
| --- | --- | --- | --- | --- | --- |
| zork2 | `zork2.zil` | 2 | EZIP (classic) | 11 | Low — **focus** |
| zork3 | `zork3.zil` | 3 | classic | 21 | Low–medium |
| beyondzork | `beyond.zil` | (none) | XZIP (v5) | 14 | High |

Manifests confirmed via `<INSERT-FILE>` scan. `ZORK-NUMBER` confirmed via
`<SETG ZORK-NUMBER n>` grep. Sources live at `~/Workspace/<game>/`.

## Architecture recap (where things plug in)

All edits are in **moo-agent**; django-moo core is off-limits (Rule Zero).

1. **`moo/zil_import/game_config.py`** — add a `GameConfig` per game,
   register in `GAME_CONFIGS`. Game-agnostic translator/generator read it
   at runtime.
2. **Regen** — `uv run python -m moo.zil_import <manifest.zil> --game-config
   <slug> --output moo/bootstrap/<slug>` (output gitignored, PEP-420
   discovered). Per-game verb overrides: `moo/zil_import/verbs/<slug>/`.
   Reset body: `moo/zil_import/scripts/_<slug>_reset_state_body.py`.
3. **`moo_init --bootstrap <slug> --hostname <slug>.local`** (first run),
   `--sync` after. New Site PK per game; fix `phil` Player avatar→Wizard.
4. **Skill** — `extras/skills/<slug>-shakedown/`.

## Phase 0 — Shared scaffolding (low risk, big payoff)

- [ ] `extras/skills/_shared/moo_session.py` — parameterized session
  harness. Single `--slug <game>` arg derives everything:
  `host=localhost`, `port=8022`, `user=phil+<slug>.local`,
  `hostname=<slug>.local`, `bootstrap=<slug>`, paths `/tmp/<slug>-shakedown.*`.
  Lifted verbatim from `zork_session.py` with the 6 hardcoded values
  parameterized. Keeps the FIFO loop, `--reset` (celery-stop-during-sync),
  `send`/`read`/`since`/`stop`/`status` subcommands unchanged.
- [ ] Per-skill wrapper `scripts/<slug>_session.py` — 3-line shim that
  imports the shared core with the slug baked in (so the SKILL.md command
  examples still read naturally).
- [ ] `extras/skills/_shared/references/rule-zero.md` and
  `smoke-workflow.md` — game-neutral references; per-skill SKILL.md links
  here instead of carrying copies. Per-game `coverage.md`,
  `known-quirks.md`, `completed-work.md` stay local to each skill.
- [ ] **Do NOT** refactor the existing 893-line `zork1_smoke.py` /
  486-line `hhg_smoke.py` now. Instead add a small `_smoke_base.py`
  (connect + reset + walk + report) for the new games' opener-smokes.
  Retrofit zork1/hhg onto it later — tracked as a follow-up, not in scope.

## Phase 1 — GameConfig stubs for all three

- [ ] Add `ZORK2_CONFIG`, `ZORK3_CONFIG`, `BEYONDZORK_CONFIG` to
  `game_config.py` and register in `GAME_CONFIGS`.
  Minimum viable fields: `name`, `dataset_name`, `banner`,
  `manifest_files`, `license_blurb`, `zork_number` (2/3 for the zorks;
  leave default for beyondzork). NPC atom maps + synonym/adjective
  truncation maps start empty and get populated during shakedown.

## Phase 2 — Skill trees for all three

For each `<slug>` in {zork2, zork3, beyondzork}:

- [ ] `extras/skills/<slug>-shakedown/SKILL.md` — cloned from
  `zork-shakedown/SKILL.md`, retargeted (game name, `<slug>.local`,
  bootstrap name, opener sequence). Links shared rule-zero + smoke-workflow.
- [ ] Empty `BUGS.md`, `TODO.md`, `FEATURES.md`.
- [ ] `references/coverage.md`, `known-quirks.md`, `completed-work.md`
  (seeded, mostly empty).
- [ ] `scripts/<slug>_session.py` wrapper (Phase 0).
- [ ] beyondzork only: `BEYONDZORK-FEASIBILITY.md` with the v5/XZIP
  writeup and an explicit "no regen attempted yet" note.

## Phase 3 — Drive zork2 to a working bootstrap

- [ ] Populate `ZORK2_CONFIG` NPC atom map + avatar atoms by scanning
  `2dungeon.zil` / `2actions.zil` (e.g. the Wizard of Frobozz, the demon,
  the dragon, the princess).
- [ ] Regen: `uv run python -m moo.zil_import ~/Workspace/zork2/zork2.zil
  --game-config zork2 --output .../moo-agent/moo/bootstrap/zork2`.
- [ ] `moo_init --bootstrap zork2 --hostname zork2.local`; record assigned
  Site PK in the `reference_site_pk_layout` memory.
- [ ] Fix `phil` Player avatar→Wizard on the new site (snippet in
  smoke-workflow.md).
- [ ] `_zork2_reset_state_body.py` + opener-smoke + spot script.
- [ ] Run the find→fix loop on the opening sequence until clean; capture
  synonym/adjective 6-char truncations into `ZORK2_CONFIG` as they surface.
- [ ] Cross-check zork1 smoke after any shared translator/generator change
  (no regression).

## Phase 4 — zork3 trial regen (light)

- [ ] One regen pass from `zork3.zil` to capture a baseline + gap list in
  zork3's `completed-work.md` / `BUGS.md`. Not driven to completion now.

## Risks / notes

- **Later-Z-machine unknowns.** The importer was built for v3-era ZIL
  (zork1) and validated on hhg. zork2/zork3 are the same classic family and
  should behave like zork1. beyondzork is XZIP (v5) — expect parser/syntax
  forms the importer doesn't model, plus an RPG layer and a split-screen
  display. Feasibility-only until we choose to invest.
- **Site PK drift.** Memory `reference_site_pk_layout` says 1–4 are taken
  (1 example.com, 2 zork1.local, 3 default, 4 hhg.local). New games take
  5+. Update that memory after each `moo_init`.
- **Don't touch django-moo core.** Every gap → `moo/zil_import/` or
  `verbs/<slug>/` or System Object `do_command`. If a fix seems to need
  core, stop and ask (TODO.md).
