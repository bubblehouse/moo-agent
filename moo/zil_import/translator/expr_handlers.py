"""
Expression-level form-head handlers.

``ZilTranslator._translate_expr`` dispatches through ``HANDLERS``;
unknown heads fall through to ``_h_default`` (routine calls,
single-element lists, bare atoms).  Atom-level branches live in
``_translate_expr`` itself.  See :doc:`/reference/zil-importer`
(Translator package layout).

Every ``_h_*`` handler in this module follows the ``Handler`` protocol
below.  Per-handler docstrings describe only the form-specific
behaviour; the ``Handler``-protocol parameters and return type are
documented once on the alias and not repeated.
"""
# Handlers were split out of ``ZilTranslator`` but still reach into its
# private ``_translate_expr`` / ``_is_prso_atom`` / ``_direction_string``
# API — they're effectively the same module by intent.
# pylint: disable=protected-access

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Callable

from ..ir import FLAG_PROPERTIES, ZIL_VERBS
from .constants import M_TO_VERB
from .identifiers import as_object, routine_call_name, routine_dot_name, sanitize_ident, substrate_receiver

if TYPE_CHECKING:
    from . import ZilTranslator


Handler = Callable[["ZilTranslator", list], str]
"""
Expression-handler protocol.

:param translator: The active :class:`ZilTranslator` instance.
:param node: ZIL form to translate; ``node[0]`` is the head atom.
:returns: A Python expression string.
"""


def _h_btst(t: "ZilTranslator", node: list) -> str:
    """Translate ``<BTST a b>`` (bit-test) as ``((a or 0) & (b or 0)) != 0``."""
    if len(node) < 3:
        return _h_default(t, node)
    a = t._translate_expr(node[1])
    b = t._translate_expr(node[2])
    # `or 0` guards None zstate values (unpopulated parser globals).
    return f"((({a}) or 0) & (({b}) or 0)) != 0"


def _h_bor(t: "ZilTranslator", node: list) -> str:
    """Translate ``<BOR ...>`` (bitwise OR) as a parenthesised ``|`` chain."""
    if len(node) < 3:
        return _h_default(t, node)
    args_expr = " | ".join(f"(({t._translate_expr(a)}) or 0)" for a in node[1:])
    return f"({args_expr})"


def _h_band(t: "ZilTranslator", node: list) -> str:
    """Translate ``<BAND ...>`` (bitwise AND) as a parenthesised ``&`` chain."""
    if len(node) < 3:
        return _h_default(t, node)
    args_expr = " & ".join(f"(({t._translate_expr(a)}) or 0)" for a in node[1:])
    return f"({args_expr})"


def _h_msb(t: "ZilTranslator", node: list) -> str:
    """Translate ``<MSB word>`` — the ZIL library macro ``<BAND word #2 1111111100000000>``.

    Masks the high byte of a 16-bit word (``& 0xff00`` = ``& 65280``); Beyond
    Zork uses it to decode the exit-type field of an ``XTYPE`` table word
    (``MSB`` = type, ``LSB`` = length).  Delegate to ``BAND`` so the ``or 0``
    null-guard stays consistent.  Without this the form emitted an undefined
    ``msb(...)`` call (NameError in ``MARK-EXITS`` / ``MARK-DIR``).
    """
    word = node[1] if len(node) > 1 else 0
    return _h_band(t, ["BAND", word, 0xFF00])


def _h_lsb(t: "ZilTranslator", node: list) -> str:
    """Translate ``<LSB word>`` — the ZIL library macro ``<BAND word 127>``.

    Masks the low 7 bits (the length field of an ``XTYPE`` word).  Delegates
    to ``BAND``; without it the form emitted an undefined ``lsb(...)`` call.
    """
    word = node[1] if len(node) > 1 else 0
    return _h_band(t, ["BAND", word, 127])


def _h_dless_p(t: "ZilTranslator", node: list) -> str:
    """Translate ``<DLESS? var val>`` — Z-machine ``dec_chk``.

    Decrement ``var`` by one, then test whether it is now less than ``val``.
    Emitted as a walrus so the decrement side-effect happens in expression
    position (RestrictedPython compiles ``:=``).  Used as the loop-step test
    in ``MARK-EXITS`` and other direction/counter loops.  Without this the
    form emitted an undefined ``dless_p(...)`` call.
    """
    var = t._translate_expr(node[1]) if len(node) > 1 else "0"
    val = t._translate_expr(node[2]) if len(node) > 2 else "0"
    if var.isidentifier():
        return f"({var} := {var} - 1) < {val}"
    # Non-identifier target can't be walrus-assigned; compare read-only.
    return f"({var} - 1) < {val}"


def _h_igrtr_p(t: "ZilTranslator", node: list) -> str:
    """Translate ``<IGRTR? var val>`` — Z-machine ``inc_chk``.

    Increment ``var`` by one, then test whether it is now greater than
    ``val``.  Walrus companion to :func:`_h_dless_p`.  Without this the form
    emitted an undefined ``igrtr_p(...)`` call.
    """
    var = t._translate_expr(node[1]) if len(node) > 1 else "0"
    val = t._translate_expr(node[2]) if len(node) > 2 else "0"
    if var.isidentifier():
        return f"({var} := {var} + 1) > {val}"
    return f"({var} + 1) > {val}"


def _h_cond(t: "ZilTranslator", node: list) -> str:
    """Translate expression-context COND as a chained right-to-left ternary."""
    expr = "None"
    for clause in reversed(list(node[1:])):
        if not isinstance(clause, (list, tuple)) or not clause:
            continue
        test = clause[0]
        body = list(clause[1:])
        test_is_else = isinstance(test, str) and test.upper() in ("ELSE", "T", "TRUE")
        value_expr = t._translate_expr(body[-1]) if body else t._translate_expr(test)
        if test_is_else:
            expr = value_expr
        else:
            test_expr = t._translate_expr(test)
            expr = f"({value_expr} if {test_expr} else {expr})"
    return expr


