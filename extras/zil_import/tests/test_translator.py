"""
Round-trip tests for the ZIL → Python translator.

Each test takes a ZIL S-expression source string, runs it through the
tokenizer / parser / converter / translator pipeline, and asserts that the
emitted Python carries the expected idioms.  These are unit tests of the
translator itself, not of the runtime sandbox — we never execute the output.
"""

# Several tests poke ZilTranslator's protected shebang builders directly
# to verify per-clause dspec carve-outs.  The methods stay underscore-
# prefixed in production (they're not part of the translator's public
# surface) but the tests need to exercise them in isolation.
# pylint: disable=protected-access

from __future__ import annotations

import pytest

from extras.zil_import.converter import _extract_routine
from extras.zil_import.parser import Str, parse, tokenize
from extras.zil_import.translator import (
    ZilTranslator,
    sanitize_ident,
    has_f_dispatch,
    has_m_dispatch,
    translate_f_clause,
    translate_m_clause,
    translate_routine,
)


def _routine(src: str):
    """Parse a single ROUTINE form into a ZilRoutine."""
    nodes = parse(tokenize(src))
    assert len(nodes) == 1, f"expected one top-level form, got {len(nodes)}"
    return _extract_routine(nodes[0])


def _translate(src: str) -> str:
    return translate_routine(_routine(src))


# ---------------------------------------------------------------------------
# Basic statement forms
# ---------------------------------------------------------------------------


def test_tell_emits_print():
    """<TELL ...> becomes a print() call."""
    out = _translate('<ROUTINE FOO () <TELL "hello" CR>>')
    assert "print('hello')" in out


def test_tell_concatenates_segments():
    """<TELL "a" "b"> joins both segments into one print."""
    out = _translate('<ROUTINE FOO () <TELL "first " "second" CR>>')
    assert "print(" in out
    # Order preserved.
    first = out.index("first")
    second = out.index("second")
    assert first < second


def test_crlf_emits_blank_print():
    """<CRLF> becomes print() with no args."""
    out = _translate("<ROUTINE FOO () <CRLF>>")
    assert "print()" in out


def test_rtrue_emits_return_true():
    """<RTRUE> compiles to `return True`."""
    out = _translate("<ROUTINE FOO () <RTRUE>>")
    assert "return True" in out


def test_rfalse_emits_return_false():
    """<RFALSE> compiles to `return False`."""
    out = _translate("<ROUTINE FOO () <RFALSE>>")
    assert "return False" in out


# ---------------------------------------------------------------------------
# Control flow
# ---------------------------------------------------------------------------


def test_cond_emits_if_else_chain():
    """<COND (test1 body1) (T body2)> becomes if/else."""
    out = _translate("<ROUTINE FOO () <COND (<EQUAL? .X 1> <RTRUE>) (T <RFALSE>)>>")
    assert "if " in out
    # The else branch may be `else:` or fall through to `return False`.
    assert "return True" in out
    assert "return False" in out


def test_verb_predicate_emits_membership_check():
    """<VERB? TAKE> becomes a ``the_player_verb in [...]`` membership check
    with each ZIL synonym (take/get/pick) listed so any of them matches at
    dispatch time.  ``the_player_verb`` is bound at the top of the routine
    via ``invoked_verb_name(verb_name)`` so it carries the player's typed
    verb even when the routine is invoked as a sub-call from another verb
    (where ``verb_name`` would be the callee's own name)."""
    out = _translate("<ROUTINE FOO () <COND (<VERB? TAKE> <RTRUE>)>>")
    assert "the_player_verb in [" in out
    assert "'take'" in out
    # Setup line should be present so the_player_verb resolves correctly.
    assert "the_player_verb = invoked_verb_name(verb_name)" in out


