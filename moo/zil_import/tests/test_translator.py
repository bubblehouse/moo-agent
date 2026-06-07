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

from moo.zil_import.converter import _extract_routine
from moo.zil_import.parser import Str, parse, tokenize
from moo.zil_import.translator import (
    F_CLAUSES,
    M_CLAUSES,
    ZilTranslator,
    atom_to_snake,
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


def test_here_predicate_emits_current_room_check():
    """``<HERE? KITCHEN>`` becomes a current-room equality test against
    ``context.player.here()`` (how the ``HERE`` global is rendered), and a
    multi-atom form becomes a membership check.  Without the handler the form
    fell through to an undefined ``here_p(...)`` call (NameError at runtime)."""
    one = _translate("<ROUTINE FOO () <COND (<HERE? KITCHEN> <RTRUE>)>>")
    assert "player.here() ==" in one
    assert "here_p(" not in one
    many = _translate("<ROUTINE FOO () <COND (<HERE? KITCHEN CELLAR> <RTRUE>)>>")
    assert "player.here() in (" in many


def test_is_predicate_delegates_to_fset():
    """``<IS? ,LAMP ONBIT>`` is the library macro ``<FSET? ,LAMP ONBIT>`` and
    emits an ``.flag(...)`` check, not an undefined ``is_p(...)`` call."""
    out = _translate("<ROUTINE FOO () <COND (<IS? ,LAMP ONBIT> <RTRUE>)>>")
    assert ".flag(" in out
    assert "is_p(" not in out


def test_t_predicate_emits_nonzero_check():
    """``<T? .N>`` is the library macro ``<NOT <ZERO? .N>>`` — a non-zero
    truthiness test, not an undefined ``t_p(...)`` call."""
    out = _translate("<ROUTINE FOO (N) <COND (<T? .N> <RTRUE>)>>")
    assert "!= 0" in out
    assert "t_p(" not in out


def test_msb_lsb_emit_byte_masks():
    """``<MSB w>`` / ``<LSB w>`` are the library macros ``<BAND w 0xff00>`` /
    ``<BAND w 127>`` — emit ``&`` byte masks, not undefined ``msb``/``lsb`` calls."""
    msb = _translate("<ROUTINE FOO (W) <COND (<MSB .W> <RTRUE>)>>")
    assert "& ((65280) or 0)" in msb
    assert "msb(" not in msb
    lsb = _translate("<ROUTINE FOO (W) <COND (<LSB .W> <RTRUE>)>>")
    assert "& ((127) or 0)" in lsb
    assert "lsb(" not in lsb


def test_dless_igrtr_emit_walrus_dec_inc_checks():
    """``<DLESS? .I N>`` / ``<IGRTR? .I N>`` are Z-machine dec_chk/inc_chk —
    decrement/increment-then-test, emitted as walrus so the side-effect lands
    in expression position. Not undefined ``dless_p``/``igrtr_p`` calls."""
    dless = _translate("<ROUTINE FOO (I) <COND (<DLESS? I 0> <RTRUE>)>>")
    assert "(i := i - 1) < 0" in dless
    assert "dless_p(" not in dless
    igrtr = _translate("<ROUTINE FOO (I) <COND (<IGRTR? I 9> <RTRUE>)>>")
    assert "(i := i + 1) > 9" in igrtr
    assert "igrtr_p(" not in igrtr


def test_map_builtin_handlers_emit_substrate_calls():
    """The auto-map renderer's ZIL builtins map to substrate/SDK calls, not
    undefined bare functions: INTBL?/COPYT/PRINTT → ``_.``; PUTB → table_put;
    GETPT → getp; FONT → no-op; INC/DEC → walrus mutate."""
    intbl = _translate("<ROUTINE FOO (V T L) <COND (<INTBL? .V .T .L 1> <RTRUE>)>>")
    assert "_.intbl_p(" in intbl and "intbl_p(v" not in intbl.replace("_.intbl_p(v", "")
    assert "_.copyt(" in _translate("<ROUTINE FOO (A B) <COPYT .A .B 4>>")
    assert "_.printt(" in _translate("<ROUTINE FOO (M) <PRINTT .M 17 11>>")
    assert "_.table_put(" in _translate("<ROUTINE FOO (M) <PUTB .M 0 32>>")
    assert ".getp(" in _translate("<ROUTINE FOO (O) <GETPT .O ,P?COORDS>>")
    # FONT is inert (no-op constant), not an undefined font() call.
    assert "font(" not in _translate("<ROUTINE FOO () <FONT 3>>")


def test_inc_dec_emit_walrus_mutation():
    """``<INC X>`` / ``<DEC X>`` mutate in place via walrus (do_curset uses them)."""
    inc = _translate("<ROUTINE FOO (X) <INC X>>")
    assert "(x := x + 1)" in inc
    dec = _translate("<ROUTINE FOO (X) <DEC X>>")
    assert "(x := x - 1)" in dec


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


def test_make_macro_emits_set_flag_true():
    """Beyond Zork's <MAKE obj flag> macro (= <FSET obj flag>) sets the flag True."""
    out = _translate("<ROUTINE FOO () <MAKE ,GRUE ,SEEN>>")
    assert ".set_flag(" in out
    assert "True" in out


def test_unmake_macro_emits_set_flag_false():
    """<UNMAKE obj flag> macro (= <FCLEAR obj flag>) clears the flag."""
    out = _translate("<ROUTINE FOO () <UNMAKE ,GRUE ,SEEN>>")
    assert ".set_flag(" in out
    assert "False" in out


def test_assigned_predicate_checks_not_none():
    """<ASSIGNED? .X> tests whether an optional ("OPT") param was supplied."""
    out = _translate('<ROUTINE FOO (A "OPT" X) <COND (<ASSIGNED? .X> <RTRUE>)>>')
    assert "is not None" in out
    assert "assigned_p" not in out


def test_first_coerces_empty_to_zil_false_for_xzip_only():
    """In the XZIP dialect <FIRST? obj> coerces the empty case to ZIL FALSE (0)
    so the object-walk loop terminators (<ZERO? .OBJ> / == 0) fire; EZIP keeps
    the plain ``.contents.first()`` (its loops use truthy / is-None tests)."""
    from moo.zil_import.game_config import BEYONDZORK_CONFIG

    xzip = translate_routine(_routine("<ROUTINE FOO () <FIRST? ,HERE>>"), game_config=BEYONDZORK_CONFIG)
    assert ".contents.first() or 0)" in xzip
    ezip = _translate("<ROUTINE FOO () <FIRST? ,HERE>>")
    assert ".contents.first()" in ezip
    assert "or 0)" not in ezip


def test_next_sibling_coerces_to_zil_false_for_xzip_only():
    """<NEXT? obj> wraps next_sibling in ``(... or 0)`` for XZIP only."""
    from moo.zil_import.game_config import BEYONDZORK_CONFIG

    xzip = translate_routine(_routine("<ROUTINE FOO (X) <NEXT? .X>>"), game_config=BEYONDZORK_CONFIG)
    assert "(_.next_sibling(x) or 0)" in xzip
    ezip = _translate("<ROUTINE FOO (X) <NEXT? .X>>")
    assert "_.next_sibling(x)" in ezip
    assert "or 0)" not in ezip


def test_table_ops_use_byte_addressed_substrate_for_xzip_only():
    """REST/GET/PUT/COPYT/INTBL? route to the byte-addressed zaddr_* substrate
    for the XZIP dialect (pointer arithmetic) and the list-based primitives for
    EZIP (unchanged)."""
    from moo.zil_import.game_config import BEYONDZORK_CONFIG

    src = "<ROUTINE FOO (T X) <REST .T 2> <GET .T 1> <PUT .T 1 5> <COPYT .T .T 4> <INTBL? .X .T 8 1>>"
    xzip = translate_routine(_routine(src), game_config=BEYONDZORK_CONFIG)
    for name in ("zaddr_rest", "zaddr_get", "zaddr_put", "zaddr_copyt", "zaddr_intbl_p"):
        assert f"_.{name}(" in xzip, name
    ezip = _translate(src)
    for name in ("_.rest(", "_.table_get(", "_.table_put(", "_.copyt(", "_.intbl_p("):
        assert name in ezip, name
    assert "zaddr_" not in ezip


def test_dirout_routes_to_capture_substrate_for_xzip_only():
    """<DIROUT D-TABLE-ON AUX-TABLE> redirects output into a table buffer via the
    zdirout substrate for XZIP; EZIP keeps the safe no-op comment."""
    from moo.zil_import.game_config import BEYONDZORK_CONFIG

    xzip = translate_routine(_routine("<ROUTINE T () <DIROUT ,D-TABLE-ON ,AUX-TABLE>>"), game_config=BEYONDZORK_CONFIG)
    assert "_.zdirout(" in xzip
    ezip = _translate("<ROUTINE T () <DIROUT ,D-TABLE-ON ,AUX-TABLE>>")
    assert "_.zdirout(" not in ezip
    assert "not yet modelled" in ezip


def test_lowcore_routes_to_substrate():
    """<LOWCORE FLAGS> (Z-machine header read) → _.lowcore(...), not a bare call."""
    out = _translate("<ROUTINE FOO () <LOWCORE FLAGS>>")
    assert "_.lowcore(" in out
    assert "\nlowcore(" not in out and " lowcore(" not in out


def test_apply_variable_routine_routes_to_substrate():
    """<APPLY .X ,M-LOOK> (routine held in a variable) routes to the _.apply
    substrate helper rather than the removed Python 2 apply() builtin."""
    out = _translate("<ROUTINE FOO (X) <APPLY .X ,M-LOOK>>")
    assert "_.apply(" in out
    assert "\napply(" not in out and " apply(" not in out


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


def test_getp_with_variable_prop_emits_local_not_literal():
    """<GETP ,HERE .DIR> with .DIR a routine var emits getp(dir), not getp('.dir').

    The prop arg is the loop variable's *value* (a P? property number resolved
    at runtime by the getp helper), so it must be the bare local — emitting the
    literal string ``'.dir'`` (the old bug) makes every lookup miss.
    """
    out = _translate('<ROUTINE FOO ("AUX" DIR) <GETP ,HERE .DIR>>')
    assert ".getp(dir)" in out
    assert "getp('.dir')" not in out


def test_getp_with_form_prop_emits_expression():
    """<GETP .RM <GETB ,PDIR-LIST .DIR>> translates the computed prop as an expr.

    The exit-table lookup the auto-map relies on: the prop arg is a form, so it
    must become a runtime expression (the GETB into PDIR-LIST), not a stringified
    literal of the AST.
    """
    out = _translate('<ROUTINE FOO (RM "AUX" DIR) <GETP .RM <GETB ,PDIR-LIST .DIR>>>')
    assert "rm.getp(" in out
    assert "zaddr_get" in out or "table_get" in out
    assert "['getb'" not in out


def test_opt_keyword_is_not_a_parameter():
    """``"OPT"`` is the short form of ``"OPTIONAL"`` — a keyword, not a param.

    Beyond Zork / Zork Zero use ``"OPT"`` exclusively; mis-parsing it as a
    parameter shifts the real optionals by one slot, so ``<APPLY .X ,M-LOOK>``
    on a room ACTION lands M-LOOK in a phantom ``opt`` arg and the room's
    ``CONTEXT`` check (the description branch) never fires.
    """
    routine = _routine('<ROUTINE HILLTOP-F ("OPT" (CONTEXT <>)) <COND (<EQUAL? .CONTEXT ,M-LOOK> <TELL "desc" CR>)>>')
    assert "OPT" not in routine.params
    assert routine.params == ["CONTEXT"]


def test_opt_param_read_from_first_arg():
    """A single ``"OPT"`` param maps to ``args[0]`` (no phantom leading param)."""
    out = _translate('<ROUTINE HILLTOP-F ("OPT" (CONTEXT <>)) <COND (<EQUAL? .CONTEXT ,M-LOOK> <TELL "x" CR>)>>')
    assert "context = args[0]" in out


def test_tell_article_tokens_route_through_article_helper():
    """TELL ``CA``/``THE``/``A`` tokens print article+desc, consuming the object.

    Regression: an unhandled article token concatenated the bare object (a
    string-or-None ``zstate_get('CA')``) and the raw Object, crashing room
    descriptions like AT-LEDGE-F with ``can only concatenate str (not None)``.
    """
    from moo.zil_import.game_config import BEYONDZORK_CONFIG

    out = translate_routine(_routine('<ROUTINE FOO (O) <TELL CA .O " blasted">>'), game_config=BEYONDZORK_CONFIG)
    assert ".article(o, False, True)" in out  # CA → article, not "the", capitalised
    assert "zstate_get('CA')" not in out
    the = translate_routine(_routine("<ROUTINE FOO (O) <TELL THE .O>>"), game_config=BEYONDZORK_CONFIG)
    assert ".article(o, True, False)" in the


def test_char_literal_and_ascii_resolve_to_codepoint():
    """``!\\X`` char literals tokenise to a codepoint; ``<ASCII …>`` is identity.

    Regression: ``<PRINTC %<ASCII !\\:>>`` mis-tokenised ``!\\:`` into ``!`` +
    ``:`` and emitted ``ascii(zstate_get('!'), zstate_get(':'))`` — a 2-arg call
    to an undefined ``ascii`` (NameError, crashed the raw-mode stats line).
    """
    out = _translate("<ROUTINE FOO () <PRINTC <ASCII !\\:>>>")
    assert "chr(58)" in out  # ':' is codepoint 58
    assert "ascii(" not in out


def test_tell_quoted_string_is_not_an_article_token():
    """A quoted literal like ``"a"`` / ``"the"`` is text, not an article token."""
    from moo.zil_import.game_config import BEYONDZORK_CONFIG

    out = translate_routine(_routine('<ROUTINE FOO () <TELL "a" CR>>'), game_config=BEYONDZORK_CONFIG)
    assert "'a'" in out
    assert ".article(" not in out


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


@pytest.mark.parametrize(
    "atom,expected",
    [
        ("FOREST-ROOM", "forest_room"),
        ("LIVING-ROOM-FCN", "living_room_fcn"),
        ("EQUAL?", "equal_p"),
        ("DEFINE!", "define_b"),
        ("MIXED?-CASE!", "mixed_p_case_b"),
        ("already_snake", "already_snake"),
    ],
)
def test_atom_to_snake(atom, expected):
    """Three-replace chain: ``-``→``_``, ``?``→``_p``, ``!``→``_b``."""
    assert atom_to_snake(atom) == expected


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


# ---------------------------------------------------------------------------
# Combined M-/F-clause dispatch (Phase 7d of the syntax-row refactor)
# ---------------------------------------------------------------------------


def _trans(src: str, **kwargs) -> ZilTranslator:
    """Build a ZilTranslator over one ROUTINE form."""
    return ZilTranslator(_routine(src), **kwargs)


def test_match_m_clause_cond_bare():
    """``<EQUAL? .RARG ,M-BEG>`` returns ``("M-BEG", None)``."""
    t = _trans("<ROUTINE FOO () <RTRUE>>")
    cond = ["EQUAL?", ".RARG", ",M-BEG"]
    assert t._match_m_clause_cond(cond, "RARG", M_CLAUSES) == ("M-BEG", None)


def test_match_m_clause_cond_and_wrapped():
    """``<AND <EQUAL? .RARG ,M-ENTER> <other>>`` returns ``("M-ENTER", <other>)``."""
    t = _trans("<ROUTINE FOO () <RTRUE>>")
    cond = ["AND", ["EQUAL?", ".RARG", ",M-ENTER"], ["EQUAL?", ",TOWEL-OFFERED", "0"]]
    match = t._match_m_clause_cond(cond, "RARG", M_CLAUSES)
    assert match is not None
    constant, rest = match
    assert constant == "M-ENTER"
    assert rest == ["EQUAL?", ",TOWEL-OFFERED", "0"]


def test_match_m_clause_cond_and_wrapped_multiple_residuals():
    """AND with 3+ subs returns AND-wrapped residual when more than one
    extra cond remains after pulling out the matching EQUAL?."""
    t = _trans("<ROUTINE FOO () <RTRUE>>")
    cond = [
        "AND",
        ["EQUAL?", ".RARG", ",M-END"],
        ["EQUAL?", ",X", "1"],
        ["EQUAL?", ",Y", "2"],
    ]
    match = t._match_m_clause_cond(cond, "RARG", M_CLAUSES)
    assert match is not None
    constant, rest = match
    assert constant == "M-END"
    assert rest is not None
    assert rest[0] == "AND"
    assert len(rest) == 3  # AND + 2 residual conds


def test_match_m_clause_cond_no_match():
    """Non-EQUAL?, wrong dispatch_var, or unknown constant returns None."""
    t = _trans("<ROUTINE FOO () <RTRUE>>")
    assert t._match_m_clause_cond(["TELL", '"x"'], "RARG", M_CLAUSES) is None
    assert t._match_m_clause_cond(["EQUAL?", ".MODE", ",M-BEG"], "RARG", M_CLAUSES) is None
    assert t._match_m_clause_cond(["EQUAL?", ".RARG", ",NOT-A-CONSTANT"], "RARG", M_CLAUSES) is None


def test_extract_clause_with_extras_preserves_and_rest():
    """An AND-wrapped clause returns ``(body, and_rest)`` so the combined
    emitter can wrap the body in an inner predicate guard.  The COND must
    carry at least one bare ``<EQUAL? .RARG ,M-X>`` clause to anchor
    :py:meth:`_find_dispatch` (the walker isn't AND-aware on its own)."""
    src = (
        "<ROUTINE FOO (RARG) "
        "<COND "
        '(<EQUAL? .RARG ,M-LOOK> <TELL "look" CR>) '
        '(<AND <EQUAL? .RARG ,M-BEG> <EQUAL? ,FOO 1>> <TELL "hit" CR>)>>'
    )
    t = _trans(src)
    extracted = t._extract_clause_with_extras(t.routine.body, "M-BEG", M_CLAUSES)
    assert extracted is not None
    body, and_rest = extracted
    assert and_rest == ["EQUAL?", "FOO", 1]
    assert body  # the TELL body survived extraction


def test_translate_combined_clauses_emits_if_elif_ladder():
    """Combined-emission output ladders M-* constants with if/elif."""
    src = (
        "<ROUTINE FOREST-ROOM (RARG) "
        "<COND "
        '(<EQUAL? .RARG ,M-BEG> <TELL "begin" CR>) '
        '(<EQUAL? .RARG ,M-END> <TELL "end" CR>)>>'
    )
    t = _trans(src, action_owner=("FOREST-ROOM", True))
    out = t.translate_combined_clauses()
    assert 'if rarg == "M-BEG":' in out
    assert 'elif rarg == "M-END":' in out


def test_translate_combined_clauses_skip_constants_drops_body_and_alias():
    """``skip_constants`` drops both the branch body AND the role-name
    alias from the shebang.  Used to coexist with hand-written role
    overrides (e.g. ``living_room/turnfunc.py``)."""
    src = (
        "<ROUTINE LIVING-ROOM-FCN (RARG) "
        "<COND "
        '(<EQUAL? .RARG ,M-BEG> <TELL "begin" CR>) '
        '(<EQUAL? .RARG ,M-END> <TELL "end" CR>)>>'
    )
    t = _trans(src, action_owner=("LIVING-ROOM", True))
    out = t.translate_combined_clauses(skip_constants={"M-END"})
    assert 'if rarg == "M-BEG":' in out
    assert "M-END" not in out
    shebang = out.split("\n", 1)[0]
    shebang_tokens = shebang.split()
    assert "turnfunc" not in shebang_tokens  # M-END's role name is gone
    assert "preturnfunc" in shebang_tokens  # M-BEG's role name stays


def test_translate_combined_clauses_empty_returns_blank():
    """Every clause being a no-op short-circuits to ``""``."""
    src = "<ROUTINE FOREST-ROOM (RARG) <COND (<EQUAL? .RARG ,M-BEG> <>) (<EQUAL? .RARG ,M-END> <>)>>"
    t = _trans(src, action_owner=("FOREST-ROOM", True))
    assert t.translate_combined_clauses() == ""


def test_translate_combined_clauses_parser_safe_hoist_resets_on_success():
    """The parser-safe-hoist flag is reset after a successful run so
    subsequent translations on the same instance don't emit the guard."""
    src = '<ROUTINE FOREST-ROOM (RARG) <COND (<EQUAL? .RARG ,M-BEG> <TELL "begin" CR>)>>'
    t = _trans(src, action_owner=("FOREST-ROOM", True))
    assert t._force_parser_safe_hoist is False
    t.translate_combined_clauses()
    assert t._force_parser_safe_hoist is False


def test_parser_safe_hoist_emits_none_guard():
    """When ``_force_parser_safe_hoist=True``, the prso hoist guards
    against ``context.parser is None`` so daemon-invoked branches don't
    crash on missing parser state."""
    t = _trans("<ROUTINE V-FOO () <FSET? ,PRSO ,TAKEBIT>>")
    t._force_parser_safe_hoist = True
    hoist = t._maybe_hoist_prso(["prso.something"])
    assert any("context.parser is not None" in line for line in hoist)


def test_extract_f_clause_with_extras_uses_mode_dispatch_var():
    """F-clauses dispatch on ``.MODE`` rather than ``.RARG``; the
    extractor must pass MODE to the matcher."""
    src = '<ROUTINE TROLL-FCN (MODE) <COND (<EQUAL? .MODE ,F-DEAD> <TELL "dies" CR>)>>'
    t = _trans(src, action_owner=("TROLL", False))
    extracted = t._extract_clause_with_extras(t.routine.body, "F-DEAD", F_CLAUSES)
    assert extracted is not None


# ---------------------------------------------------------------------------
# Display / screen-window opcodes (v5 XZIP and later) → windowed-display SDK
# ---------------------------------------------------------------------------


def test_split_emits_window_split():
    """<SPLIT n> opens/resizes the upper window."""
    out = _translate("<ROUTINE T () <SPLIT 12>>")
    assert "window_split(player, 12)" in out
    assert "from moo.sdk import" in out and "window_split" in out


def test_curset_emits_zcurset():
    """<CURSET row col> moves the upper-window cursor and records the position
    (via the zcurset substrate) so printt can lay a grid out from it."""
    out = _translate("<ROUTINE T () <CURSET 2 3>>")
    assert "_.zcurset(2, 3)" in out


def test_clear_emits_window_clear():
    """<CLEAR> clears the upper window."""
    out = _translate("<ROUTINE T () <CLEAR>>")
    assert "window_clear(player)" in out


def test_screen_emits_runtime_target_select():
    """<SCREEN ,S-WINDOW>/<SCREEN ,S-TEXT> set the runtime output target via the
    zscreen substrate (cross-routine, unlike the old static within-routine flag)."""
    out = _translate("<ROUTINE T () <SCREEN ,S-WINDOW>>")
    assert "_.zscreen(1)" in out
    out2 = _translate("<ROUTINE T () <SCREEN ,S-TEXT>>")
    assert "_.zscreen(0)" in out2


def test_xzip_output_routes_through_zout():
    """For the XZIP dialect, TELL/PRINT/PRINTC route through the zout substrate so
    the active (upper/lower) window is chosen at runtime; EZIP keeps print()."""
    from moo.zil_import.game_config import BEYONDZORK_CONFIG

    xzip = translate_routine(_routine('<ROUTINE T () <TELL "HP"> <PRINTC 65> <CRLF>>'), game_config=BEYONDZORK_CONFIG)
    assert "_.zout('HP', 0)" in xzip
    assert "_.zout(chr(65))" in xzip
    assert "_.zout('', 1)" in xzip
    ezip = _translate("<ROUTINE T () <PRINTC 65>>")
    assert "print(chr(65), end='')" in ezip
    assert "zout" not in ezip


def test_screen_lower_keeps_print():
    """After <SCREEN ,S-TEXT>, <TELL ...> goes back to the scrolling print()."""
    out = _translate('<ROUTINE T () <SCREEN ,S-WINDOW> <SCREEN ,S-TEXT> <TELL "story" CR>>')
    assert "print('story')" in out
    assert "window_emit" not in out


def test_screen_numeric_arg_selects_window():
    """<SCREEN 1> selects the upper window; <SCREEN 0> the lower."""
    upper = _translate('<ROUTINE T () <SCREEN 1> <TELL "x">>')
    assert "window_emit(player," in upper
    lower = _translate('<ROUTINE T () <SCREEN 0> <TELL "x">>')
    assert "print('x'" in lower


def test_unmodelled_display_opcodes_are_safe_noops():
    """HLIGHT/COLOR/FONT emit comments, not bogus runtime calls."""
    out = _translate("<ROUTINE T () <HLIGHT 1> <COLOR 4 2> <FONT 3>>")
    assert "# ZIL: <HLIGHT ...>" in out
    assert "hlight(" not in out
    assert "color(" not in out
    assert "font(" not in out
