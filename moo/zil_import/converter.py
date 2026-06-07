"""
Convert parsed ZIL AST nodes into IR dataclasses.

See :doc:`/reference/zil-importer`.
"""

from __future__ import annotations

import logging
from typing import Any

from .game_config import GameConfig
from .ir import (
    DIRECTION_ATOMS,
    ZilExit,
    ZilObject,
    ZilRoom,
    ZilRoutine,
    ZilSyntaxRule,
    ZilTable,
)

log = logging.getLogger(__name__)


def _is_form(node: Any, head: str) -> bool:
    """
    True when ``node`` is a list whose head atom equals ``head``.

    :param node: AST node to test.
    :param head: Expected head atom.
    :returns: ``True`` for matching forms.
    """
    return isinstance(node, list) and len(node) >= 1 and node[0] == head


def _is_group(node: Any) -> bool:
    """
    True when ``node`` is a parenthesised ZIL group (``tuple`` in our AST).

    :param node: AST node to test.
    :returns: ``True`` for tuples.
    """
    return isinstance(node, tuple)


def _str_or_none(val: Any) -> str | None:
    """
    Return ``val`` when it is a string, else ``None``.

    :param val: Candidate value.
    :returns: ``val`` if it's a ``str``; otherwise ``None``.
    """
    return val if isinstance(val, str) else None


def _parse_exit(direction: str, prop: tuple) -> ZilExit:
    """
    Parse a direction property tuple into a :class:`ZilExit`.

    Recognised forms:

    * ``(NORTH TO ROOM-NAME)`` — flat EZIP form
    * ``(EAST "blocked message")``
    * ``(WEST TO ROOM IF FLAG)``
    * ``(WEST TO ROOM IF FLAG ELSE "message")``
    * ``(DOWN PER ROUTINE-NAME)``

    XZIP (v5) titles wrap the exit value in a ``<…>`` form, so the value
    arrives as a single nested list — ``(NW <TO ON-PIKE>)`` →
    ``("NW", ["TO", "ON-PIKE"])``.  Such a value is unwrapped and parsed by
    the same rules, plus the XZIP-only exit macros:

    * ``<SAY-TO ROOM "message">`` — move, printing a message
    * ``<SORRY "message">`` — blocked exit that prints a message
    * ``<THRU DOOR ROOM>`` — traverse a door object into a room

    :param direction: The direction atom (NORTH / EAST / …).
    :param prop: The full property tuple (head + tail).
    :returns: A populated :class:`ZilExit`.
    """
    rest = list(prop[1:])  # everything after the direction atom

    # XZIP wraps the exit routine in a <…> form, so the direction's value is a
    # single nested list/tuple.  EZIP uses flat tokens, which never trip this.
    if len(rest) == 1 and isinstance(rest[0], (list, tuple)):
        rest = list(rest[0])

    if not rest:
        return ZilExit(
            direction=direction, dest=None, message=None, condition=None, else_message=None, per_routine=None
        )

    # String-only: blocked exit with message
    if isinstance(rest[0], str) and not rest[0].isupper():
        return ZilExit(
            direction=direction, dest=None, message=rest[0], condition=None, else_message=None, per_routine=None
        )
    if isinstance(rest[0], str) and rest[0] == rest[0] and len(rest) == 1 and " " in rest[0]:
        # Multi-word string captured as one string token
        return ZilExit(
            direction=direction, dest=None, message=rest[0], condition=None, else_message=None, per_routine=None
        )

    # SORRY "message" — XZIP blocked exit (prints a message, no traversal)
    if rest[0] == "SORRY":
        msg = rest[1] if len(rest) > 1 and isinstance(rest[1], str) else None
        return ZilExit(direction=direction, dest=None, message=msg, condition=None, else_message=None, per_routine=None)

    # SAY-TO room "message" — XZIP move-with-message
    if rest[0] == "SAY-TO":
        dest = rest[1] if len(rest) > 1 and isinstance(rest[1], str) else None
        msg = rest[2] if len(rest) > 2 and isinstance(rest[2], str) else None
        return ZilExit(direction=direction, dest=dest, message=msg, condition=None, else_message=None, per_routine=None)

    # THRU door room — XZIP traversal through a door object; the destination
    # is the room (the trailing atom).  The door guard is not modelled yet.
    if rest[0] == "THRU":
        atoms = [a for a in rest[1:] if isinstance(a, str)]
        dest = atoms[-1] if atoms else None
        return ZilExit(
            direction=direction, dest=dest, message=None, condition=None, else_message=None, per_routine=None
        )

    # PER routine
    if rest[0] == "PER":
        routine = rest[1] if len(rest) > 1 else None
        return ZilExit(
            direction=direction, dest=None, message=None, condition=None, else_message=None, per_routine=routine
        )

    # TO room [IF flag [ELSE "message"]]
    if rest[0] == "TO":
        dest = rest[1] if len(rest) > 1 else None
        condition = None
        else_message = None
        if len(rest) > 2 and rest[2] == "IF":
            condition = rest[3] if len(rest) > 3 else None
            if len(rest) > 4 and rest[4] == "ELSE":
                else_message = rest[5] if len(rest) > 5 else None
        return ZilExit(
            direction=direction,
            dest=dest,
            message=None,
            condition=condition,
            else_message=else_message,
            per_routine=None,
        )

    # Fallback: treat first atom as destination
    if isinstance(rest[0], str):
        return ZilExit(
            direction=direction, dest=rest[0], message=None, condition=None, else_message=None, per_routine=None
        )

    log.warning("Could not parse exit %s: %r", direction, prop)
    return ZilExit(direction=direction, dest=None, message=None, condition=None, else_message=None, per_routine=None)