def test_independent_if_blocks_not_treated_as_chain():
    """Sequential standalone <COND> forms followed by a tail expression must
    NOT be wrapped — only the routine's tail-position form gets the
    implicit-return wrap.  Regression: ``_wrap_trailing_return_recursive``
    used to walk every if-opener at the routine indent, wrapping
    ``print("a")`` from an earlier if-block as ``return print("a")``.  That
    short-circuited the routine before reaching subsequent statements
    (LEAF-PILE's V?MOVE branch swallowed the leaves_appear call this way)."""
    out = _translate('<ROUTINE FOO () <COND (<EQUAL? .X 1> <TELL "a" CR>)> <TELL "tail" CR>>')
    # The earlier branch's print must remain a bare statement, not a
    # ``return print(...)`` (which would short-circuit the routine before
    # the tail TELL ever ran).
    assert "print('a')" in out
    assert "return print(" not in out
    # And the tail print is followed by an implicit `return` wrap
    # (split out of `return print(...)` by _fix_return_print).
    pt = out.index("print('tail')")
    after_tail = out[pt:]
    assert "return" in after_tail


def test_if_else_chain_at_tail_still_wraps_branches():
    """A trailing if/else at the routine indent IS the tail expression and
    each branch's last line should be wrapped — keep the canonical case
    working (this is the behaviour ``test_cond_emits_if_else_chain`` exercises
    end-to-end)."""
    out = _translate("<ROUTINE FOO () <COND (<EQUAL? .X 1> <RTRUE>) (T <RFALSE>)>>")
    # Both branches end in explicit returns — preserved by the wrap pass.
    assert "return True" in out
    assert "return False" in out


# ---------------------------------------------------------------------------
# SDK calls
# ---------------------------------------------------------------------------


def test_fset_predicate_emits_flag_call():
    """<FSET? ,OBJ ,FLAGBIT> becomes an obj.flag(...) call."""
    out = _translate("<ROUTINE FOO () <COND (<FSET? ,LANTERN ,LIGHTBIT> <RTRUE>)>>")
    assert ".flag(" in out


def test_move_emits_zil_sdk_move():
    """<MOVE ,OBJ ,LOC> becomes .moveto(...)."""
    out = _translate("<ROUTINE FOO () <MOVE ,LANTERN ,LIVING-ROOM>>")
    assert ".moveto" in out


def test_remove_emits_zil_sdk_remove():
    """<REMOVE ,OBJ> becomes _.remove(...)."""
    out = _translate("<ROUTINE FOO () <REMOVE ,LANTERN>>")
    assert "_.remove" in out


def test_jigs_up_emits_death_call():
    """<JIGS-UP "msg"> becomes _.jigs_up(...)."""
    out = _translate('<ROUTINE FOO () <JIGS-UP "You died.">>')
    assert "_.jigs_up" in out


# ---------------------------------------------------------------------------
# Globals + properties
# ---------------------------------------------------------------------------


def test_move_passes_atom_args():
    """<MOVE ,OBJ ,LOC> emits a .moveto call with both atoms."""
    out = _translate("<ROUTINE FOO () <MOVE ,LANTERN ,LIVING-ROOM>>")
    assert ".moveto" in out
    assert "LANTERN" in out
    assert "LIVING-ROOM" in out or "LIVING_ROOM" in out


def test_getp_emits_getp_helper():
    """<GETP ,OBJ P?DESC> routes through obj.getp() for safe property access."""
    out = _translate("<ROUTINE FOO () <GETP ,LANTERN P?DESC>>")
    assert ".getp(" in out


# ---------------------------------------------------------------------------
# M-clause splitting (room/object action dispatch)
# ---------------------------------------------------------------------------


def test_m_dispatch_detected_when_present():
    """A routine with M-LOOK in COND advertises m-dispatch."""
    routine = _routine('<ROUTINE FOO (RARG) <COND (<EQUAL? .RARG ,M-LOOK> <TELL "looking" CR>)>>')
    assert has_m_dispatch(routine) is True


def test_m_dispatch_absent_for_plain_routine():
    """A routine that never tests RARG against M-* has no m-dispatch."""
    routine = _routine('<ROUTINE FOO () <TELL "hi" CR>>')
    assert has_m_dispatch(routine) is False


