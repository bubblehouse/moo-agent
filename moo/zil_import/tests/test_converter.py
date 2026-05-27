"""IR-extraction tests.

Covers ``converter.py``: ROOM/OBJECT/ROUTINE extraction, exit-property
parsing, TABLE/LTABLE value flattening, and the SYNTAX/SYNONYM/SETG
top-level dispatch in ``extract_all``.

These exercise the converter directly with hand-rolled AST fragments so
the tests are independent of the ZIL source corpus.
"""

# pylint can't infer the parser's tuple shape for ``[node] = parse(...)``;
# every SYNTAX-rule test uses that single-element destructure pattern.
# pylint: disable=unbalanced-tuple-unpacking

from __future__ import annotations

import pytest

from moo.zil_import.converter import (
    _extract_object,
    _extract_room,
    _extract_routine,
    _extract_table_values,
    _parse_exit,
    _parse_syntax_rule,
    extract_all,
    extract_syntax_rules,
)
from moo.zil_import.parser import Str, parse, tokenize


# ---------------------------------------------------------------------------
# Exit parsing
# ---------------------------------------------------------------------------


def test_parse_exit_to_room():
    """``(NORTH TO LIVING-ROOM)`` → simple destination exit."""
    exit_ = _parse_exit("NORTH", ("NORTH", "TO", "LIVING-ROOM"))
    assert exit_.dest == "LIVING-ROOM"
    assert exit_.message is None
    assert exit_.condition is None
    assert exit_.per_routine is None


def test_parse_exit_blocked_string_message():
    """``(EAST "Locked door.")`` → blocked exit with nogo message."""
    exit_ = _parse_exit("EAST", ("EAST", Str("Locked door.")))
    assert exit_.dest is None
    assert exit_.message == "Locked door."
    assert exit_.condition is None


def test_parse_exit_to_with_if_condition():
    """``(WEST TO ROOM IF MAGIC-FLAG)`` → conditional traversal."""
    exit_ = _parse_exit("WEST", ("WEST", "TO", "STRANGE-PASSAGE", "IF", "MAGIC-FLAG"))
    assert exit_.dest == "STRANGE-PASSAGE"
    assert exit_.condition == "MAGIC-FLAG"
    assert exit_.else_message is None


def test_parse_exit_to_if_else_message():
    """``(WEST TO ROOM IF FLAG ELSE "msg")`` carries the else message too."""
    exit_ = _parse_exit(
        "WEST",
        ("WEST", "TO", "PASSAGE", "IF", "MAGIC-FLAG", "ELSE", Str("nailed shut")),
    )
    assert exit_.dest == "PASSAGE"
    assert exit_.condition == "MAGIC-FLAG"
    assert exit_.else_message == "nailed shut"


def test_parse_exit_per_routine():
    """``(DOWN PER TRAP-DOOR-EXIT)`` → routine-driven destination."""
    exit_ = _parse_exit("DOWN", ("DOWN", "PER", "TRAP-DOOR-EXIT"))
    assert exit_.per_routine == "TRAP-DOOR-EXIT"
    assert exit_.dest is None


def test_parse_exit_empty_returns_blank_exit():
    """A direction with no payload (``(NORTH)``) is a blank/blocked exit."""
    exit_ = _parse_exit("NORTH", ("NORTH",))
    assert exit_.dest is None
    assert exit_.message is None
    assert exit_.condition is None


# ---------------------------------------------------------------------------
# ROUTINE extraction
# ---------------------------------------------------------------------------


def _routine_form(src: str):
    return parse(tokenize(src))[0]


def test_extract_routine_positional_params_only():
    routine = _extract_routine(_routine_form("<ROUTINE FOO (X Y) <RTRUE>>"))
    assert routine.name == "FOO"
    assert routine.params == ["X", "Y"]
    assert not routine.aux_vars


def test_extract_routine_aux_separator():
    routine = _extract_routine(_routine_form('<ROUTINE BAR (A "AUX" B C) <RTRUE>>'))
    assert routine.params == ["A"]
    assert routine.aux_vars == ["B", "C"]