def _h_apply(t: "ZilTranslator", node: list) -> str:
    """Translate ``<APPLY <GETP obj ,P?ACTION> ,M-X>`` as a guarded ``invoke_verb``."""
    if len(node) < 3:
        return _h_default(t, node)
    target = node[1]
    arg = node[2]
    verb_name = None
    if isinstance(arg, str):
        arg_atom = arg.lstrip(",.").upper()
        verb_name = M_TO_VERB.get(arg_atom)
    if verb_name and isinstance(target, list) and len(target) >= 3:
        t_head = target[0]
        if isinstance(t_head, str) and t_head.upper() in ("GETP", "GETPT"):
            obj_expr = t._translate_expr(target[1])
            # recurse=False prevents an inheriting substrate from looping forever.
            return (
                f"({obj_expr}.invoke_verb({verb_name!r}) "
                f"if {obj_expr} is not None and {obj_expr}.has_verb({verb_name!r}, recurse=False) "
                f"else None)"
            )
    # Routine arrives through a variable / unmatched shape — route to the
    # substrate ``apply`` helper (HERE-relative M-* dispatch, else None).  A bare
    # ``apply(...)`` would NameError — Python 3 removed the builtin.
    call_args = ", ".join(t._translate_expr(a) for a in node[1:])
    return f"_.apply({call_args})"


def _h_add(t: "ZilTranslator", node: list) -> str:
    """Translate ``<+ ...>`` / ``<ADD ...>`` as a parenthesised ``+`` chain."""
    return "(" + " + ".join(t._translate_expr(a) for a in node[1:]) + ")"


def _h_sub(t: "ZilTranslator", node: list) -> str:
    """Translate ``<- ...>`` / ``<SUB ...>`` as a unary negate or ``-`` chain."""
    if len(node) == 2:
        return f"(-{t._translate_expr(node[1])})"
    return "(" + " - ".join(t._translate_expr(a) for a in node[1:]) + ")"


def _h_mul(t: "ZilTranslator", node: list) -> str:
    """Translate ``<* ...>`` / ``<MUL ...>`` as a parenthesised ``*`` chain."""
    return "(" + " * ".join(t._translate_expr(a) for a in node[1:]) + ")"


def _h_div(t: "ZilTranslator", node: list) -> str:
    """Translate ``</ ...>`` / ``<DIV ...>`` as a parenthesised ``//`` chain (integer div)."""
    return "(" + " // ".join(t._translate_expr(a) for a in node[1:]) + ")"


def _h_mod(t: "ZilTranslator", node: list) -> str:
    """Translate ``<MOD a b>`` as ``a % b``."""
    a, b = node[1], node[2]
    return f"{t._translate_expr(a)} % {t._translate_expr(b)}"


def _h_abs(t: "ZilTranslator", node: list) -> str:
    """Translate ``<ABS x>`` as ``abs(x)``."""
    return f"abs({t._translate_expr(node[1])})"


def _h_min(t: "ZilTranslator", node: list) -> str:
    """Translate ``<MIN ...>`` as ``min(...)``."""
    args_expr = ", ".join(t._translate_expr(a) for a in node[1:])
    return f"min({args_expr})"


def _h_max(t: "ZilTranslator", node: list) -> str:
    """Translate ``<MAX ...>`` as ``max(...)``."""
    args_expr = ", ".join(t._translate_expr(a) for a in node[1:])
    return f"max({args_expr})"


def _h_equal(t: "ZilTranslator", node: list) -> str:
    """
    Translate ``<EQUAL? a b ...>`` as ``==`` or ``in (...)`` membership.

    When LHS is PRSO and all operands are direction atoms, emits a
    string comparison against ``get_dobj_str()``.  See
    :doc:`/explanation/zil-importer` (Direction-token (`P?`) atoms).
    """
    if t._is_prso_atom(node[1]):
        dirs = [t._direction_string(a) for a in node[2:]]
        if all(d is not None for d in dirs):
            if len(dirs) == 1:
                return f"context.parser.get_dobj_str() == {dirs[0]!r}"
            rhs = ", ".join(repr(d) for d in dirs)
            return f"context.parser.get_dobj_str() in ({rhs})"
    if len(node) == 3:
        return f"{t._translate_expr(node[1])} == {t._translate_expr(node[2])}"
    lhs = t._translate_expr(node[1])
    rhs = ", ".join(t._translate_expr(a) for a in node[2:])
    return f"{lhs} in ({rhs})"


def _h_not_equal(t: "ZilTranslator", node: list) -> str:
    """Translate ``<N==? a b>`` / ``<N=? a b>`` as ``a != b``."""
    return f"{t._translate_expr(node[1])} != {t._translate_expr(node[2])}"


def _h_gt(t: "ZilTranslator", node: list) -> str:
    """Translate ``<G? a b>`` / ``<GRTR? a b>`` as ``a > b``."""
    return f"{t._translate_expr(node[1])} > {t._translate_expr(node[2])}"


def _h_lt(t: "ZilTranslator", node: list) -> str:
    """Translate ``<L? a b>`` / ``<LESS? a b>`` as ``a < b``."""
    return f"{t._translate_expr(node[1])} < {t._translate_expr(node[2])}"


def _h_ge(t: "ZilTranslator", node: list) -> str:
    """Translate ``<G=? a b>`` as ``a >= b``."""
    return f"{t._translate_expr(node[1])} >= {t._translate_expr(node[2])}"


def _h_le(t: "ZilTranslator", node: list) -> str:
    """Translate ``<L=? a b>`` as ``a <= b``."""
    return f"{t._translate_expr(node[1])} <= {t._translate_expr(node[2])}"


def _h_zero_p(t: "ZilTranslator", node: list) -> str:
    """Translate ``<0? x>`` / ``<ZERO? x>`` as ``x == 0``."""
    return f"{t._translate_expr(node[1])} == 0"


def _h_one_p(t: "ZilTranslator", node: list) -> str:
    """Translate ``<1? x>`` as ``x == 1``."""
    return f"{t._translate_expr(node[1])} == 1"


def _h_and(t: "ZilTranslator", node: list) -> str:
    """Translate ``<AND ...>`` (expression context) as a parenthesised ``and`` chain."""
    # Parens preserve ZIL grouping under Python's `and > or` precedence.
    return "(" + " and ".join(t._translate_expr(a) for a in node[1:]) + ")"


def _h_or(t: "ZilTranslator", node: list) -> str:
    """Translate ``<OR ...>`` (expression context) as a parenthesised ``or`` chain."""
    return "(" + " or ".join(t._translate_expr(a) for a in node[1:]) + ")"


_SIMPLE_OPERAND_RE = re.compile(r"^([A-Za-z_][\w\.\[\]\(\)]*|-?\d+(\.\d+)?)$")