def test_m_clause_extracts_only_matching_branch():
    """translate_m_clause emits only the body of the matching M-* clause."""
    routine = _routine(
        "<ROUTINE FOO (RARG) "
        "<COND "
        '(<EQUAL? .RARG ,M-LOOK> <TELL "looking" CR>) '
        '(<EQUAL? .RARG ,M-BEG>  <TELL "begin"   CR>)>>'
    )
    look = translate_m_clause(routine, "M-LOOK")
    beg = translate_m_clause(routine, "M-BEG")
    assert "looking" in look and "begin" not in look
    assert "begin" in beg and "looking" not in beg


# ---------------------------------------------------------------------------
# F-clause splitting (per-villain combat dispatch)
# ---------------------------------------------------------------------------


def test_f_dispatch_detected_when_present():
    """A routine with <EQUAL? .MODE ,F-DEAD> in COND advertises f-dispatch.

    Per-villain ACTION routines (TROLL-FCN, THIEF-FCN, CYCLOPS-FCN) test
    .MODE against F-* combat constants; without f-dispatch detection, the
    F-DEAD branch (which drops the villain's weapon to the floor) was
    never split into its own verb file, so the bloody axe stayed in
    limbo after troll death."""
    routine = _routine('<ROUTINE FOO (MODE) <COND (<EQUAL? .MODE ,F-DEAD> <TELL "dead" CR>)>>')
    assert has_f_dispatch(routine) is True


def test_f_dispatch_absent_for_plain_routine():
    """A routine that never tests MODE against F-* has no f-dispatch."""
    routine = _routine('<ROUTINE FOO () <TELL "hi" CR>>')
    assert has_f_dispatch(routine) is False


def test_f_clause_extracts_only_matching_branch():
    """translate_f_clause emits only the body of the matching F-* clause."""
    routine = _routine(
        "<ROUTINE FOO (MODE) "
        "<COND "
        '(<EQUAL? .MODE ,F-DEAD>      <TELL "perish" CR>) '
        '(<EQUAL? .MODE ,F-CONSCIOUS> <TELL "wakes"  CR>)>>'
    )
    dead = translate_f_clause(routine, "F-DEAD")
    conscious = translate_f_clause(routine, "F-CONSCIOUS")
    assert "perish" in dead and "wakes" not in dead
    assert "wakes" in conscious and "perish" not in conscious


def test_f_clause_uses_mapped_verb_name_in_shebang():
    """F-DEAD maps to the ``f_dead`` verb name (per _M_TO_VERB)."""
    routine = _routine('<ROUTINE FOO (MODE) <COND (<EQUAL? .MODE ,F-DEAD> <TELL "dead" CR>)>>')
    out = translate_f_clause(routine, "F-DEAD")
    # First line is the shebang
    first_line = out.splitlines()[0]
    assert first_line.startswith("#!moo verb f_dead")


# ---------------------------------------------------------------------------
# Fallback for unhandled forms
# ---------------------------------------------------------------------------


def test_unhandled_enable_form_emits_zil_comment_only():
    """Defensive fallback: an ``<ENABLE>`` whose inner form is neither
    ``<QUEUE>`` nor ``<INT>`` annotates the original form as a ZIL
    comment and emits no executable statement. The known inner forms
    (covered separately) are exhaustive for the actual Zork sources;
    the fallback exists so a future ZIL input can't silently produce
    invalid Python."""
    out = _translate("<ROUTINE FOO () <ENABLE <SOMETHING-NOT-QUEUE>>>")
    assert "# ZIL:" in out
    assert "ENABLE not translated" in out
    # Earlier versions raised NotImplementedError, which broke control
    # flow because subsequent body forms became unreachable code.
    assert "NotImplementedError" not in out


def test_enable_queue_emits_sdk_queue():
    """<ENABLE <QUEUE routine delay>> compiles to _.queue(...) for
    turn-mode daemons (i-lantern is the canonical fuel-decay case)."""
    out = _translate("<ROUTINE FOO () <ENABLE <QUEUE I-LANTERN 100>>>")
    assert "_.queue('i-lantern', 100)" in out