def test_extract_routine_optional_separator_skipped():
    """``"OPTIONAL"`` separates positional from optional params; both end up
    in ``params`` (the converter currently doesn't track optionality past the
    AUX boundary).  Anchors that the separator atom itself is not retained
    as a param."""
    routine = _extract_routine(_routine_form('<ROUTINE FOO (X "OPTIONAL" Y) <RTRUE>>'))
    assert "OPTIONAL" not in routine.params
    assert "X" in routine.params and "Y" in routine.params


def test_extract_routine_initial_values_captured():
    """``(VAR default)`` tuples in the arg list seed ``initial_values``."""
    routine = _extract_routine(_routine_form('<ROUTINE FOO ("AUX" (N 5) (S "hi")) <RTRUE>>'))
    assert routine.aux_vars == ["N", "S"]
    assert routine.initial_values["N"] == 5
    assert routine.initial_values["S"] == "hi"


def test_extract_routine_no_args_means_empty_param_lists():
    routine = _extract_routine(_routine_form("<ROUTINE FOO () <RTRUE>>"))
    assert not routine.params
    assert not routine.aux_vars
    assert routine.body  # has at least the RTRUE form


# ---------------------------------------------------------------------------
# TABLE / LTABLE extraction
# ---------------------------------------------------------------------------


def test_extract_table_values_bare_table():
    """A plain ``<TABLE …>`` returns its scalar entries verbatim."""
    form = parse(tokenize('<TABLE 1 2 "hi">'))[0]
    assert _extract_table_values(form) == [1, 2, "hi"]


def test_extract_table_values_ltable_prepends_length():
    """``<LTABLE …>`` carries an implicit length-at-offset-0; the converter
    prepends it so ``LKP`` / ``GO-NEXT`` can read the count."""
    form = parse(tokenize("<LTABLE A B C>"))[0]
    values = _extract_table_values(form)
    assert values[0] == 3  # length
    assert values[1:] == ["@A", "@B", "@C"]


def test_extract_table_values_atom_refs_get_at_prefix():
    """Bare uppercase atoms become ``"@<ATOM>"`` so the generator can
    distinguish them from quoted strings during emission."""
    form = parse(tokenize("<TABLE RESERVOIR-SOUTH FOREST-1>"))[0]
    assert _extract_table_values(form) == ["@RESERVOIR-SOUTH", "@FOREST-1"]


def test_extract_table_values_nil_slot_retained():
    """``<>`` inside a TABLE keeps its slot — the CYCLOPS villain record
    relies on this so V-MSGS (slot 4) stays at slot 4."""
    form = parse(tokenize("<TABLE CYCLOPS <> 0 0 CYCLOPS-MELEE>"))[0]
    assert _extract_table_values(form) == ["@CYCLOPS", None, 0, 0, "@CYCLOPS-MELEE"]


def test_extract_table_values_pure_flag_group_skipped():
    """``(PURE)`` and other parenthesised flag groups are dropped."""
    form = parse(tokenize("<TABLE (PURE) 1 2 3>"))[0]
    assert _extract_table_values(form) == [1, 2, 3]


def test_extract_table_values_nested_table_recurses():
    """Nested ``TABLE``/``LTABLE`` are stored as sublists so atom-reference
    resolution can walk them in the generator."""
    form = parse(tokenize("<TABLE <TABLE A B> <LTABLE C>>"))[0]
    values = _extract_table_values(form)
    assert values == [["@A", "@B"], [1, "@C"]]


def test_extract_table_values_non_table_returns_empty():
    """A non-TABLE form returns an empty list — guard against caller misuse."""
    assert not _extract_table_values(["NOT-A-TABLE", 1, 2])
    assert not _extract_table_values("scalar")


# ---------------------------------------------------------------------------
# ROOM / OBJECT extraction
# ---------------------------------------------------------------------------