def _is_simple_operand(expr: str) -> bool:
    """True when ``expr`` is an identifier, attribute chain, or numeric literal.

    Used to decide whether ``not (a == b)`` can safely collapse to ``a != b``
    without risking the ``not``/``or``/``and`` precedence trap.
    """
    return bool(_SIMPLE_OPERAND_RE.match(expr.strip()))


def _h_not(t: "ZilTranslator", node: list) -> str:
    """Translate ``<NOT x>`` as ``not x``, collapsing comparisons to their inverse.

    Only collapses when both operands are simple identifiers/calls — once
    a sub-expression carries ``or``/``and``/``==`` etc. the precedence trap
    around ``not`` breaks the intended semantics, so we leave the explicit
    ``not (...)`` form alone (the translator emits those operands without
    parens, so flattening would shift binding the wrong way).
    """
    inner = node[1]
    if isinstance(inner, list) and len(inner) >= 2 and isinstance(inner[0], str):
        head = inner[0].upper()
        if head in ("==?", "EQUAL?") and len(inner) == 3:
            left = t._translate_expr(inner[1])
            right = t._translate_expr(inner[2])
            if _is_simple_operand(left) and _is_simple_operand(right):
                return f"{left} != {right}"
        elif head in ("0?", "ZERO?") and len(inner) == 2:
            arg = t._translate_expr(inner[1])
            if _is_simple_operand(arg):
                return f"{arg} != 0"
        elif head == "1?" and len(inner) == 2:
            arg = t._translate_expr(inner[1])
            if _is_simple_operand(arg):
                return f"{arg} != 1"
    return f"not {t._translate_expr(inner)}"


def _h_fset_p(t: "ZilTranslator", node: list) -> str:
    """Translate ``<FSET? obj flag>`` as ``obj.flag(flag)``, honouring FLAG_PROPERTIES polarity."""
    obj = t._translate_expr(node[1]) if len(node) > 1 else "None"
    flag_node = node[2] if len(node) > 2 else None
    flag = t._translate_flag_name(flag_node) if flag_node is not None else '"unknown"'
    # ``<LOC obj>`` is None for a room (rooms have no location); Z-machine
    # ``<FSET? <null> flag>`` is a safe False, but Python ``None.flag()``
    # raises (``take bridge`` → PRE-TAKE → LOC-CLOSED? crashed here).  When
    # the operand is a None-returning ``<LOC …>`` form, null-guard the check.
    nullable = isinstance(node[1], list) and len(node[1]) > 0 and str(node[1][0]).upper() == "LOC"
    if nullable:
        check = f"({obj} is not None and {obj}.flag({flag}))"
        inverted = f"({obj} is None or not {obj}.flag({flag}))"
    else:
        check = f"{obj}.flag({flag})"
        inverted = f"(not {check})"
    # FLAG_PROPERTIES polarity: NDESCBIT → ("obvious", False) inverts the check.
    if isinstance(flag_node, list) and len(flag_node) == 1:
        inner = flag_node[0]
    else:
        inner = flag_node
    if isinstance(inner, str):
        upper = inner.lstrip(",.").upper()
        if upper in FLAG_PROPERTIES:
            _prop, set_value = FLAG_PROPERTIES[upper]
            if set_value is False:
                return inverted
    return check


def _h_in_p(t: "ZilTranslator", node: list) -> str:
    """Translate ``<IN? obj container>`` as ``obj.location == container``.

    For parser pseudo-vars (``prso``/``prsi``), emit a null-safe form —
    Z-machine semantics treat ``<IN?>`` on the null object as false, but
    the parser may dispatch a verb with a missing PRSI when the topic
    didn't resolve (e.g. ``ask prosser about bypass``).
    """
    obj = as_object(t._translate_expr(node[1])) if len(node) > 1 else "None"
    container = t._translate_expr(node[2]) if len(node) > 2 else "None"
    if obj.strip() in ("prso", "prsi"):
        return f"({obj} is not None and {obj}.location == {container})"
    return f"{obj}.location == {container}"


def _h_loc(t: "ZilTranslator", node: list) -> str:
    """Translate ``<LOC obj>`` as ``obj.location`` (null-safe for parser pseudo-vars)."""
    obj = as_object(t._translate_expr(node[1])) if len(node) > 1 else "None"
    if obj.strip() in ("prso", "prsi"):
        return f"({obj}.location if {obj} is not None else None)"
    return f"{obj}.location"


def _h_first(t: "ZilTranslator", node: list) -> str:
    """Translate ``<FIRST? obj>`` / ``<FIRST obj>`` as ``obj.contents.first()``.

    XZIP-dialect games (Beyond Zork) write object-walk loops that test the
    result with ``<ZERO? .OBJ>`` / ``== 0``; ``.first()`` returns ``None`` on an
    empty container and ``None != 0``, so those loops run off the end.  Coerce
    the empty case to ``0`` (ZIL FALSE) for that dialect only — a real child is
    truthy so ``or 0`` fires solely on None.  EZIP loops use truthy/``is None``
    tests that already handle ``None``, so they keep the plain form unchanged.
    """
    obj = as_object(t._translate_expr(node[1])) if len(node) > 1 else "None"
    # ORM .first() — `next(iter(...))` isn't sandboxed.
    if t.game_config.exit_tables:
        return f"({obj}.contents.first() or 0)"
    return f"{obj}.contents.first()"


def _h_assigned_p(t: "ZilTranslator", node: list) -> str:
    """Translate ``<ASSIGNED? .VAR>`` — was an optional ``"OPT"`` param supplied?

    The generator defaults an unsupplied optional routine parameter to ``None``
    (``except_v = args[3] if len(args) > 3 else None``), so a supplied value is
    exactly ``var is not None`` — ZIL never passes ``None`` as a real argument.
    """
    if len(node) < 2:
        return "False"
    return f"({t._translate_expr(node[1])} is not None)"


def _h_next(t: "ZilTranslator", node: list) -> str:
    """Translate ``<NEXT? obj>`` / ``<NEXT obj>`` as ``_.next_sibling(obj)``.

    ``next_sibling`` returns ``None`` when there is no next sibling.  For the
    XZIP dialect (whose loops terminate on ``<ZERO? .OBJ>`` / ``== 0``) coerce
    that to ``0`` (ZIL FALSE) so the terminators fire; EZIP's truthy/``is None``
    tests already handle ``None``, so leave the substrate verb game-neutral and
    keep the plain call there.
    """
    obj = as_object(t._translate_expr(node[1])) if len(node) > 1 else "None"
    if t.game_config.exit_tables:
        return f"(_.next_sibling({obj}) or 0)"
    return f"_.next_sibling({obj})"