def _extract_room(form: list) -> ZilRoom:
    """
    Build a :class:`ZilRoom` from a parsed ``<ROOM ...>`` form.

    :param form: The ROOM form (head + atom + property groups).
    :returns: Populated :class:`ZilRoom`.
    """
    atom = form[1]
    desc = ""
    ldesc = None
    fdesc = None
    exits: list[ZilExit] = []
    flags: list[str] = []
    globals_list: list[str] = []
    action = None
    value = 0
    pseudo: list[tuple[str, str]] = []

    for prop in form[2:]:
        if not _is_group(prop) or not prop:
            continue
        key = prop[0] if prop else None
        if not isinstance(key, str):
            continue
        key = key.upper()

        if key == "DESC":
            desc = prop[1] if len(prop) > 1 else ""
        elif key == "LDESC":
            ldesc = prop[1] if len(prop) > 1 else None
        elif key == "FDESC":
            fdesc = prop[1] if len(prop) > 1 else None
        elif key in DIRECTION_ATOMS:
            # (IN ROOMS) is the room's container declaration, not an exit direction
            if key == "IN" and len(prop) == 2 and prop[1] == "ROOMS":
                pass
            else:
                exits.append(_parse_exit(key, prop))
        elif key == "FLAGS":
            flags.extend(str(f).upper() for f in prop[1:] if isinstance(f, str))
        elif key == "GLOBAL":
            globals_list.extend(str(g).upper() for g in prop[1:] if isinstance(g, str))
        elif key == "ACTION":
            action = prop[1] if len(prop) > 1 else None
        elif key == "VALUE":
            value = prop[1] if len(prop) > 1 and isinstance(prop[1], int) else 0
        elif key == "PSEUDO":
            # (PSEUDO "word" routine "word2" routine2 ...)
            items = list(prop[1:])
            for i in range(0, len(items) - 1, 2):
                word = items[i] if isinstance(items[i], str) else str(items[i])
                rtn = items[i + 1] if isinstance(items[i + 1], str) else str(items[i + 1])
                pseudo.append((word, rtn))
        elif key in ("IN",):
            pass  # always ROOMS — skip
        elif key == "LOC":
            # XZIP room-objects declare their container as (LOC ROOMS); that
            # marker only identifies them as rooms (see ``_is_room_object``)
            # and is not a room property — skip it.
            pass
        else:
            pass  # unknown property — skip silently

    if not desc and ldesc:
        # Some rooms only have LDESC; use first sentence as desc
        desc = ldesc.split(".")[0].strip()

    return ZilRoom(
        atom=atom,
        desc=desc,
        ldesc=ldesc,
        fdesc=fdesc,
        exits=exits,
        flags=flags,
        globals=globals_list,
        action=action,
        value=value,
        pseudo=pseudo,
    )