def test_extract_room_collects_exits_flags_globals():
    form = parse(
        tokenize(
            "<ROOM WEST-OF-HOUSE "
            '(DESC "West of House") '
            '(LDESC "You are standing in an open field west of a white house.") '
            "(NORTH TO NORTH-OF-HOUSE) "
            "(SOUTH TO SOUTH-OF-HOUSE) "
            "(FLAGS RLANDBIT ONBIT SACREDBIT) "
            "(GLOBAL WHITE-HOUSE BOARD)>"
        )
    )[0]
    room = _extract_room(form)
    assert room.atom == "WEST-OF-HOUSE"
    assert room.desc == "West of House"
    assert room.ldesc.startswith("You are standing")
    directions = sorted(e.direction for e in room.exits)
    assert directions == ["NORTH", "SOUTH"]
    assert "RLANDBIT" in room.flags
    assert "WHITE-HOUSE" in room.globals


def test_extract_room_falls_back_to_ldesc_for_desc():
    """A room with only LDESC gets a synthesized ``desc`` from the first
    sentence of LDESC."""
    form = parse(tokenize('<ROOM FOREST-1 (LDESC "This is a forest. Trees are everywhere.")>'))[0]
    room = _extract_room(form)
    assert room.desc == "This is a forest"


def test_extract_object_synonyms_lowercased():
    form = parse(
        tokenize('<OBJECT TROPHY-CASE (IN LIVING-ROOM) (SYNONYM CASE TROPHY) (ADJECTIVE TROPHY) (DESC "trophy case")>')
    )[0]
    obj = _extract_object(form)
    assert obj.atom == "TROPHY-CASE"
    assert obj.location == "LIVING-ROOM"
    assert obj.synonyms == ["case", "trophy"]
    assert obj.adjectives == ["trophy"]


def test_extract_object_vtype_lowercased():
    form = parse(tokenize("<OBJECT MAGIC-BOAT (IN RESERVOIR-SOUTH) (VTYPE NONLANDBIT) (FLAGS VEHBIT)>"))[0]
    obj = _extract_object(form)
    assert obj.vtype == "nonlandbit"


# ---------------------------------------------------------------------------
# extract_all top-level dispatch
# ---------------------------------------------------------------------------


def test_extract_all_separates_bare_and_compound_syntax():
    """``<SYNTAX TURN OFF OBJECT = V-LAMP-OFF>`` populates
    ``compound_verb_dict``; bare ``<SYNTAX EXAMINE OBJECT = V-EXAMINE>``
    populates ``bare_syntax_dict``.  Both end up in ``syntax_dict``.
    """
    nodes = parse(tokenize("<SYNTAX EXAMINE OBJECT = V-EXAMINE> <SYNTAX TURN OFF OBJECT = V-LAMP-OFF>"))
    _, _, _, _, _, syntax_dict, _, compound_verb_dict, bare_syntax_dict = extract_all(nodes)
    assert "EXAMINE" in syntax_dict
    assert "TURN" in syntax_dict
    assert ("TURN", "OFF") in compound_verb_dict
    assert compound_verb_dict[("TURN", "OFF")] == "V-LAMP-OFF"
    assert "EXAMINE" in bare_syntax_dict
    assert "TURN" not in bare_syntax_dict  # particle-bearing rules excluded


# ---------------------------------------------------------------------------
# ZilSyntaxRule reification (Phase 1 of the syntax-row refactor)
# ---------------------------------------------------------------------------


def test_parse_syntax_rule_bare_one_arity():
    """``<SYNTAX EXAMINE OBJECT = V-EXAMINE>`` → arity 1, no particle, no iobj_prep."""
    [node] = parse(tokenize("<SYNTAX EXAMINE OBJECT = V-EXAMINE>"))
    rule = _parse_syntax_rule(node)
    assert rule is not None
    assert rule.verb == "EXAMINE"
    assert rule.arity == 1
    assert rule.v_routine == "V-EXAMINE"
    assert rule.particle is None
    assert rule.iobj_prep is None