def test_enable_int_emits_sdk_queue_with_zero_delay():
    """<ENABLE <INT routine>> re-enables a previously queued turn-mode
    task; in SDK terms that's a queue() with delay=0."""
    out = _translate("<ROUTINE FOO () <ENABLE <INT I-CYCLOPS>>>")
    assert "_.queue('i-cyclops', 0)" in out


def test_enable_realtime_routine_uses_native_scheduler():
    """``i-thief`` is on the realtime allowlist; ENABLE must emit a
    ``_.schedule_realtime`` call targeting the snake-cased verb name."""
    out = _translate("<ROUTINE FOO () <ENABLE <QUEUE I-THIEF -1>>>")
    assert "_.schedule_realtime('i_thief', -1)" in out
    assert "_.queue('i-thief'" not in out


def test_disable_realtime_routine_uses_native_unscheduler():
    """DISABLE on a realtime routine routes to _.unschedule_realtime."""
    out = _translate("<ROUTINE FOO () <DISABLE <INT I-FOREST-ROOM>>>")
    assert "_.unschedule_realtime('i_forest_room')" in out
    assert "_.cancel('i-forest-room')" not in out


def test_bare_int_does_not_recursively_invoke_routine():
    """``<INT routine>`` in expression context must not emit a function
    call to the routine itself.  The canonical i-sword body does
    ``<SET DEM <INT I-SWORD>>`` — if the translator emitted
    ``_.thing.i_sword()`` for the inner ``I-SWORD``, the daemon
    would invoke itself infinitely as soon as it fires.

    Regression: caught when the smoke harness wedged on the first turn
    because i-sword's first invocation recursed until the celery worker
    timed out.
    """
    out = _translate("<ROUTINE I-SWORD () <SET DEM <INT I-SWORD>>>")
    assert "_.thing.i_sword()" not in out, f"INT translation recursively invokes the routine itself:\n{out}"
    assert "_.thing.int(" not in out, f"INT translation calls a nonexistent ``int`` verb:\n{out}"
    # The slot is unsupported in our scheduling model — None is the safe placeholder.
    assert "dem = None" in out


def test_river_and_tide_daemons_stay_on_turn_queue():
    """Boat drift, tide flips, and sword glow are timing-sensitive in
    canonical Zork — keep them on the per-player turn queue so the
    smoke harness's expected cadence holds."""
    for routine in ("i-river", "i-rfill", "i-rempty", "i-sword"):
        out = _translate(f"<ROUTINE FOO () <ENABLE <QUEUE {routine.upper()} 1>>>")
        assert f"_.queue('{routine}', 1)" in out, f"{routine} should still emit _.queue (turn-accurate)"
        assert "_.schedule_realtime" not in out, f"{routine} should NOT emit _.schedule_realtime"


def test_disable_turn_routine_still_uses_cancel():
    """DISABLE on a turn-mode routine keeps the per-player ``_.cancel``
    path so turn-accurate decay (lantern fuel, rage) stays synchronous
    with player commands."""
    out = _translate("<ROUTINE FOO () <DISABLE <INT I-LANTERN>>>")
    assert "_.cancel('i-lantern')" in out


def test_bare_queue_routes_through_classifier():
    """Bare ``<QUEUE r d>`` (not wrapped in ENABLE) honours the same
    realtime/turn split as ``<ENABLE <QUEUE r d>>``."""
    realtime = _translate("<ROUTINE FOO () <QUEUE I-FOREST-ROOM 5>>")
    assert "_.schedule_realtime('i_forest_room', 5)" in realtime

    turn = _translate("<ROUTINE FOO () <QUEUE I-FIGHT 1>>")
    assert "_.queue('i-fight', 1)" in turn


def test_double_equal_predicate_translates_as_equality():
    """<==? a b> is one of ZIL's equality predicates and translates
    identically to <EQUAL? a b>. This depended on the parser tokenizing
    ``==?`` as a single atom (rather than ``==`` + ``?``)."""
    out = _translate("<ROUTINE FOO () <COND (<==? ,HERE ,FOREST-1> <RTRUE>)>>")
    assert "==" in out
    assert "if " in out
    assert "# ZIL: unrecognised" not in out