def _extract_object(form: list, placement_prop: str = "IN", in_is_dir: bool = False) -> ZilObject:
    """
    Build a :class:`ZilObject` from a parsed ``<OBJECT ...>`` form.

    :param form: The OBJECT form (head + atom + property groups).
    :param placement_prop: Property atom naming the object's container.
        EZIP uses ``IN``; XZIP (Beyond Zork) uses ``LOC``.
    :param in_is_dir: When true (XZIP), an ``(IN …)`` group is the
        enter-direction exit and is ignored here rather than read as
        placement.
    :returns: Populated :class:`ZilObject`.
    """
    atom = form[1]
    location = None
    synonyms: list[str] = []
    adjectives: list[str] = []
    desc = None
    ldesc = None
    fdesc = None
    text = None
    flags: list[str] = []
    action = None
    capacity = 0
    size = 5
    value = 0
    tvalue = 0
    vtype = None

    for prop in form[2:]:
        if not _is_group(prop) or not prop:
            continue
        key = prop[0] if prop else None
        if not isinstance(key, str):
            continue
        key = key.upper()

        if key == placement_prop:
            location = prop[1] if len(prop) > 1 else None
        elif key == "IN" and in_is_dir:
            # XZIP: (IN <TO …>) is the enter-direction exit, not placement.
            # Objects carry no exits, so drop it.
            pass
        elif key == "SYNONYM":
            synonyms.extend(str(s).lower() for s in prop[1:] if isinstance(s, str))
        elif key == "ADJECTIVE":
            adjectives.extend(str(a).lower() for a in prop[1:] if isinstance(a, str))
        elif key == "DESC":
            desc = prop[1] if len(prop) > 1 else None
        elif key == "LDESC":
            ldesc = prop[1] if len(prop) > 1 else None
        elif key == "FDESC":
            fdesc = prop[1] if len(prop) > 1 else None
        elif key == "TEXT":
            text = prop[1] if len(prop) > 1 else None
        elif key == "FLAGS":
            flags.extend(str(f).upper() for f in prop[1:] if isinstance(f, str))
        elif key == "ACTION":
            action = prop[1] if len(prop) > 1 else None
        elif key == "CAPACITY":
            capacity = prop[1] if len(prop) > 1 and isinstance(prop[1], int) else 0
        elif key == "SIZE":
            size = prop[1] if len(prop) > 1 and isinstance(prop[1], int) else 5
        elif key == "VALUE":
            value = prop[1] if len(prop) > 1 and isinstance(prop[1], int) else 0
        elif key == "TVALUE":
            tvalue = prop[1] if len(prop) > 1 and isinstance(prop[1], int) else 0
        elif key == "VTYPE":
            # (VTYPE NONLANDBIT) — vehicle type atom; lower-cased to match ROOM_FLAG_PROPERTIES.
            vtype_atom = prop[1] if len(prop) > 1 and isinstance(prop[1], str) else None
            if vtype_atom:
                vtype = vtype_atom.lower()

    return ZilObject(
        atom=atom,
        location=location,
        synonyms=synonyms,
        adjectives=adjectives,
        desc=desc,
        ldesc=ldesc,
        fdesc=fdesc,
        text=text,
        flags=flags,
        action=action,
        capacity=capacity,
        size=size,
        value=value,
        tvalue=tvalue,
        vtype=vtype,
    )


def _extract_routine(form: list) -> ZilRoutine:
    """
    Parse a ROUTINE form into a :class:`ZilRoutine`.

    ZIL header syntax::

        (ROUTINE name (arg1 arg2 "AUX" local1 local2) body...)

    The arg-list is ``form[2]`` if it's a group; body starts at
    ``form[2]`` or ``form[3]``.

    :param form: The ROUTINE form.
    :returns: Populated :class:`ZilRoutine`.
    """
    name = form[1] if len(form) > 1 else "UNKNOWN"

    params: list[str] = []
    aux_vars: list[str] = []
    initial_values: dict = {}
    body_start = 2

    # form[2] may be a tuple (arg-list group) or immediately a body form
    if len(form) > 2 and isinstance(form[2], tuple):
        arg_list = form[2]
        body_start = 3
        in_aux = False
        for item in arg_list:
            # ZIL keyword separators — boundary between positional and keyword groups.
            if isinstance(item, str) and item.upper() in ("AUX", '"AUX"'):
                in_aux = True
                continue
            # "OPT" is the short form of "OPTIONAL" (Beyond Zork / Zork Zero use
            # it exclusively; the EZIP games use the long form).  Both are
            # keyword separators, not parameters — skipping them keeps the
            # positional/optional params correctly aligned with call args.
            if isinstance(item, str) and item.upper() in ("OPTIONAL", '"OPTIONAL"', "OPT", '"OPT"'):
                continue
            # (VAR default) tuples — capture initial value for the translator's initializer.
            if isinstance(item, tuple) and item:
                var_name = str(item[0]).upper() if isinstance(item[0], str) else None
                if var_name is None:
                    continue
                if len(item) > 1:
                    initial_values[var_name] = item[1]
                if in_aux:
                    aux_vars.append(var_name)
                else:
                    params.append(var_name)
            elif isinstance(item, str):
                if in_aux:
                    aux_vars.append(item.upper())
                else:
                    params.append(item.upper())

    body = list(form[body_start:])
    raw_zil = repr(form[:6])  # first few elements for inline comment context

    return ZilRoutine(
        name=name,
        params=params,
        aux_vars=aux_vars,
        body=body,
        raw_zil=raw_zil,
        initial_values=initial_values,
    )