def test_parse_syntax_rule_particle_one_arity():
    """``<SYNTAX TURN OFF OBJECT = V-LAMP-OFF>`` → particle ``OFF``, arity 1."""
    [node] = parse(tokenize("<SYNTAX TURN OFF OBJECT = V-LAMP-OFF>"))
    rule = _parse_syntax_rule(node)
    assert rule is not None
    assert rule.verb == "TURN"
    assert rule.particle == "OFF"
    assert rule.arity == 1
    assert rule.iobj_prep is None
    assert rule.v_routine == "V-LAMP-OFF"


def test_parse_syntax_rule_iobj_prep_two_arity():
    """``<SYNTAX PUT OBJECT IN OBJECT = V-PUT-IN>`` → iobj_prep ``IN``, arity 2."""
    [node] = parse(tokenize("<SYNTAX PUT OBJECT IN OBJECT = V-PUT-IN>"))
    rule = _parse_syntax_rule(node)
    assert rule is not None
    assert rule.verb == "PUT"
    assert rule.arity == 2
    assert rule.particle is None
    assert rule.iobj_prep == "IN"
    assert rule.v_routine == "V-PUT-IN"


def test_parse_syntax_rule_skips_find_have_constraints():
    """``(FIND TAKEBIT)`` and ``(HAVE …)`` tuples are skipped during parse."""
    [node] = parse(tokenize("<SYNTAX PUT OBJECT (FIND TAKEBIT) (HAVE TAKE HELD) IN OBJECT (FIND CONTBIT) = V-PUT-IN>"))
    rule = _parse_syntax_rule(node)
    assert rule is not None
    assert rule.verb == "PUT"
    assert rule.arity == 2
    assert rule.iobj_prep == "IN"
    assert rule.particle is None


def test_parse_syntax_rule_zero_arity_intransitive():
    """``<SYNTAX INVENTORY = V-INVENTORY>`` → arity 0, no objects."""
    [node] = parse(tokenize("<SYNTAX INVENTORY = V-INVENTORY>"))
    rule = _parse_syntax_rule(node)
    assert rule is not None
    assert rule.verb == "INVENTORY"
    assert rule.arity == 0
    assert rule.particle is None
    assert rule.iobj_prep is None


def test_parse_syntax_rule_malformed_returns_none():
    """Missing ``=`` or missing V-routine → returns None."""
    [no_eq] = parse(tokenize("<SYNTAX FOO OBJECT V-FOO>"))
    assert _parse_syntax_rule(no_eq) is None
    [no_routine] = parse(tokenize("<SYNTAX FOO OBJECT =>"))
    assert _parse_syntax_rule(no_routine) is None


def test_extract_syntax_rules_groups_by_verb():
    """Multiple SYNTAX rules per verb collect into one list."""
    nodes = parse(
        tokenize(
            "<SYNTAX PUT OBJECT IN OBJECT = V-PUT-IN> "
            "<SYNTAX PUT OBJECT ON OBJECT = V-PUT-ON> "
            "<SYNTAX TURN OFF OBJECT = V-LAMP-OFF>"
        )
    )
    rules = extract_syntax_rules(nodes)
    assert set(rules) == {"PUT", "TURN"}
    put_routines = [(r.iobj_prep, r.v_routine) for r in rules["PUT"]]
    assert ("IN", "V-PUT-IN") in put_routines
    assert ("ON", "V-PUT-ON") in put_routines
    assert rules["TURN"][0].particle == "OFF"


def test_extract_all_and_extract_syntax_rules_agree_on_arity():
    """The legacy syntax_dict and the typed rules report identical
    (arity, v_routine) shape — the inline branch in ``extract_all``
    derives its dict from the same parser the side helper uses."""
    nodes = parse(tokenize("<SYNTAX EXAMINE OBJECT = V-EXAMINE> <SYNTAX PUT OBJECT IN OBJECT = V-PUT-IN>"))
    _, _, _, _, _, syntax_dict, _, _, _ = extract_all(nodes)
    rules = extract_syntax_rules(nodes)
    for verb, rule_list in rules.items():
        legacy = syntax_dict[verb]
        derived = [(r.arity, r.v_routine) for r in rule_list]
        assert derived == legacy