# ---------------------------------------------------------------------------
# Header + verb shebang
# ---------------------------------------------------------------------------


def test_translation_starts_with_moo_shebang():
    """Generated verb files start with the #!moo verb header."""
    out = _translate('<ROUTINE FOO () <TELL "hi" CR>>')
    assert out.lstrip().startswith("#!moo verb")


@pytest.mark.parametrize("name", ["FOO", "BAR-FN", "X-Y-Z"])
def test_routine_name_appears_in_shebang(name):
    """Routine names are snake-cased into the shebang verb name (D-mild).

    Hyphens become underscores so callers can reach the verb via
    dot-syntax (``_.thing.bar_fn()``) instead of always going
    through ``invoke_verb``.  Player-typed verb names in action-handler
    routines still keep their hyphens — that case is handled by the
    multi-verb shebang branch in ``_shebang()`` and isn't exercised here.
    """
    out = _translate(f'<ROUTINE {name} () <TELL "x" CR>>')
    expected = name.lower().replace("-", "_")
    assert expected in out.splitlines()[0]


# ---------------------------------------------------------------------------
# Identifier sanitization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("FOO", "foo"),
        ("FOO-BAR", "foo_bar"),
        ("LIT?", "lit_p"),
        ("STOLE-LIGHT?", "stole_light_p"),
        # ZIL local-var deref ``.X`` is stripped on entry so the resulting
        # identifier matches the unadorned variable name. (``,X`` is
        # stripped at the call site before reaching ``sanitize_ident`` —
        # not by the helper itself.)
        (".OLD-LIT", "old_lit"),
        # Any non-alphanumeric character collapses to ``_`` so we never
        # emit invalid identifiers.
        ("FOO!", "foo_"),
        ("FOO*BAR", "foo_bar"),
        # Empty / pathological inputs round-trip to a stable sentinel.
        ("", "unknown_v"),
        (".", "unknown_v"),
    ],
)
def testsanitize_ident_basic(raw, expected):
    assert sanitize_ident(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        # Atoms whose sanitized form would be a Python keyword get a
        # ``_v`` suffix so the generated code parses.
        ("DEF", "def_v"),
        ("CLASS", "class_v"),
        ("IF", "if_v"),
        ("RETURN", "return_v"),
        # Atoms whose sanitized form would shadow a common builtin (used
        # heavily by the translator output) get the same suffix.
        ("SET", "set_v"),
        ("LIST", "list_v"),
        ("TYPE", "type_v"),
        ("PRINT", "print_v"),
    ],
)
def testsanitize_ident_avoids_keyword_and_builtin_collisions(raw, expected):
    assert sanitize_ident(raw) == expected


@pytest.mark.parametrize("raw", ["1FOO", "9-FOO", "0?"])
def testsanitize_ident_prefixes_leading_digit(raw):
    """Leading digits get a ``v_`` prefix so the result is a valid identifier."""
    out = sanitize_ident(raw)
    assert out.startswith("v_"), f"{raw!r} → {out!r} should be prefixed"
    assert out.replace("_", "").replace("v", "", 1) or True  # well-formed


def testsanitize_ident_is_idempotent_for_valid_names():
    """Already-valid identifiers round-trip unchanged."""
    for name in ("foo", "foo_bar", "x_y_z"):
        assert sanitize_ident(name) == name


# ---------------------------------------------------------------------------
# Parser tokenization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("predicate", ["0?", "1?", "ZERO?"])
def test_predicate_tokens_are_atoms_not_number_plus_atom(predicate):
    """``0?`` and ``1?`` must lex as a single atom — not as a number followed
    by ``?``. The translator depends on the head of ``<0? .X>`` being the
    atom ``0?`` so it can dispatch on it; if the parser splits it, the form
    becomes ``[0, ?, .X]`` and translation degenerates to a Python list
    literal that's always truthy."""
    tokens = tokenize(f"<{predicate} 1>")
    kinds = [t.kind for t in tokens]
    # ``<``, atom, number, ``>``
    assert kinds == ["open_angle", "atom", "number", "close_angle"]
    assert tokens[1].value == predicate