def _h_global_in_p(t: "ZilTranslator", node: list) -> str:
    """Translate ``<GLOBAL-IN? obj loc>`` as ``obj.global_in(loc)``."""
    obj = t._translate_expr(node[1]) if len(node) > 1 else "None"
    loc = t._translate_expr(node[2]) if len(node) > 2 else "None"
    return f"{obj}.global_in({loc})"


def _h_rfatal(_t: "ZilTranslator", _node: list) -> str:
    """Translate ``<RFATAL>`` as the constant ``2`` (ZIL fatal-branch sentinel)."""
    return "2"


def _table_op(t: "ZilTranslator", xzip_verb: str, ezip_verb: str) -> str:
    """Pick the substrate verb name for a table op by dialect.

    XZIP (Beyond Zork) uses the byte-addressed pointer model (``zaddr_*`` in
    ``verbs/system/ztables.py``) so its buffer-scroll routines can do pointer
    arithmetic; EZIP keeps the list-based primitives (``verbs/system/tables.py``)
    verbatim.
    """
    return xzip_verb if t.game_config.exit_tables else ezip_verb


def _h_put(t: "ZilTranslator", node: list) -> str:
    """Translate ``<PUT tbl idx val>`` as a table write."""
    table = t._translate_expr(node[1]) if len(node) > 1 else "None"
    idx = t._translate_expr(node[2]) if len(node) > 2 else "0"
    val = t._translate_expr(node[3]) if len(node) > 3 else "None"
    return f"_.{_table_op(t, 'zaddr_put', 'table_put')}({table}, {idx}, {val})"


def _h_rest(t: "ZilTranslator", node: list) -> str:
    """Translate ``<REST tbl offset>`` (sub-table view / pointer shifted by ``offset``)."""
    table = t._translate_expr(node[1]) if len(node) > 1 else "None"
    offset = t._translate_expr(node[2]) if len(node) > 2 else "2"
    return f"_.{_table_op(t, 'zaddr_rest', 'rest')}({table}, {offset})"


def _h_putb(t: "ZilTranslator", node: list) -> str:
    """Translate ``<PUTB tbl idx val>`` — byte write.

    In the EZIP list model one slot is one ZIL word, so a byte write is the same
    as ``PUT``; in the XZIP byte-addressed model it writes one byte cell.
    """
    table = t._translate_expr(node[1]) if len(node) > 1 else "None"
    idx = t._translate_expr(node[2]) if len(node) > 2 else "0"
    val = t._translate_expr(node[3]) if len(node) > 3 else "None"
    return f"_.{_table_op(t, 'zaddr_put', 'table_put')}({table}, {idx}, {val})"


def _h_getpt(t: "ZilTranslator", node: list) -> str:
    """Translate ``<GETPT obj prop>`` (property-table address).

    In the Z-machine ``GETPT`` returns the address of a property's table; in
    our object model a table-valued property *is* the table, so this is the
    same as ``GETP``.
    """
    obj = as_object(t._translate_expr(node[1])) if len(node) > 1 else "None"
    prop = t._translate_prop_name(node[2]) if len(node) > 2 else '"unknown"'
    return f"{obj}.getp({prop})"


def _h_lowcore(t: "ZilTranslator", node: list) -> str:
    """Translate ``<LOWCORE field [...]>`` (Z-machine header read) as
    ``_.lowcore(...)``.

    There is no story-file header at runtime, so the substrate returns the
    benign baseline (0) — see ``verbs/system/zmachine.py``. A bare ``lowcore(…)``
    would NameError."""
    call_args = ", ".join(t._translate_expr(a) for a in node[1:])
    return f"_.lowcore({call_args})"


def _h_font(_t: "ZilTranslator", _node: list) -> str:
    """Translate ``<FONT n>`` as a no-op returning ``0``.

    Beyond Zork switches to font 3 (character-graphics) to draw the auto-map
    box; we render those glyphs as Unicode text through the normal pipeline,
    so font selection is inert.  The return value (prior font) is unused.
    """
    return "0"


def _h_intbl_p(t: "ZilTranslator", node: list) -> str:
    """Translate ``<INTBL? val tbl len [stride]>`` — Z-machine table search.

    Returns the matching sub-table offset or ``False``.  Delegated to the
    ``_.intbl_p`` substrate verb (``verbs/system/tables.py``).
    """
    val = t._translate_expr(node[1]) if len(node) > 1 else "None"
    tbl = t._translate_expr(node[2]) if len(node) > 2 else "None"
    length = t._translate_expr(node[3]) if len(node) > 3 else "0"
    stride = t._translate_expr(node[4]) if len(node) > 4 else "1"
    return f"_.{_table_op(t, 'zaddr_intbl_p', 'intbl_p')}({val}, {tbl}, {length}, {stride})"


def _h_copyt(t: "ZilTranslator", node: list) -> str:
    """Translate ``<COPYT src dest count>`` — table copy.

    A negative ``count`` is the ZIL overlap convention (copy backward).
    Delegated to the ``_.copyt`` substrate verb.
    """
    src = t._translate_expr(node[1]) if len(node) > 1 else "None"
    dest = t._translate_expr(node[2]) if len(node) > 2 else "None"
    count = t._translate_expr(node[3]) if len(node) > 3 else "0"
    return f"_.{_table_op(t, 'zaddr_copyt', 'copyt')}({src}, {dest}, {count})"


def _h_printt(t: "ZilTranslator", node: list) -> str:
    """Translate ``<PRINTT tbl width [height]>`` — print a byte grid.

    Emits ``height`` rows of ``width`` characters from the table to the
    current window.  Delegated to the ``_.printt`` substrate verb.
    """
    tbl = t._translate_expr(node[1]) if len(node) > 1 else "None"
    width = t._translate_expr(node[2]) if len(node) > 2 else "0"
    height = t._translate_expr(node[3]) if len(node) > 3 else "1"
    return f"_.printt({tbl}, {width}, {height})"


def _h_inc(t: "ZilTranslator", node: list) -> str:
    """Translate ``<INC var>`` (increment in place) as a walrus ``(var := var + 1)``.

    The walrus keeps the mutation in expression position (RestrictedPython
    compiles ``:=``); as a bare statement it still increments.  A non-identifier
    target degrades to a read-only ``(expr + 1)``.
    """
    var = t._translate_expr(node[1]) if len(node) > 1 else "0"
    return f"({var} := {var} + 1)" if var.isidentifier() else f"({var} + 1)"