def _extract_table_values(form: Any) -> list:
    """
    Extract values from a ZIL ``TABLE`` / ``LTABLE`` form.

    Strings, ints, ``<>`` (None), and bare atom references are kept;
    nested tables recurse; ``(PURE)`` flag groups are discarded.
    ``LTABLE`` prepends the implicit length so ``GO-NEXT``'s
    ``table_get(tbl, 0)`` reads the count.  See
    :doc:`/reference/zil-importer` (Converter notes) for the full rule
    set; the generator's ``035_tables.py`` resolves atom references at
    runtime.

    :param form: The TABLE / LTABLE form.
    :returns: Flat list of values; ``[]`` for non-table inputs.
    """
    if not isinstance(form, list) or not form:
        return []
    head = form[0]
    if head not in ("TABLE", "LTABLE", "PTABLE", "PLTABLE"):
        return []
    from .parser import Str

    values = []
    for item in form[1:]:
        if isinstance(item, Str):
            # Quoted string — game text.
            values.append(str(item))
        elif isinstance(item, int):
            values.append(item)
        elif item is None:
            # ZIL ``<>`` (nil) — slot the literal None so the table keeps
            # its positional layout.  CYCLOPS's villain record
            # ``<TABLE CYCLOPS <> 0 0 CYCLOPS-MELEE>`` needs the second
            # slot held; without this, V-MSGS (slot 4) shifts to slot 3.
            values.append(None)
        elif isinstance(item, str):
            # Bare atom — atom reference.  Prefix with ``@`` so the
            # generator can distinguish atom refs from regular strings
            # when emitting bootstrap code.
            values.append("@" + item)
        elif isinstance(item, list) and item and item[0] in ("TABLE", "LTABLE", "PTABLE", "PLTABLE"):
            # Nested TABLE / LTABLE / PTABLE — recurse and embed as a sub-list.
            values.append(_extract_table_values(item))
        elif isinstance(item, tuple):
            # Parenthesized flag group like ``(PURE)`` — skip.
            continue
    if head in ("LTABLE", "PLTABLE"):
        # ZIL's LTABLE / PLTABLE store the element count at offset 0 implicitly
        # (PLTABLE is the pure/read-only variant of LTABLE — same length
        # prefix).  Without the PLTABLE prefix, ``<GET tbl 0>`` read the first
        # element instead of the count and ``<GET tbl 1>`` the second element
        # instead of the first — Beyond Zork's SCRAMBLE crashed on
        # ``,FOREST-ROOMS`` (``int + Object`` in the maze-table arithmetic),
        # since the generated code, translated from ZIL, expects the prefix.
        return [len(values)] + values
    return values


_CONST_EXPR_OPS = ("+", "-", "*", "/")


