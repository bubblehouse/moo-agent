# Zork III — Completed work

Translator/generator/SDK/config fixes that landed for Zork III. Don't re-do these;
build on them. Mirrors `../../zork-shakedown/references/completed-work.md`.

## Landed fixes

### 2026-06-06 — smoke + spot harness created

Added `moo/zil_import/scripts/zork3_smoke.py` (assertion-driven canonical
opener, 23 commands) and `zork3_spot.py` (verbatim-output spot tool), both
cloned from the zork2 equivalents. The smoke walks a single continuous path
threading both shakedown branches: western spur (Junction → Barren Area →
Cliff, embedded-sword special case, verified reverse exits) then the southern
dungeon (Creepy Crawl → Tight Squeeze → Crystal Grotto → Land of Shadow →
Foggy Room → Lake Shore → Aqueduct View). Asserts the connect banner, lit
opener, `inventory`/`diagnose`/`score`/`examine`/`wait`, the `take sword`
refusal, a blocked-exit fail-probe (`down` at Endless Stair), and the
canonical `swim` refusal. **PASS (23/23), reproducible across two runs.**
Both self-reset via `moo_init --sync` (Celery stopped for the txn).

### 2026-06-06 — second shakedown (deferred-bug cleanup)

1. **`diagnose` shim for zork3**
   (`moo/zil_import/verbs/zork3/actor/diagnose.py`, `--on "Actor" --dspec
   none`). `V-DIAGNOSE` is in the translator's global `_SKIP_ROUTINES`, so no
   verb was generated. zork3's V-DIAGNOSE is NOT zork1's C-TABLE health math
   — it's `<TELL <GET ,DIAG ,P-STRENGTH> CR>`, one lookup into the 6-entry
   `DIAG` string table. On the MOO side: `DIAG` → `zstate_diag` list on the
   System Object (`035_tables.py`), `P-STRENGTH` → `player.zstate_get(...)`
   (opens at 5). Shim reads strength (default 5), `_.table_get(zstate_diag,
   strength)`, prints it. Verified live → "You are in perfect health."

2. **Daemon-sweep log mislabel** (`generator/__init__.py:_gen_daemons`).
   The emitted `050_daemons.py` logged a hardcoded `'zork1 realtime daemons:
   swept …'` for every game. Made game-neutral: `'realtime daemons: swept %d
   stale PT row(s)'`. (`_gen_daemons` takes no `cfg`, so dropping the word
   was the minimal game-agnostic fix.) Pure log string — zero gameplay
   impact, so the zork1 smoke cross-check was skipped; 223 importer unit
   tests pass.

### 2026-06-05 — inaugural bootstrap + first shakedown

1. **`reset_body_filename` for zork3** (`game_config.py` +
   `moo/zil_import/scripts/_zork3_reset_state_body.py`). `ZORK3_CONFIG` had
   no `reset_body_filename`, so it fell back to the default
   `_reset_state_body.py` — *zork1's* body — which the generator copied into
   `moo/bootstrap/zork3/099_reset_state.py`. That body hardcodes
   `zork1.local`, restores the zork1 snapshot, and calls
   `ContextManager.set_site(zork1_site)`. Since `099_reset_state.py` is a
   numbered script it runs during `moo_init` **before** `load_verbs`, leaving
   the SiteManager pinned to site 2 (zork1) for the entire verb load. Result:
   every `--on` lookup resolved against zork1's objects, and the first verb
   whose owner only exists in zork3 (`man_f.py` → `--on "man (MAN)"`) crashed
   with `Object.DoesNotExist`. Fix mirrors zork2: dedicated reset body
   hardcoding `zork3.local`, snapshot path `zork3-site-{pk}.json`, start room
   "Endless Stair" (ZIL `ZORK2-STAIR`), `zstate_always_lit/_lit=True`,
   `strength=0`, the substrate `everyone:write` grant loop. Dropped zork2's
   carousel-flag and lamp/sword seeds (Zork III opens carrying nothing).

2. **`clocker` shim for zork3**
   (`moo/zil_import/verbs/zork3/thing/helpers/clocker.py`). `wait` crashed
   with `Thing has no attribute clocker`: V-WAIT's translated body loops
   `_.thing.clocker()` (ZIL `<CLOCKER>`), but `CLOCKER` is a global routine
   in the Z-machine clock machinery the importer replaces with
   `zil_sdk/queue_sdk.py:tick`. zork1/hhg supply a per-game `clocker` shim;
   zork3 had none. Added the no-early-break variant (cloned from zork1):
   `_.tick(); return False`.

## Smoke progress

| Date | Pass / Total | Score | Notes |
| --- | --- | --- | --- |
| 2026-06-05 | — (no smoke script yet) | 0/7, 11 moves | Inaugural live shakedown via the SSH harness. Canonical opener clean: Endless Stair → Junction (sword-in-rock special-case works) → Barren Area → Cliff (rope/precipice), all exits + reverse exits correct. `look`/`inventory`/`examine`/`take`/movement/`score`/`wait` all good after fixes. No `zork3_smoke.py` exists yet — build one (clone `zork2_smoke.py`) for Mode-2 work. |
| 2026-06-06 | **23/23** (`zork3_smoke.py`) | 0/7 | First assertion-driven smoke — canonical opener walk, all 23 commands pass, reproducible. |
| 2026-06-06 | — (manual) | 0/7 | Second live shakedown, southern/eastern dungeon. `diagnose`+`wait` fixes verified in-session. Walked Endless Stair → Junction → Creepy Crawl → Tight Squeeze → Crystal Grotto → (back) → Land of Shadow → Foggy Room → Lake Shore → Aqueduct View. All descriptions/exits clean; multi-word + preposition parsing OK (`enter lake`, `examine hooded figure`); `swim`→"Go jump in a lake!". **Zero tracebacks in the celery log all run.** Hooded-figure (alias `figure`, "hooded figure") did NOT materialise in the Land of Shadow — its appearance daemon is turn-gated; driving it is next run's target. |

Add a row each session.