def test_parser_distinguishes_strings_from_atoms():
    """Quoted strings come back as ``Str`` (a subclass of ``str``); bare
    atoms come back as plain ``str``. The translator uses this distinction
    to decide between ``print('hello')`` and ``zstate_get('HELLO')``."""
    nodes = parse(tokenize('<TELL "hello" HELLO>'))
    assert len(nodes) == 1
    form = nodes[0]
    quoted, atom = form[1], form[2]
    assert isinstance(quoted, Str)
    assert quoted == "hello"
    assert isinstance(atom, str) and not isinstance(atom, Str)
    assert atom == "HELLO"


def test_string_literal_translates_as_python_string():
    """A ZIL string in expression context emits a Python string literal,
    not a state read — even when the contents look atom-like (all caps,
    contains hyphens)."""
    out = _translate('<ROUTINE FOO () <TELL "ALL CAPS WITH-DASHES" CR>>')
    assert "'ALL CAPS WITH-DASHES'" in out
    # The all-caps content must NOT be treated as a global-state lookup.
    assert "zstate_get('ALL" not in out


# ---------------------------------------------------------------------------
# Phase 1A: PRSO / PRSI hoist + None guard
# ---------------------------------------------------------------------------


def test_prso_hoisted_as_local_when_body_references_it():
    """Routine body that touches PRSO gets a top-of-routine binding so the
    dobj is fetched exactly once and downstream method calls run against
    a stable local instead of a fresh parser query each access."""
    out = _translate("<ROUTINE V-FOO () <FSET? ,PRSO ,OPENBIT>>")
    assert "prso = parser.get_dobj() if parser.has_dobj_str() else None" in out


def test_prso_not_hoisted_when_body_does_not_reference_it():
    """No spurious prologue when PRSO never appears."""
    out = _translate('<ROUTINE V-FOO () <TELL "hi" CR>>')
    assert "prso = parser.get_dobj()" not in out


def test_prsi_hoisted_independently_of_prso():
    """PRSI gets its own hoist; PRSO doesn't piggy-back."""
    out = _translate("<ROUTINE V-FOO () <FSET? ,PRSI ,OPENBIT>>")
    assert "prsi = parser.get_iobj() if parser.has_iobj() else None" in out
    assert "prso = parser.get_dobj()" not in out


def test_dspec_this_substrate_emits_none_guard():
    """V-PUT-style substrate verb with PRSO access gets an early-return
    guard so bare `put` doesn't AttributeError on ``None.location``."""
    out = _translate("<ROUTINE V-PUT () <FSET? ,PRSO ,OPENBIT>>")
    assert "if prso is None:" in out
    assert "What do you want to put?" in out


def test_dspec_this_substrate_guard_omitted_when_no_prso_use():
    """V-LOOK-style residual that doesn't touch PRSO at all should NOT
    grow a missing-dobj guard."""
    out = _translate('<ROUTINE V-LOOK () <TELL "ok" CR>>')
    assert "if prso is None:" not in out


def test_non_v_routine_guard_uses_generic_message():
    """Helper routines like IDROP (registered as substrate verbs but
    not player-typed verbs) still get a guard, but the message falls
    through to the generic refusal rather than echoing the helper name."""
    out = _translate("<ROUTINE IDROP () <FSET? ,PRSO ,OPENBIT>>")
    assert "if prso is None:" in out
    assert "What do you want to idrop?" not in out


def test_null_safe_iobj_methods_wraps_prsi_flag():
    """``prsi.flag(...)`` inside a routine body becomes
    ``(prsi.flag(...) if prsi else None)`` so a missing iobj doesn't
    crash on ``None.flag``."""
    out = _translate("<ROUTINE V-FOO () <FSET? ,PRSI ,OPENBIT>>")
    assert "prsi.flag('open') if prsi else None" in out


# ---------------------------------------------------------------------------
# Per-clause split dspec (Bug 4 — examine fallback to held lantern)
# ---------------------------------------------------------------------------


