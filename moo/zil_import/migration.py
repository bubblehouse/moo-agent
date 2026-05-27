"""
Per-verb migration switch for the syntax-row dispatcher refactor.

When a verb atom is in :data:`MIGRATED_VERBS` the generator emits its
syntax-row file (from ``templates/syntax_row.py.j2``) and the V-* helper
under ``verbs/thing/v_routines/`` becomes the active dispatch target.
Verbs not in the set continue through the legacy per-verb-atom
dispatcher emission at :func:`moo.zil_import.generator.generate_all`.

This module is deleted in Phase 8 when the legacy emission path is
removed; until then, batches roll forward by adding verb atoms here and
gating each addition on a zork1-smoke parity check.
"""

from __future__ import annotations

#: Verb atoms whose dispatch lands on the new syntax-row emitter.
#: Phase 4 starts with single-rule verbs (no compound particles, no
#: prep-iobj variants).  Multi-rule verbs from the originally-planned
#: Batch A (take, drop, look, examine, read, open) require either
#: per-particle parser disambiguation or in-body dispatch logic and
#: land in later phases.
MIGRATED_VERBS: set[str] = {
    # Phase 4 — single-rule intransitive / arity-1 verbs
    "inventory",
    "close",
    # Phase 5 — single-rule arity-2 transitive with iobj_prep.
    # ATTACK is excluded: V-ATTACK is in _SKIP_ROUTINES because the
    # substrate is hand-written under verbs/zork1/thing/substrate_verbs/
    # (per-game override; the auto-translated body leaks SSH usernames
    # via self.desc() on "attack me" / "kill me").
    "lock",
    "unlock",
    # Phase 6 Batch A — single-rule transitive verbs (arity-1, no
    # particle, no iobj_prep).  The syntax-row template's existing
    # per-cell emission Just Works for these.  Skipped from this
    # batch: attack / kill (V-ATTACK in _SKIP_ROUTINES → no v_attack
    # helper); pour / drink (multi-rule with iobj_prep — handled in
    # Batch C).
    "wear",
    "eat",
    "extinguish",
    "smell",
    # Phase 6 Batch B — multi-rule single-particle or near-single-rule
    # verbs.  `_emit_syntax_row_files` emits one file per cell, so a
    # verb like OPEN (bare + ``open up``) gets `open.py` + `open_up.py`.
    # Both invoke the same V-routine — the cell explosion is harmless.
    "open",
    "read",
    "untie",
    "burn",
    "tie",
    # Phase 6 Batch C — iobj_prep multi-rule transitive verbs.  PUT
    # has 7+ rules spanning IN / ON / UNDER / etc.  Each cell becomes
    # one syntax-row file: `put_in.py`, `put_on.py`, `put_under.py`,
    # routing to the matching V-PUT-IN / V-PUT-ON / V-PUT-UNDER helper
    # which the generator already emits as a v_routine helper.
    "put",
    "give",
    "throw",
    "pour",
    "drink",
    # Phase 6 Batch D — complex multi-rule verbs.  TAKE has 5+ rules
    # (bare, ``take all``, ``take all but``, ``take from``); DROP has 4;
    # EXAMINE has 3; LOOK has 10+.  LOOK can compete with room M-LOOK
    # combined-emission aliases (every room's pub_f.py / *_fcn.py
    # registers ``look`` for the M-LOOK branch) — verify smoke + harness
    # carefully.
    "take",
    "drop",
    "examine",
    "look",
}