def test_extract_all_synonym_keyed_by_canonical_atom():
    """``<SYNONYM ATTACK FIGHT HURT INJURE>`` keys aliases under the
    canonical ATTACK atom."""
    nodes = parse(tokenize("<SYNONYM ATTACK FIGHT HURT>"))
    _, _, _, _, _, _, synonyms_dict, _, _ = extract_all(nodes)
    assert synonyms_dict["ATTACK"] == ["FIGHT", "HURT"]


def test_extract_all_global_table_lands_in_tables_dict():
    nodes = parse(tokenize("<GLOBAL HERO-MELEE <TABLE 1 2 3>>"))
    _, _, _, tables, _, _, _, _, _ = extract_all(nodes)
    assert "HERO-MELEE" in tables
    assert tables["HERO-MELEE"].values == [1, 2, 3]


def test_extract_all_scalar_global_lands_in_globals_dict():
    nodes = parse(tokenize("<GLOBAL LOAD-ALLOWED 100>"))
    _, _, _, _, globals_dict, _, _, _, _ = extract_all(nodes)
    assert globals_dict["LOAD-ALLOWED"] == 100


def test_extract_all_setg_seeds_zstate():
    """Top-level ``<SETG ZORK-NUMBER 1>`` initializes a zstate slot."""
    nodes = parse(tokenize("<SETG ZORK-NUMBER 1>"))
    _, _, _, _, globals_dict, _, _, _, _ = extract_all(nodes)
    assert globals_dict["ZORK-NUMBER"] == 1


def test_extract_all_constant_seeds_globals():
    """``<CONSTANT MISSED 1>`` joins globals_dict for zstate-style lookups."""
    nodes = parse(tokenize("<CONSTANT MISSED 1>"))
    _, _, _, _, globals_dict, _, _, _, _ = extract_all(nodes)
    assert globals_dict["MISSED"] == 1


def test_extract_all_global_does_not_overwrite_setg():
    """When both SETG and GLOBAL/CONSTANT name the same atom, the first
    win — SETG carries mutable state semantics that CONSTANT can't override.
    """
    nodes = parse(tokenize("<SETG FLAG 1> <CONSTANT FLAG 99>"))
    _, _, _, _, globals_dict, _, _, _, _ = extract_all(nodes)
    assert globals_dict["FLAG"] == 1


def test_extract_all_skips_malformed_top_level_nodes():
    """A non-list / non-string-head node must not crash the loop."""
    nodes = ["just-a-string", 42, [None, 1, 2]]
    rooms, objects, routines, tables, *_ = extract_all(nodes)
    assert not rooms
    assert not objects
    assert not routines
    assert not tables


# ---------------------------------------------------------------------------
# Round-trip — converter accepts real-world routine shapes
# ---------------------------------------------------------------------------


def test_extract_all_round_trip_routine_object_room():
    nodes = parse(
        tokenize(
            '<ROOM CELLAR (DESC "Cellar") (FLAGS NDESCBIT)> '
            "<OBJECT LANTERN (IN CELLAR) (FLAGS LIGHTBIT TAKEBIT)> "
            "<ROUTINE LIGHT-LANTERN () <FSET ,LANTERN ,ONBIT>>"
        )
    )
    rooms, objects, routines, *_ = extract_all(nodes)
    assert "CELLAR" in rooms
    assert "LANTERN" in objects
    assert "LIGHT-LANTERN" in routines


# Property-based smoke: every public property on the dataclasses survives a
# round-trip through tokenize + parse + extract.  Catches accidental
# regressions where a new converter rule eats a field.
@pytest.mark.parametrize(
    "src,attr,expected",
    [
        ('<ROOM R (DESC "Foo") (VALUE 25)>', "value", 25),
        ("<OBJECT O (IN R) (CAPACITY 7)>", "capacity", 7),
        ("<OBJECT O (IN R) (TVALUE 4)>", "tvalue", 4),
    ],
)
def test_extract_room_object_scalar_properties(src, attr, expected):
    node = parse(tokenize(src))[0]
    extractor = _extract_room if node[0] == "ROOM" else _extract_object
    item = extractor(node)
    assert getattr(item, attr) == expected