def _h_dec(t: "ZilTranslator", node: list) -> str:
    """Translate ``<DEC var>`` (decrement in place) as a walrus ``(var := var - 1)``."""
    var = t._translate_expr(node[1]) if len(node) > 1 else "0"
    return f"({var} := {var} - 1)" if var.isidentifier() else f"({var} - 1)"


def _h_read(t: "ZilTranslator", _node: list) -> str:
    """Translate ``<READ ...>`` based on surrounding context.

    Inside a ``<REPEAT>`` (translated as ``while True``), READ has to
    exit the loop — otherwise the loop's ``parser.words[0]`` repeats
    forever (LOUD-ROOM-FCN, FINISH).  Outside a loop, READ is a
    "press ENTER to continue" pause; in DjangoMOO the right wiring is
    ``moo.sdk.output.open_input(player, prompt, callback_verb)``, but
    that needs the translator to split the routine into pre-READ and
    post-READ halves and emit a continuation verb.  For now, outside a
    loop emit ``pass`` so post-READ code runs immediately — the
    player sees the prompt and then the next print() output without
    the pause.  Functionally correct for V-SCORE / V-QUIT / V-VERIFY
    (just no pause); a future pass should wire open_input + callback.

    Returns ``True`` from inside a REPEAT so the M-ENTER caller (exit
    ``move`` verb) sees a truthy "handled" signal and skips the
    post-enter M-LOOK — Loud Room would otherwise double-render the
    room desc (FIRST-LOOK + move.py's subsequent invoke_verb("look")).
    """
    if t._repeat_depth > 0:
        return "return True"
    return "pass"


def _h_get(t: "ZilTranslator", node: list) -> str:
    """
    Translate ``<GET tbl idx>`` / ``<GETB tbl idx>`` (table read).

    ``P-LEXV`` maps to ``parser.words``; the literal-zero table maps to
    the synthesized V-VERSION release/serial bytes.
    """
    tbl_node = node[1] if len(node) > 1 else None
    idx_node = node[2] if len(node) > 2 else None
    if isinstance(tbl_node, str) and tbl_node.lstrip(",.").upper() == "P-LEXV":
        # context.parser is None when a verb is invoked programmatically
        # (e.g. enterfunc fired by celery without a parsed command); guard
        # so the inline P-LEXV access doesn't AttributeError on .words.
        if isinstance(idx_node, str) and idx_node.lstrip(",.").upper() == "P-LEXWORDS":
            return "(len(context.parser.words) if context.parser is not None else 0)"
        idx_expr = t._translate_expr(idx_node) if idx_node is not None else "1"
        return (
            f"(context.parser.words[({idx_expr}) - 1] "
            f"if context.parser is not None and len(context.parser.words) >= ({idx_expr}) "
            f'else "")'
        )
    if isinstance(tbl_node, int) and tbl_node == 0:
        idx = t._translate_expr(idx_node) if idx_node is not None else "0"
        return f'_.table_get(_.get_property("zstate_version_table"), {idx})'
    table = t._translate_expr(tbl_node) if tbl_node is not None else "None"
    idx = t._translate_expr(idx_node) if idx_node is not None else "0"
    return f"_.{_table_op(t, 'zaddr_get', 'table_get')}({table}, {idx})"


def _h_ascii(t: "ZilTranslator", node: list) -> str:
    """Translate ``<ASCII char>`` — the char's codepoint.

    In the Z-machine a character and its code are the same integer, so ASCII is
    the identity on its argument (a ``!\\X`` char literal already tokenises to
    the codepoint).  Used in ``<PRINTC %<ASCII !\\:>>``-style status formatting.
    """
    return t._translate_expr(node[1]) if len(node) > 1 else "0"


def _h_getp(t: "ZilTranslator", node: list) -> str:
    """Translate ``<GETP obj prop>`` as ``obj.getp(prop)``."""
    obj = as_object(t._translate_expr(node[1])) if len(node) > 1 else "None"
    prop = t._translate_prop_name(node[2]) if len(node) > 2 else '"unknown"'
    return f"{obj}.getp({prop})"


def _h_putp_expr(t: "ZilTranslator", node: list) -> str:
    """Translate ``<PUTP obj prop val>`` (expression context) as ``obj.set_property(...)``."""
    obj = as_object(t._translate_expr(node[1])) if len(node) > 1 else "None"
    prop = t._translate_prop_name(node[2]) if len(node) > 2 else '"unknown"'
    val = t._translate_expr(node[3]) if len(node) > 3 else "None"
    return f"{obj}.set_property({prop}, {val})"


_PARSER_STATE_SLOTS = frozenset({"PRSA", "PRSO", "PRSI", "P-PRSA", "P-PRSO", "P-PRSI", "P-LEXV"})


def _h_setg_expr(t: "ZilTranslator", node: list) -> str:
    """Translate ``<SETG key val>`` (expression) as ``context.player.zstate_set(...)``."""
    key = str(node[1]).upper() if len(node) > 1 else "UNKNOWN"
    if key in _PARSER_STATE_SLOTS:
        return "None  # SETG of parser-state slot is a no-op in DjangoMOO"
    val = t._translate_expr(node[2]) if len(node) > 2 else "None"
    return f"context.player.zstate_set({repr(key)}, {val})"


def _h_gval(t: "ZilTranslator", node: list) -> str:
    """Translate ``<GVAL key>`` — ``GLOBAL_MAP`` entry or ``zstate_get`` fallback."""
    key = str(node[1]).upper() if len(node) > 1 else "UNKNOWN"
    if key in t._global_map:
        return t._global_map[key]
    return f"context.player.zstate_get({repr(key)})"


def _h_tell_expr(t: "ZilTranslator", node: list) -> str:
    """Translate ``<TELL ...>`` (expression context) via :meth:`_translate_tell`."""
    return t._translate_tell(node)


def _h_crlf_expr(_t: "ZilTranslator", _node: list) -> str:
    """Translate ``<CRLF>`` (expression) as a bare ``print()``."""
    return "print()"


def _h_print_expr(t: "ZilTranslator", node: list) -> str:
    """Translate ``<PRINT val>`` (expression) as ``print(val)``."""
    val = t._translate_expr(node[1]) if len(node) > 1 else '""'
    return f"print({val})"