def _eval_const_expr(form: Any, ns: dict[str, int]) -> int | None:
    """
    Evaluate a ZIL compile-time constant expression to an int, or ``None``.

    ZIL writes compile-time arithmetic as ``%<OP a b ...>`` (the ``%`` read-time
    eval marker drops in tokenisation, leaving a plain form ``["OP", a, b, ...]``).
    The supported operators are the variadic integer ops ``+ - * /``; operands are
    int literals, other already-resolved constant names (looked up in ``ns``), or
    nested expressions.  Division truncates toward zero (Z-machine semantics).

    :param form: An int, an atom name (str), or an ``["OP", ...]`` list.
    :param ns: Namespace of constant/global name → int resolved so far.
    :returns: The integer value, or ``None`` if any operand is unresolvable.
    """
    if isinstance(form, bool):
        return None
    if isinstance(form, int):
        return form
    if isinstance(form, str):
        return ns.get(form)
    if isinstance(form, list) and form and form[0] in _CONST_EXPR_OPS:
        op = form[0]
        args = [_eval_const_expr(a, ns) for a in form[1:]]
        if not args or any(a is None for a in args):
            return None
        acc = args[0]
        for val in args[1:]:
            if op == "+":
                acc += val
            elif op == "-":
                acc -= val
            elif op == "*":
                acc *= val
            else:  # "/" — Z-machine division truncates toward zero
                if val == 0:
                    return None
                acc = int(acc / val)
        return acc
    return None


def _extract_itable_values(form: Any, ns: dict[str, int]) -> list | None:
    """
    Expand a ZIL ``<ITABLE count (spec) fill...>`` form into a value list.

    ``ITABLE`` builds a table of ``count`` entries.  ``count`` may be an int
    literal or a compile-time expression resolvable via ``ns``.  An optional
    parenthesised spec group (``(BYTE)`` / ``(WORD)`` / ``(LEXV)`` / ``(PURE)``)
    sets element size and is skipped — every element is one list slot in our
    model.  Any trailing fill values form a pattern repeated to fill the table;
    with none given, entries default to ``0``.

    :param form: The ``["ITABLE", ...]`` form.
    :param ns: Namespace for resolving a symbolic ``count``.
    :returns: A list of ``count`` entries, or ``None`` if ``count`` is unknown.
    """
    if not isinstance(form, list) or not form or form[0] != "ITABLE" or len(form) < 2:
        return None
    count = _eval_const_expr(form[1], ns)
    if count is None or count < 0:
        return None
    fill: list = []
    for item in form[2:]:
        if isinstance(item, tuple):
            # (BYTE) / (WORD) / (LEXV) / (PURE) spec group — informational.
            continue
        if isinstance(item, int):
            fill.append(item)
        elif isinstance(item, str):
            # Atom reference — resolve if known, else keep as an @-ref so the
            # generator can resolve it at bootstrap time (mirrors TABLE).
            resolved = ns.get(item)
            fill.append(resolved if resolved is not None else "@" + item)
        elif item is None:
            fill.append(None)
    if not fill:
        fill = [0]
    return [fill[i % len(fill)] for i in range(count)]


def _parse_syntax_rule(node: list) -> ZilSyntaxRule | None:
    """
    Parse one ``<SYNTAX … = V-ROUTINE>`` form into a :class:`ZilSyntaxRule`.

    Walks the tokens between the verb atom and ``=``: counts ``OBJECT``
    occurrences (arity), collects the single string token before the
    first ``OBJECT`` as ``particle``, and the single string token
    between the two ``OBJECT`` slots as ``iobj_prep``.  Parenthesised
    constraint groups like ``(FIND TAKEBIT)`` and ``(HAVE …)`` are
    skipped — the V-routine does its own object-state checks.

    :param node: A parsed ZIL form whose head is ``"SYNTAX"``.
    :returns: A populated :class:`ZilSyntaxRule`, or ``None`` if the
        form is malformed (no verb atom, no ``=``, or no V-routine).
    """
    if not isinstance(node, list) or len(node) < 4:
        return None
    verb = node[1] if isinstance(node[1], str) else None
    if not verb:
        return None
    try:
        eq_idx = next(i for i, t in enumerate(node) if t == "=")
    except StopIteration:
        return None
    after_eq = [t for t in node[eq_idx + 1 :] if isinstance(t, str)]
    if not after_eq:
        return None
    v_routine = after_eq[0]

    arity = 0
    particle_tokens: list[str] = []
    between_tokens: list[str] = []
    for tok in node[2:eq_idx]:
        if tok == "OBJECT":
            arity += 1
            continue
        if not isinstance(tok, str):
            # Parenthesised tuples like (FIND TAKEBIT) — skip.
            continue
        if arity == 0:
            particle_tokens.append(tok)
        elif arity == 1:
            between_tokens.append(tok)
        # arity == 2 trailing tokens (rare; would be a third-OBJECT
        # prep) are ignored — ZIL syntax is dobj+iobj max.
    return ZilSyntaxRule(
        verb=verb,
        arity=arity,
        v_routine=v_routine,
        particle=particle_tokens[0] if particle_tokens else None,
        iobj_prep=between_tokens[0] if between_tokens else None,
    )


