# HHG-specific features and their implementation status

HHG has several mechanics that don't appear in Zork I. This file tracks how well the translator and bootstrap handle each one — useful for prioritising shakedown probes and surfacing translation gaps.

## Multi-POV identity switching (`IDENTITY-FLAG`)

HHG's `GO` routine (`misc.zil:179`) seeds `IDENTITY-FLAG` to `ARTHUR`. Throughout the game, various puzzles swap the protagonist (`IDENTITY-FLAG := FORD`, `TRILLIAN`, `ZAPHOD`). Verb bodies branch on the current identity to print character-specific text.

- **Initial seed**: handled by `moo/zil_import/scripts/_hhg_reset_state_body.py` (sets `identity_flag → lookup("Arthur")`).
- **Mid-game switches**: ZIL emits `<SETG IDENTITY-FLAG ,FORD>`; the translator turns these into `player.zstate_set('identity_flag', lookup("Ford"))`. ✅ **VERIFIED LIVE 2026-06-04 — all three** (Ford, Trillian, Zaphod) triggered through the dream-Dark and confirmed in state. No translation fix needed. See coverage.md "Multi-POV switches" + completed-work 2026-06-04 for the full mechanism + reproduction recipe.
- **Conditional dispatch**: ZIL `<COND (<EQUAL? ,IDENTITY-FLAG ,FORD> …)>` becomes `if player.zstate_get('IDENTITY-FLAG') == lookup('ford'):`. ✅ Exercised 2026-06-04 — e.g. COUNTRY-LANE M-LOOK's "your home" (Arthur) vs "Arthur's home" (Ford) branch fires correctly post-switch.

## Startup daemons

`GO` queues three real-time interrupts:

- `I-HOUSEWRECK` at 20 ticks (Earth demolition crew arrives)
- `I-THING` at 21 ticks
- `I-VOGONS` at 50 ticks

These need to be enqueued by the reset script. The daemon classifier (`moo/zil_import/translator/daemon_modes.py`) decides realtime vs. turn-based scheduling.

## Babel fish puzzle

The Babel fish is HHG's most-celebrated puzzle. Multi-step state machine with several object dependencies. Likely surfaces ZIL idioms the translator hasn't been exercised on. Probe location: Vogon Hold area.

## Improbability drive (Heart of Gold sequences)

Random text substitutions when the drive engages. ZIL uses `<RANDOM>` and table lookups. Probe location: Heart of Gold bridge.

## Coverage status

See [references/coverage.md](references/coverage.md).