def _h_printi_expr(t: "ZilTranslator", node: list) -> str:
    """Translate ``<PRINTI "lit">`` (expression) as ``print("lit", end='')``."""
    val = t._translate_expr(node[1]) if len(node) > 1 else '""'
    return f"print({val}, end='')"


def _h_printn_expr(t: "ZilTranslator", node: list) -> str:
    """Translate ``<PRINTN val>`` (expression) as ``print(str(val), end='')``."""
    val = t._translate_expr(node[1]) if len(node) > 1 else "0"
    return f"print(str({val}), end='')"


def _h_printc_expr(t: "ZilTranslator", node: list) -> str:
    """Translate ``<PRINTC val>`` (expression) as ``print(chr(val), end='')``."""
    val = t._translate_expr(node[1]) if len(node) > 1 else "0"
    return f"print(chr({val}), end='')"


def _h_printd_expr(t: "ZilTranslator", node: list) -> str:
    """Translate ``<PRINTD obj>`` (expression) as ``print(obj.desc(), end='')``."""
    obj = t._translate_expr(node[1]) if len(node) > 1 else "None"
    return f"print({obj}.desc(), end='')"


def _h_pick_one(t: "ZilTranslator", node: list) -> str:
    """Translate ``<PICK-ONE table>`` as ``_.pick(table)``."""
    table = t._translate_expr(node[1]) if len(node) > 1 else '"unknown"'
    return f"_.pick({table})"


def _h_verb_p(t: "ZilTranslator", node: list) -> str:
    """Translate ``<VERB? X Y...>`` as a player-verb membership test against ``the_player_verb``."""
    verbs = [str(v).upper() for v in node[1:] if isinstance(v, str)]
    aliases: list[str] = []
    for v in verbs:
        # Normalize hyphens to underscores: ``invoked_verb_name`` returns
        # the registered verb name (e.g. ``lie_down`` for SYNTAX ``LIE
        # DOWN``).  The ZIL_VERBS fallback uses ``v.lower()`` which keeps
        # the hyphen (``lie-down``), so the equality check would never
        # match the underscored runtime value.  Existing dict entries
        # like ``take-off`` get the same treatment for consistency.
        aliases.extend(alias.replace("-", "_") for alias in ZIL_VERBS.get(v, [v.lower()]))
    t._verbs_handled.update(aliases)
    # See explanation/zil-importer (M-clause player-verb binding).
    var = "the_player_verb"
    if len(aliases) == 1:
        return f"{var} == {aliases[0]!r}"
    return f"{var} in {aliases!r}"


def _h_running(_t: "ZilTranslator", node: list) -> str:
    """Translate ``<RUNNING? ,I-FOO>`` as a queue-membership check.

    Canonical ``RUNNING?`` walks the ``C-TABLE`` clock-interrupt table,
    but DjangoMOO schedules daemons through the per-player
    ``zstate_queue`` (``verbs/system/queue.py``) and never populates
    ``C-TABLE`` — so the auto-translated routine always returns False and
    every ``RUNNING?``-gated branch (notably the improbability-drive win
    in ``SWITCH-F``: ``<RUNNING? ,I-TEA>``) is dead code.  Worse, the
    default emission renders the daemon atom ``,I-TEA`` as a CALL
    (``_.thing.i_tea()``), executing the daemon as a side effect on every
    check.  Emit the kebab-case NAME string instead and let the
    hand-written ``is_running`` predicate (``verbs/hhg/thing/predicates/``)
    look it up in the queue.  HHG-only: zork1 has no ``RUNNING?`` and
    ``RUNNING?`` is in ``_SKIP_ROUTINES`` so the C-TABLE version isn't emitted.
    """
    routine = str(node[1]).lower().replace("_", "-") if len(node) > 1 else "unknown"
    return f"_.thing.is_running({routine!r})"


def _h_prso_p(t: "ZilTranslator", node: list) -> str:
    """Translate ``<PRSO? X Y...>`` as ``prso == X`` / ``prso in (X, Y)``.

    ZIL's ``PRSO?`` checks whether the parser's direct object matches any
    of the listed atoms. Without this handler the translator falls
    through to a generic routine call and emits ``prso_p(...)``, which
    raises ``NameError`` at runtime (PRE-TAKE and friends).

    When every operand is a direction atom (``<PRSO? ,P?SOUTH>``), the
    parsed "object" is a movement direction, which DjangoMOO never resolves
    to an ``Object`` — so a ``prso ==`` comparison is dead (the ``P?<dir>``
    atom has no seeded value).  Mirror :func:`_h_equal` and compare against
    ``get_dobj_str()`` instead.  This is what unblocks the post-airlock Dark
    exit (``go south`` → LEAVE-DARK) in HHG's DARK-FUNCTION.
    """
    dirs = [t._direction_string(a) for a in node[1:]]
    if node[1:] and all(d is not None for d in dirs):
        if len(dirs) == 1:
            return f"context.parser.get_dobj_str() == {dirs[0]!r}"
        rhs = ", ".join(repr(d) for d in dirs)
        return f"context.parser.get_dobj_str() in ({rhs})"
    targets = [t._translate_expr(arg) for arg in node[1:]]
    if not targets:
        return "False"
    if len(targets) == 1:
        return f"prso == {targets[0]}"
    return f"prso in ({', '.join(targets)})"


def _h_here_p(t: "ZilTranslator", node: list) -> str:
    """Translate ``<HERE? X Y...>`` as a current-room membership test.

    ZIL's ``HERE?`` macro (``<MULTIFROB HERE .ATMS>``) checks whether the
    player's current room (``,HERE``) equals any of the listed room atoms.
    Without this handler the form falls through to a generic routine call
    and emits ``here_p(...)``, which raises ``NameError`` at runtime — every
    room-description routine that branches on ``HERE?`` (Beyond Zork's
    ``FARM-ROOM`` describe path, etc.) hits it.  Mirror :func:`_h_prso_p`
    but compare against ``context.player.here()`` (how the ``HERE`` global
    is rendered, see ``translator/constants.py``).
    """
    targets = [t._translate_expr(arg) for arg in node[1:]]
    if not targets:
        return "False"
    if len(targets) == 1:
        return f"context.player.here() == {targets[0]}"
    return f"context.player.here() in ({', '.join(targets)})"


