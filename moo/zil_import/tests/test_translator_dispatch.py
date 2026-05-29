"""
Direct unit tests for the translator's verb-dispatch emission.

These exercise translator internals that previously had no direct
coverage — only the auto-regenerated consistency/coverage baselines,
which can't catch wrong-but-consistent output.  Covered here:

- ``_fix_return_print`` — ``return print(...)`` is split into
  ``print(...)`` + ``return True`` (the truthy "handled" semantic the
  OBJECT-FUNCTION action chain depends on).
- ``translate_object_function_combined`` COND fall-through — an
  ``<AND <VERB? X> <test>>`` clause folds ``test`` into the elif
  condition rather than wrapping the body, and a non-``VERB?`` outer
  clause containing a nested ``VERB?`` dispatch emits a guarded
  fallback elif.
"""

# Tests poke protected translator methods directly to verify dispatch
# emission in isolation (these aren't part of the public surface).
# pylint: disable=protected-access

from __future__ import annotations

from moo.zil_import.converter import _extract_routine
from moo.zil_import.parser import parse, tokenize
from moo.zil_import.translator import ZilTranslator


def _routine(src: str):
    """Parse a single ROUTINE form into a ZilRoutine."""
    nodes = parse(tokenize(src))
    assert len(nodes) == 1, f"expected one top-level form, got {len(nodes)}"
    return _extract_routine(nodes[0])


def _trans(src: str, **kwargs) -> ZilTranslator:
    """Build a ZilTranslator over one ROUTINE form."""
    return ZilTranslator(_routine(src), **kwargs)


# ---------------------------------------------------------------------------
# _fix_return_print
# ---------------------------------------------------------------------------


def test_fix_return_print_splits_into_print_and_return_true():
    """``return print(...)`` becomes ``print(...)`` then ``return True``."""
    t = _trans("<ROUTINE FOO () <RTRUE>>")
    out = t._fix_return_print(["    return print('Taken.')"])
    assert out == ["    print('Taken.')", "    return True"]


def test_fix_return_print_preserves_indentation():
    """Both emitted lines keep the original line's indentation."""
    t = _trans("<ROUTINE FOO () <RTRUE>>")
    out = t._fix_return_print(["        return print('x')"])
    assert out == ["        print('x')", "        return True"]


def test_fix_return_print_leaves_non_matching_lines():
    """Lines that aren't ``return print(...)`` pass through untouched."""
    t = _trans("<ROUTINE FOO () <RTRUE>>")
    lines = ["    return False", "    print('hi')", "    return value"]
    assert t._fix_return_print(list(lines)) == lines


# ---------------------------------------------------------------------------
# translate_object_function_combined — COND fall-through
# ---------------------------------------------------------------------------


def test_verb_clause_extra_test_folds_into_elif_condition():
    """An ``<AND <VERB? X> <test>>`` clause folds ``test`` into the elif
    condition ``(the_verb == 'x') and (...)`` instead of wrapping the
    body — so a failed guard falls through to later clauses."""
    src = (
        "<ROUTINE RUSTY-KNIFE-FCN () "
        '<COND (<AND <VERB? ATTACK> <FSET? ,PRSO ,TOUCHBIT>> <TELL "stab" CR>) '
        '(<VERB? TAKE> <TELL "got it" CR>)>>'
    )
    t = _trans(src, action_owner=("RUSTY-KNIFE", False))
    out = t.translate_object_function_combined()
    assert "(the_verb == 'attack') and (" in out
    # A clause with no extra test stays a bare verb comparison.
    assert "elif the_verb == 'take':" in out


def test_non_verb_outer_clause_with_nested_verb_emits_guarded_fallback():
    """A non-``VERB?`` outer clause whose body contains a nested
    ``VERB?`` dispatch becomes a fallback elif guarded by the outer
    test, with the verb switch inlined."""
    src = (
        "<ROUTINE BEER-F () "
        '<COND (<VERB? EXAMINE> <TELL "a beer" CR>) '
        '(<EQUAL? ,IDENTITY ,FORD> <COND (<VERB? DRINK> <TELL "glug" CR>)>)>>'
    )
    t = _trans(src, action_owner=("BEER", False))
    out = t.translate_object_function_combined()
    assert "elif player.zstate_get('IDENTITY') == player.zstate_get('FORD'):" in out
    assert "if the_player_verb == 'drink':" in out