def extract_syntax_rules(nodes: list) -> dict[str, list[ZilSyntaxRule]]:
    """
    Walk parsed ZIL nodes and produce a verb → rules map.

    Side-helper to :func:`extract_all` that returns the SYNTAX table as
    a typed rule list per verb atom.  Used by the refactored generator
    to emit one verb file per ``(verb, particle, iobj_prep, arity)``
    cell.  ``extract_all`` populates the legacy ``syntax_dict`` /
    ``compound_verb_dict`` / ``bare_syntax_dict`` views from the same
    rules so back-compat consumers keep working.

    :param nodes: Top-level AST nodes from :func:`moo.zil_import.parser.parse`.
    :returns: Verb atom → ordered list of :class:`ZilSyntaxRule`.
    """
    rules: dict[str, list[ZilSyntaxRule]] = {}
    for node in nodes:
        if not isinstance(node, list) or not node or node[0] != "SYNTAX":
            continue
        rule = _parse_syntax_rule(node)
        if rule is None:
            continue
        rules.setdefault(rule.verb, []).append(rule)
    return rules


def _is_room_object(form: list) -> bool:
    """
    Does this ``<OBJECT …>`` form actually declare a room?

    XZIP titles (Beyond Zork) have no ``<ROOM>`` head; rooms are plain
    objects marked by ``(LOC ROOMS)`` and a ``LOCATION`` flag.  Both
    markers are required so a normal object placed in some other container
    (``(LOC GURDY)``) is never mistaken for a room.

    :param form: A parsed ``<OBJECT …>`` form.
    :returns: True if the form carries the room marker.
    """
    loc_is_rooms = False
    has_location_flag = False
    for prop in form[2:]:
        if not _is_group(prop) or not prop:
            continue
        key = prop[0]
        if not isinstance(key, str):
            continue
        key = key.upper()
        if key == "LOC" and len(prop) > 1 and prop[1] == "ROOMS":
            loc_is_rooms = True
        elif key == "FLAGS" and any(isinstance(f, str) and f.upper() == "LOCATION" for f in prop[1:]):
            has_location_flag = True
    return loc_is_rooms and has_location_flag