def _h_is_p(t: "ZilTranslator", node: list) -> str:
    """Translate ``<IS? obj flag>`` — the ZIL library macro ``<FSET? obj flag>``.

    Beyond Zork defines ``IS?`` as ``<DEFMAC IS? ('OBJ 'FLAG) <FORM FSET?
    .OBJ .FLAG>>`` and uses it heavily in the describe routines.  The arg
    shape matches ``FSET?`` exactly, so delegate to its handler (which
    honours FLAG_PROPERTIES polarity and the ``<LOC …>`` null-guard).
    Without this the form emitted an undefined ``is_p(...)`` call.
    """
    return _h_fset_p(t, node)


def _h_t_p(t: "ZilTranslator", node: list) -> str:
    """Translate ``<T? term>`` — the ZIL library macro ``<NOT <ZERO? term>>``.

    A truthiness test (non-zero).  Rewrite to the macro's definition and
    delegate to the ``NOT`` handler, which collapses ``NOT ZERO?`` to
    ``term != 0``.  Without this the form emitted an undefined ``t_p(...)``.
    """
    term = node[1] if len(node) > 1 else 0
    return _h_not(t, ["NOT", ["ZERO?", term]])


def _h_prsi_p(t: "ZilTranslator", node: list) -> str:
    """Translate ``<PRSI? X Y...>`` as ``prsi == X`` / ``prsi in (X, Y)``."""
    targets = [t._translate_expr(arg) for arg in node[1:]]
    if not targets:
        return "False"
    if len(targets) == 1:
        return f"prsi == {targets[0]}"
    return f"prsi in ({', '.join(targets)})"


def _h_random(t: "ZilTranslator", node: list) -> str:
    """Translate ``<RANDOM N>`` as ``random.randint(1, N)``."""
    n = t._translate_expr(node[1]) if len(node) > 1 else "6"
    return f"random.randint(1, {n})"


def _h_prob(t: "ZilTranslator", node: list) -> str:
    """Translate ``<PROB N>`` (chance%) as ``random.randint(1, 100) <= N``."""
    n = t._translate_expr(node[1]) if len(node) > 1 else "50"
    return f"random.randint(1, 100) <= {n}"


def _h_score_expr(t: "ZilTranslator", node: list) -> str:
    """Translate ``<SCORE delta>`` (expression) as ``_.score_update(delta)``."""
    delta = t._translate_expr(node[1]) if len(node) > 1 else "0"
    return f"_.score_update({delta})"


def _h_jigs_up_expr(t: "ZilTranslator", node: list) -> str:
    """Translate ``<JIGS-UP msg>`` (expression) as ``_.jigs_up(msg)``."""
    msg = t._translate_expr(node[1]) if len(node) > 1 else '""'
    return f"_.jigs_up({msg})"


def _h_quit_expr(_t: "ZilTranslator", _node: list) -> str:
    """Translate ``<QUIT>`` (expression) as ``None`` (no value)."""
    return "None"


def _h_falsy(_t: "ZilTranslator", _node: list) -> str:
    """Translate ``<RESTART>`` / ``<RESTORE>`` / ``<SAVE>`` (expression) as ``False``."""
    return "False"


def _h_int_expr(_t: "ZilTranslator", node: list) -> str:
    """Translate bare ``<INT routine>`` (expression context) as ``None``.

    In canonical ZIL, ``<INT R>`` returns the I-TABLE slot for routine
    ``R`` (a 4-element table: ``[routine-id, enabled?, ticks-remaining,
    period]``) so the body can mutate the slot in place — e.g. the
    ``i-sword`` canonical body does ``<SET DEM <INT I-SWORD>>`` and later
    ``<PUT .DEM ,C-ENABLED? 0>`` to self-disable.

    DjangoMOO replaces the I-TABLE with a per-name ``zstate_queue``
    list; there is no addressable slot per routine.  Without an
    explicit handler the form falls through to the default function-call
    emission which translates ``<INT I-SWORD>`` to
    ``_.thing.int(_.thing.i_sword())`` — that is (a) a call to
    a non-existent ``int`` verb and (b) an immediate recursive invocation
    of the enclosing routine (``i-sword`` calling itself), which deadlocks
    the celery worker as soon as the daemon fires.

    Emitting ``None`` for the value keeps the canonical ``<PUT .DEM ...>``
    expression valid (the SDK's ``table_put`` no-ops on a non-list
    receiver) and effectively makes the slot-mutation a no-op.
    Disable-from-within-self is best expressed via ``return False`` from
    the daemon body, which the queue treats as "drop me", or via
    ``_.cancel("<routine>")`` / ``_.unschedule_realtime("<routine>")`` —
    none of those need INT.

    Wrapped forms (``<ENABLE <INT R>>``, ``<DISABLE <INT R>>``) are
    handled separately by ``_h_enable`` / ``_h_disable`` in
    :mod:`stmt_handlers` and never fall through here.
    """
    return "None"


def _h_object_pname(t: "ZilTranslator", node: list) -> str:
    """Translate ``<OBJECT-PNAME obj>`` (printable name) as ``obj.desc()``."""
    obj = t._translate_expr(node[1]) if len(node) > 1 else "None"
    return f"{obj}.desc()"


def _h_openable_p(t: "ZilTranslator", node: list) -> str:
    """Translate ``<OPENABLE? obj>`` as ``obj.flag("openable")``."""
    obj = t._translate_expr(node[1]) if len(node) > 1 else "None"
    return f'{obj}.flag("openable")'


def _h_perform_expr(t: "ZilTranslator", node: list) -> str:
    """Translate ``<PERFORM verb prso prsi>`` (expression) as ``_.perform(...)``."""
    verb_atom = t._translate_expr(node[1]) if len(node) > 1 else '"unknown"'
    prso = t._translate_expr(node[2]) if len(node) > 2 else "None"
    prsi = t._translate_expr(node[3]) if len(node) > 3 else "None"
    return f"_.perform({verb_atom}, {prso}, {prsi})"


def _h_set_expr(t: "ZilTranslator", node: list) -> str:
    """Translate ``<SET var val>`` (expression) as a walrus binding ``(var := val)``."""
    var = sanitize_ident(str(node[1])) if len(node) > 1 else "v_unknown"
    val = t._translate_expr(node[2]) if len(node) > 2 else "None"
    return f"({var} := {val})"


# Routines whose body uses ``<READ>`` outside ``<REPEAT>`` and recurses
# on unmatched input.  In ZIL the recursion is bounded because READ
# pauses for new keyboard input; in DjangoMOO ``<READ>`` outside a
# REPEAT loop is a no-op (``_h_read`` returns ``"pass"``), so the
# recursion runs to RecursionError before the player can type
# anything.  Suppressing the self-recursive call lets the verb exit
# cleanly.  Only the routine's own self-recursion is broken — external
# callers (V-SCORE, JIGS-UP, etc.) still call ``finish()`` normally.
_READ_RECURSIVE_ROUTINES = frozenset({"FINISH"})