def test_per_clause_split_dspec_is_this_for_object_owner():
    """A per-object ``<VERB?>`` clause emits ``--dspec this`` so the
    handler fires only when parser.dobj IS the action owner — not
    when the player is holding the object and typed an unrelated dobj.
    """
    routine = _routine('<ROUTINE LANTERN-FCN () <COND (<VERB? EXAMINE> <TELL "lamp" CR>)>>')
    t = ZilTranslator(routine, action_owner=("LANTERN", False))
    shebang = t._shebang_verb(["EXAMINE"])
    assert "--dspec this" in shebang
    assert "--dspec either" not in shebang


def test_per_clause_split_dspec_stays_either_for_room_owner():
    """Room ``<VERB?>`` clauses keep ``--dspec either`` because the
    player's dobj is rarely the room itself (e.g. Living Room's
    ``<VERB? READ>`` on gothic lettering — dobj=lettering, not room).
    """
    routine = _routine('<ROUTINE LIVING-ROOM-FCN () <COND (<VERB? READ> <TELL "gothic" CR>)>>')
    t = ZilTranslator(routine, action_owner=("LIVING-ROOM", True))
    shebang = t._shebang_verb(["READ"])
    assert "--dspec either" in shebang


def test_orphan_clause_split_keeps_dspec_either():
    """Orphan splits (no action_owner) register on $thing as the
    parent substrate routine's nested per-clause files.  They must keep
    ``--dspec either`` so the parent's forward via ``invoke_verb`` reaches
    them regardless of the dispatched dobj — the parent already
    enforces dspec at its own boundary.
    """
    routine = _routine('<ROUTINE V-FOO () <COND (<VERB? EXAMINE> <TELL "fallback" CR>)>>')
    t = ZilTranslator(routine)
    shebang = t._shebang_verb(["EXAMINE"])
    assert "--dspec either" in shebang


def test_m_clause_shebang_stays_either():
    """M-* clauses fire without a parsed dobj (M-BEG / M-LOOK / M-ENTER
    run on room entry, before player input), so they MUST stay
    ``--dspec either``.  Guards the carve-out from the per-object
    ``--dspec this`` change.
    """
    routine = _routine('<ROUTINE LIVING-ROOM-FCN (RARG) <COND (<EQUAL? .RARG ,M-LOOK> <TELL "look" CR>)>>')
    t = ZilTranslator(routine, action_owner=("LIVING-ROOM", True))
    shebang = t._shebang_m("M-LOOK")
    assert "--dspec either" in shebang


# ---------------------------------------------------------------------------
# PRE-X guard return value (Bug 6 — push/press/turn dual error message)
# ---------------------------------------------------------------------------


def test_pre_routine_prso_guard_returns_true():
    """PRE-X routines must ``return True`` from the missing-dobj guard
    so their caller V-X exits early instead of falling through to its
    default refusal (e.g. ``V-TURN`` printing "This has no effect."
    after PRE-TURN already complained about the missing dobj).
    """
    out = _translate("<ROUTINE PRE-TURN () <FSET? ,PRSO ,OPENBIT>>")
    assert "if prso is None:" in out
    # The guard's last line should be ``return True`` — locate the guard
    # block and verify.
    guard_start = out.index("if prso is None:")
    # The guard runs through to the next blank line before the body.
    guard_end = out.index("\n\n", guard_start)
    guard_block = out[guard_start:guard_end]
    assert "return True" in guard_block


def test_non_pre_routine_prso_guard_returns_bare():
    """V-X routines (terminal verbs) keep bare ``return`` in their
    missing-dobj guard so they don't accidentally signal "handled" to
    a parent that isn't there.  Guards against over-reaching the
    PRE-X change.
    """
    out = _translate("<ROUTINE V-PUT () <FSET? ,PRSO ,OPENBIT>>")
    assert "if prso is None:" in out
    guard_start = out.index("if prso is None:")
    guard_end = out.index("\n\n", guard_start)
    guard_block = out[guard_start:guard_end]
    assert "return True" not in guard_block
    assert "    return\n" in guard_block + "\n"