def extract_all(
    nodes: list,
    cfg: GameConfig | None = None,
) -> tuple[
    dict[str, ZilRoom],
    dict[str, ZilObject],
    dict[str, ZilRoutine],
    dict[str, ZilTable],
    dict[str, object],
    dict[str, list[tuple[int, str]]],
    dict[str, list[str]],
    dict[tuple[str, str], str],
    dict[str, list[tuple[int, str]]],
]:
    """
    Walk parsed ZIL AST and extract every IR collection.

    ``compound_verb_dict`` maps ``(verb, particle)`` → V-routine for
    forms like ``<SYNTAX TURN OFF OBJECT = V-LAMP-OFF>`` so the
    generator can emit particle-aware dispatchers.

    :param nodes: Top-level AST nodes from :func:`moo.zil_import.parser.parse`.
    :param cfg: Per-game config supplying the Z-machine dialect knobs.
        When ``None``, EZIP defaults apply (rooms are ``<ROOM>`` forms,
        objects are placed with ``(IN …)``) so classic games are
        unaffected.
    :returns: 9-tuple of ``(rooms, objects, routines, tables,
        globals_dict, syntax_dict, synonyms_dict, compound_verb_dict,
        bare_syntax_dict)``.
    """
    rooms_as_objects = bool(cfg and cfg.rooms_as_objects)
    placement_prop = cfg.placement_property if cfg else "IN"
    in_is_dir = bool(cfg and cfg.in_is_direction)

    rooms: dict[str, ZilRoom] = {}
    objects: dict[str, ZilObject] = {}
    routines: dict[str, ZilRoutine] = {}
    tables: dict[str, ZilTable] = {}
    globals_dict: dict[str, object] = {}
    # Resolved integer constants/globals, accumulated in source order so a
    # later compile-time expression (``%<* ,MWIDTH ,MHEIGHT>``) or symbolic
    # ITABLE length can reference earlier ones.
    const_ns: dict[str, int] = {}
    syntax_dict: dict[str, list[tuple[int, str]]] = {}
    synonyms_dict: dict[str, list[str]] = {}
    compound_verb_dict: dict[tuple[str, str], str] = {}
    bare_syntax_dict: dict[str, list[tuple[int, str]]] = {}

    for node in nodes:
        if not isinstance(node, list) or not node:
            continue
        head = node[0]
        if not isinstance(head, str):
            continue

        if head == "ROOM" and len(node) >= 2:
            try:
                room = _extract_room(node)
                rooms[room.atom] = room
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                log.warning("Failed to parse ROOM %r: %s", node[1] if len(node) > 1 else "?", exc)

        elif head == "OBJECT" and len(node) >= 2:
            if rooms_as_objects and _is_room_object(node):
                # XZIP: a room declared as an <OBJECT> with (LOC ROOMS) +
                # LOCATION flag.  Parse it through the room extractor so its
                # exits/GLOBAL/ACTION come through.
                try:
                    room = _extract_room(node)
                    rooms[room.atom] = room
                except (ValueError, KeyError, IndexError, TypeError) as exc:
                    log.warning("Failed to parse room-object %r: %s", node[1] if len(node) > 1 else "?", exc)
                continue
            try:
                obj = _extract_object(node, placement_prop=placement_prop, in_is_dir=in_is_dir)
                objects[obj.atom] = obj
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                log.warning("Failed to parse OBJECT %r: %s", node[1] if len(node) > 1 else "?", exc)

        elif head == "ROUTINE" and len(node) >= 2:
            try:
                routine = _extract_routine(node)
                routines[routine.name] = routine
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                log.warning("Failed to parse ROUTINE %r: %s", node[1] if len(node) > 1 else "?", exc)

        elif head == "GLOBAL" and len(node) >= 3:
            # <GLOBAL NAME <TABLE ...>> / <LTABLE ...> / <PTABLE ...>.
            # PTABLE is a packed-addressing variant in the Z-machine but
            # holds the same value list at the language level — used by
            # HHG's INDENTS (a packed string table) and a few other
            # display-helper globals.
            name = node[1] if isinstance(node[1], str) else None
            value_form = node[2] if len(node) > 2 else None
            if (
                name
                and isinstance(value_form, list)
                and value_form
                and value_form[0] in ("TABLE", "LTABLE", "PTABLE", "PLTABLE", "ITABLE")
            ):
                try:
                    if value_form[0] == "ITABLE":
                        # <ITABLE n (BYTE) 0> — a scratch buffer the renderer /
                        # parser fills at runtime; seed it zero-filled at length.
                        values = _extract_itable_values(value_form, const_ns)
                    else:
                        values = _extract_table_values(value_form)
                    if values:
                        tables[name] = ZilTable(name=name, values=values)
                except (ValueError, KeyError, IndexError, TypeError) as exc:
                    log.warning("Failed to parse GLOBAL TABLE %r: %s", name, exc)
            elif name and isinstance(value_form, list) and value_form and value_form[0] in _CONST_EXPR_OPS:
                # ``<GLOBAL FOO %<* ,A ,B>>`` — compile-time arithmetic init.
                resolved = _eval_const_expr(value_form, const_ns)
                if resolved is not None:
                    globals_dict[name] = resolved
                    const_ns[name] = resolved
            elif name and isinstance(value_form, (int, str, type(None))):
                # Scalar global: ``<GLOBAL LOAD-ALLOWED 100>`` initialises a
                # zstate slot that ITAKE / V-WALK / etc. read at runtime.  A
                # symbolic value (``<GLOBAL MAPX ,CENTERX>``) resolves to the
                # referenced constant when known.
                if isinstance(value_form, str) and value_form in const_ns:
                    globals_dict[name] = const_ns[value_form]
                    const_ns[name] = const_ns[value_form]
                else:
                    globals_dict[name] = value_form
                    if isinstance(value_form, int):
                        const_ns[name] = value_form

        elif head == "SETG" and len(node) >= 3:
            # Top-level ``<SETG ZORK-NUMBER 1>`` initialises a zstate slot the
            # same way ``<GLOBAL FOO 100>`` does — translated routines branch
            # on these via ``player.zstate_get("ZORK-NUMBER")`` and silently
            # fall through to the ZORK-NUMBER == 0 path otherwise.
            name = node[1] if isinstance(node[1], str) else None
            value_form = node[2] if len(node) > 2 else None
            if name and isinstance(value_form, (int, str)) and name not in globals_dict:
                globals_dict[name] = value_form
                if isinstance(value_form, int):
                    const_ns[name] = value_form

        elif head == "CONSTANT" and len(node) >= 3:
            # ``<CONSTANT MISSED 1>`` — Z-machine compile-time integer
            # constant.  Translated routines reference these via the same
            # ``player.zstate_get("MISSED")`` path as scalar globals; without
            # seeding, HERO-BLOW's ``RES == ,MISSED`` comparisons all read
            # ``None`` and the COND chain falls through to the LOSE-WEAPON
            # branch unconditionally (the per-result-code switch never
            # matches).  GLOBAL/SETG of the same name wins — those carry
            # mutable state, while CONSTANTs are pure-data lookups.
            name = node[1] if isinstance(node[1], str) else None
            value_form = node[2] if len(node) > 2 else None
            if name is None or name in globals_dict:
                pass
            elif isinstance(value_form, int):
                globals_dict[name] = value_form
                const_ns[name] = value_form
            elif (
                isinstance(value_form, list)
                and value_form
                and value_form[0] in ("TABLE", "LTABLE", "PTABLE", "PLTABLE", "ITABLE")
            ):
                # ``<CONSTANT SLINE <ITABLE ,SLINE-LENGTH (BYTE) 0>>`` — a
                # constant-named static table the renderer reads/scrolls.
                try:
                    if value_form[0] == "ITABLE":
                        values = _extract_itable_values(value_form, const_ns)
                    else:
                        values = _extract_table_values(value_form)
                    if values:
                        tables[name] = ZilTable(name=name, values=values)
                except (ValueError, KeyError, IndexError, TypeError) as exc:
                    log.warning("Failed to parse CONSTANT TABLE %r: %s", name, exc)
            elif isinstance(value_form, list) and value_form and value_form[0] in _CONST_EXPR_OPS:
                # ``<CONSTANT MAP-SIZE %<* ,MWIDTH ,MHEIGHT>>`` — compile-time
                # arithmetic; resolve against constants seen so far.
                resolved = _eval_const_expr(value_form, const_ns)
                if resolved is not None:
                    globals_dict[name] = resolved
                    const_ns[name] = resolved

        elif head == "SYNTAX" and len(node) >= 4:
            # ``<SYNTAX LIGHT OBJECT (FIND LIGHTBIT) ... = V-LAMP-ON>``.
            # Parse the form once into a typed :class:`ZilSyntaxRule`
            # then derive the legacy dict views.  Bare and compound
            # rules both go into ``syntax_dict`` so the generator sees
            # the full arity picture; compound rules (those with a
            # ``particle``) ALSO populate ``compound_verb_dict`` keyed
            # by ``(verb, particle)`` so the dispatcher generator can
            # emit particle-aware routing.  ``bare_syntax_dict`` keeps
            # the no-particle rules for _ROUTINE_TO_VERBS population:
            # a compound like ``<SYNTAX EXAMINE IN OBJECT = V-LOOK-INSIDE>``
            # must not drag the bare-form ``examine`` alias into the
            # V-LOOK-INSIDE substrate's shebang.
            rule = _parse_syntax_rule(node)
            if rule is None:
                continue
            syntax_dict.setdefault(rule.verb, []).append((rule.arity, rule.v_routine))
            if rule.particle:
                compound_verb_dict.setdefault((rule.verb, rule.particle), rule.v_routine)
            else:
                bare_syntax_dict.setdefault(rule.verb, []).append((rule.arity, rule.v_routine))

        elif head in ("SYNONYM", "VERB-SYNONYM") and len(node) >= 3:
            # ``<SYNONYM ATTACK FIGHT HURT INJURE HIT>`` — first atom is
            # canonical, the rest are aliases that resolve to the same verb.
            # ``<VERB-SYNONYM I INVENTORY>`` is the same shape (Beyond Zork
            # uses it to make ``inventory`` an alias of the primary verb
            # ``I``); without recognising it the English word never reached
            # the dispatcher and ``inventory`` parsed as "I don't know how
            # to do that."
            atoms = [t for t in node[1:] if isinstance(t, str)]
            if len(atoms) >= 2:
                synonyms_dict.setdefault(atoms[0], []).extend(atoms[1:])

    return (
        rooms,
        objects,
        routines,
        tables,
        globals_dict,
        syntax_dict,
        synonyms_dict,
        compound_verb_dict,
        bare_syntax_dict,
    )