def _h_default(t: "ZilTranslator", node: list) -> str:
    """
    Fallback handler — routine-call / bare-atom / single-element list.

    Known routines dispatch on ``$thing`` (dot-syntax or
    ``invoke_verb``); unknown heads emit a plain function call.
    """
    if not node or not isinstance(node[0], str):
        return "None"
    head_upper = node[0].upper()
    routine_upper = t.routine.name.upper()
    suppress_self_recursion = head_upper == routine_upper and routine_upper in _READ_RECURSIVE_ROUTINES

    # `(,LAMP)` parses as a one-element list.
    if len(node) == 1:
        atom = head_upper
        if atom in t._global_map:
            return t._global_map[atom]
        if atom in t.routine_atoms or atom.endswith("?"):
            if suppress_self_recursion:
                return "None"
            dot = routine_call_name(atom)
            if dot is not None:
                return f"{substrate_receiver(dot)}.{dot}()"
            return f"{substrate_receiver(atom.lower())}.invoke_verb({atom.lower()!r})"
        # Object reference: look up by name (strip ZIL suffixes)
        obj_name = atom.lower().replace("-", " ")
        return f'lookup("{obj_name}")'

    if head_upper in t._global_map:
        return t._global_map[head_upper]

    # Known routines dispatch on $thing; unknown become plain calls.
    if head_upper[0].isalpha() and not head_upper.startswith("V?"):
        if suppress_self_recursion:
            return "None"
        args_expr = ", ".join(t._translate_expr(a) for a in node[1:])
        if head_upper in t.routine_atoms:
            dot = routine_call_name(head_upper)
            if dot is not None:
                return f"{substrate_receiver(dot)}.{dot}({args_expr})"
            verb_name = head_upper.lower()
            receiver = substrate_receiver(verb_name)
            if args_expr:
                return f"{receiver}.invoke_verb({verb_name!r}, {args_expr})"
            return f"{receiver}.invoke_verb({verb_name!r})"
        func_name = sanitize_ident(head_upper)
        return f"{func_name}({args_expr})"

    return "None"


HANDLERS: dict[str, Handler] = {
    # Bit ops
    "BTST": _h_btst,
    "BOR": _h_bor,
    "BAND": _h_band,
    "MSB": _h_msb,
    "LSB": _h_lsb,
    "DLESS?": _h_dless_p,
    "IGRTR?": _h_igrtr_p,
    # Control
    "COND": _h_cond,
    "APPLY": _h_apply,
    # Arithmetic
    "+": _h_add,
    "ADD": _h_add,
    "-": _h_sub,
    "SUB": _h_sub,
    "*": _h_mul,
    "MUL": _h_mul,
    "/": _h_div,
    "DIV": _h_div,
    "MOD": _h_mod,
    "ABS": _h_abs,
    "MIN": _h_min,
    "MAX": _h_max,
    # Comparison
    "==": _h_equal,
    "EQUAL?": _h_equal,
    "=?": _h_equal,
    "==?": _h_equal,
    "N==?": _h_not_equal,
    "N=?": _h_not_equal,
    "G?": _h_gt,
    "GRTR?": _h_gt,
    "L?": _h_lt,
    "LESS?": _h_lt,
    "G=?": _h_ge,
    "L=?": _h_le,
    "0?": _h_zero_p,
    "ZERO?": _h_zero_p,
    "1?": _h_one_p,
    # Logic
    "AND": _h_and,
    "OR": _h_or,
    "NOT": _h_not,
    # Flag predicate
    "FSET?": _h_fset_p,
    # Object containment
    "IN?": _h_in_p,
    "LOC": _h_loc,
    "FIRST?": _h_first,
    "FIRST": _h_first,
    "ASSIGNED?": _h_assigned_p,
    "NEXT?": _h_next,
    "NEXT": _h_next,
    "GLOBAL-IN?": _h_global_in_p,
    # Macros / table ops / parser buffer
    "RFATAL": _h_rfatal,
    "PUT": _h_put,
    "PUTB": _h_putb,
    "REST": _h_rest,
    "READ": _h_read,
    "GET": _h_get,
    "GETB": _h_get,
    "INTBL?": _h_intbl_p,
    "COPYT": _h_copyt,
    "LOWCORE": _h_lowcore,
    "PRINTT": _h_printt,
    "INC": _h_inc,
    "DEC": _h_dec,
    "FONT": _h_font,
    # Properties / state
    "ASCII": _h_ascii,
    "GETP": _h_getp,
    "GETPT": _h_getpt,
    "PUTP": _h_putp_expr,
    "SETG": _h_setg_expr,
    "GVAL": _h_gval,
    # Output
    "TELL": _h_tell_expr,
    "CRLF": _h_crlf_expr,
    "PRINT": _h_print_expr,
    "PRINTI": _h_printi_expr,
    "PRINTR": _h_print_expr,
    "PRINT-CR": _h_print_expr,
    "PRINTN": _h_printn_expr,
    "PRINTC": _h_printc_expr,
    "PRINTD": _h_printd_expr,
    "PICK-ONE": _h_pick_one,
    # Verb dispatch
    "VERB?": _h_verb_p,
    "RUNNING?": _h_running,
    "PRSO?": _h_prso_p,
    "PRSI?": _h_prsi_p,
    "HERE?": _h_here_p,
    "IS?": _h_is_p,
    "T?": _h_t_p,
    # Random
    "RANDOM": _h_random,
    "PROB": _h_prob,
    # Score / death
    "SCORE": _h_score_expr,
    "JIGS-UP": _h_jigs_up_expr,
    # Z-machine session opcodes
    "QUIT": _h_quit_expr,
    "RESTART": _h_falsy,
    "RESTORE": _h_falsy,
    "SAVE": _h_falsy,
    # Daemon-table slot reference (bare form; ENABLE/DISABLE handle their
    # own wrappers in stmt_handlers).  See ``_h_int_expr`` for why this
    # must short-circuit to ``None`` rather than fall through to a verb call.
    "INT": _h_int_expr,
    # Misc
    "OBJECT-PNAME": _h_object_pname,
    "OPENABLE?": _h_openable_p,
    "PERFORM": _h_perform_expr,
    "SET": _h_set_expr,
}
